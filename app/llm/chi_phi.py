"""Tính toán, theo dõi chi phí sử dụng token và kiểm soát ngân sách mô hình.

Bao gồm các chức năng chính:
- Ước tính chi phí theo bảng giá config/models.yaml (hỗ trợ đánh dấu ước tính thô cho OpenRouter Auto)
- Ghi nhận lịch sử từng lượt gọi vào bảng cơ sở dữ liệu luot_goi
- Kiểm tra trần ngân sách ngày (NGAN_SACH_NGAY_USD): từ chối gọi với HTTP 503 khi vượt, cảnh báo ở 80%
- Giám sát tỷ lệ rơi tầng trong 1 giờ gần nhất: cảnh báo khi tỷ lệ không được tầng 1 phục vụ > 20%
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Optional, Tuple, Union

from sqlalchemy import func, select

from app.config import CauHinhTang, doc_cau_hinh_models, lay_cau_hinh
from app.core.database import LuotGoi, lay_phien_db

logger = logging.getLogger(__name__)

# Lưu lại lý do hỏng gần nhất của tầng 1 trong bộ nhớ để báo cáo khi tỷ lệ rơi tầng tăng cao
_ly_do_hong_tang_1_gan_nhat: str = "Chưa có sự cố nào được ghi nhận"


class VuotNganSachError(Exception):
    """Ngoại lệ khi tổng chi phí trong ngày vượt quá giới hạn ngân sách cho phép."""

    def __init__(
        self,
        thong_diep: str,
        chi_phi_hien_tai: float = 0.0,
        ngan_sach_ngay: float = 0.0,
    ):
        self.chi_phi_hien_tai = chi_phi_hien_tai
        self.ngan_sach_ngay = ngan_sach_ngay
        self.status_code = 503
        super().__init__(thong_diep)


def cap_nhat_ly_do_hong_tang_1(ly_do: str) -> None:
    """Cập nhật lý do hỏng gần nhất của tầng 1 để phục vụ giám sát cảnh báo."""
    global _ly_do_hong_tang_1_gan_nhat
    _ly_do_hong_tang_1_gan_nhat = ly_do


def lay_ly_do_hong_tang_1_gan_nhat() -> str:
    """Lấy lý do hỏng gần nhất của tầng 1."""
    return _ly_do_hong_tang_1_gan_nhat


def tinh_chi_phi_usd(
    token_vao: int,
    token_ra: int,
    gia_vao_moi_trieu: float,
    gia_ra_moi_trieu: float,
) -> float:
    """Tính toán chi phí ước tính (USD) dựa trên số lượng token và đơn giá mỗi triệu token.

    Args:
        token_vao: Số lượng token đầu vào (prompt tokens).
        token_ra: Số lượng token đầu ra (completion tokens).
        gia_vao_moi_trieu: Giá mỗi triệu token đầu vào (USD).
        gia_ra_moi_trieu: Giá mỗi triệu token đầu ra (USD).

    Returns:
        float: Chi phí ước tính bằng USD, làm tròn đến 8 chữ số thập phân.
    """
    chi_phi_vao = (token_vao / 1_000_000.0) * gia_vao_moi_trieu
    chi_phi_ra = (token_ra / 1_000_000.0) * gia_ra_moi_trieu
    tong_chi_phi = chi_phi_vao + chi_phi_ra
    return round(tong_chi_phi, 8)


def uoc_tinh_chi_phi(
    tang: Union[int, str, CauHinhTang],
    token_vao: int,
    token_ra: int,
) -> float:
    """Ước tính chi phí lượt gọi (USD) dựa trên tầng và cấu hình trong config/models.yaml.

    Args:
        tang: Số thứ tự tầng (1, 2, 3, 4), tên định danh tầng ('gemini', 'openrouter_auto',...)
              hoặc đối tượng CauHinhTang.
        token_vao: Số token đầu vào.
        token_ra: Số token đầu ra.

    Returns:
        float: Chi phí ước tính USD làm tròn đến 8 chữ số thập phân.
    """
    gia_vao = 0.0
    gia_ra = 0.0

    if isinstance(tang, CauHinhTang):
        gia_vao = tang.gia_vao_usd_moi_trieu
        gia_ra = tang.gia_ra_usd_moi_trieu
    else:
        cau_hinh = doc_cau_hinh_models()
        tang_tim_thay: Optional[CauHinhTang] = None
        for t in cau_hinh.chuoi_du_phong:
            if isinstance(tang, int) and t.tang == tang:
                tang_tim_thay = t
                break
            elif isinstance(tang, str) and (t.ten == tang or str(t.tang) == tang):
                tang_tim_thay = t
                break

        if tang_tim_thay:
            gia_vao = tang_tim_thay.gia_vao_usd_moi_trieu
            gia_ra = tang_tim_thay.gia_ra_usd_moi_trieu
        else:
            logger.warning(f"Không tìm thấy cấu hình giá cho tầng {tang} trong models.yaml")

    return tinh_chi_phi_usd(token_vao, token_ra, gia_vao, gia_ra)


def ghi_nhan_luot_goi(
    tang: int,
    model: str,
    token_vao: int = 0,
    token_ra: int = 0,
    chi_phi_usd: float = 0.0,
    do_tre_ms: float = 0.0,
    thanh_cong: bool = True,
    nguoi_dung_id: str = "khach",
    thoi_diem: Optional[datetime] = None,
    ghi_chu: Optional[str] = None,
) -> Optional[int]:
    """Ghi một dòng nhật ký lượt gọi vào bảng luot_goi trong cơ sở dữ liệu.

    Args:
        tang: Số thứ tự tầng phục vụ (1, 2, 3, 4).
        model: Tên model thực tế được sử dụng.
        token_vao: Số token đầu vào.
        token_ra: Số token đầu ra.
        chi_phi_usd: Chi phí tính bằng USD.
        do_tre_ms: Độ trễ phản hồi (mili-giây).
        thanh_cong: Trạng thái thành công hay thất bại.
        nguoi_dung_id: Định danh người dùng gọi mô hình.
        thoi_diem: Mốc thời gian (mặc định lấy thời điểm hiện tại UTC).
        ghi_chu: Ghi chú bổ sung (ví dụ: 'uoc_tinh_tho' cho OpenRouter Auto hoặc thông tin lỗi).

    Returns:
        Optional[int]: ID của bản ghi vừa tạo nếu thành công, None nếu có lỗi cơ sở dữ liệu.
    """
    if thoi_diem is None:
        thoi_diem = datetime.now(timezone.utc)

    try:
        with lay_phien_db() as phien:
            ban_ghi = LuotGoi(
                thoi_diem=thoi_diem,
                nguoi_dung_id=nguoi_dung_id,
                tang=tang,
                model=model,
                token_vao=token_vao,
                token_ra=token_ra,
                chi_phi_usd=chi_phi_usd,
                do_tre_ms=do_tre_ms,
                thanh_cong=thanh_cong,
                ghi_chu=ghi_chu,
            )
            phien.add(ban_ghi)
            phien.flush()
            return ban_ghi.id
    except Exception as e:
        logger.error(f"Lỗi khi ghi nhận lượt gọi vào cơ sở dữ liệu: {e}")
        return None


def lay_tong_chi_phi_hom_nay() -> float:
    """Tính tổng chi phí (USD) của tất cả lượt gọi trong ngày hiện tại (UTC)."""
    dau_ngay = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        with lay_phien_db() as phien:
            stmt = select(func.coalesce(func.sum(LuotGoi.chi_phi_usd), 0.0)).where(
                LuotGoi.thoi_diem >= dau_ngay
            )
            tong_chi_phi = phien.scalar(stmt)
            return float(tong_chi_phi or 0.0)
    except Exception as e:
        logger.error(f"Lỗi khi tính tổng chi phí hôm nay: {e}")
        return 0.0


def kiem_tra_ngan_sach() -> Tuple[float, float]:
    """Kiểm tra tổng chi phí trong ngày trước mỗi lượt gọi mô hình.

    Quy tắc:
    - Vượt NGAN_SACH_NGAY_USD: từ chối ngay lập tức bằng ngoại lệ VuotNganSachError (HTTP 503).
    - Đạt từ 80% ngân sách: ghi nhật ký cảnh báo (WARNING) mỗi lần gọi.

    Returns:
        Tuple[float, float]: (chi_phi_hien_tai, ngan_sach_ngay)

    Raises:
        VuotNganSachError: Khi chi phí hôm nay vượt quá ngân sách ngày.
    """
    cau_hinh = lay_cau_hinh()
    ngan_sach_ngay = float(cau_hinh.env.NGAN_SACH_NGAY_USD)
    chi_phi_hien_tai = lay_tong_chi_phi_hom_nay()

    # Kiểm tra vượt trần 100% ngân sách
    if chi_phi_hien_tai >= ngan_sach_ngay:
        thong_diep = (
            f"Hệ thống đã đạt giới hạn ngân sách hàng ngày ({ngan_sach_ngay:.2f} USD). "
            f"Hiện tại tổng chi phí hôm nay là ${chi_phi_hien_tai:.4f} USD. "
            f"Vui lòng thử lại vào ngày mai hoặc liên hệ quản trị viên."
        )
        logger.error(f"[Ngân sách] {thong_diep}")
        raise VuotNganSachError(
            thong_diep=thong_diep,
            chi_phi_hien_tai=chi_phi_hien_tai,
            ngan_sach_ngay=ngan_sach_ngay,
        )

    # Cảnh báo khi đạt ngưỡng 80% ngân sách
    if ngan_sach_ngay > 0 and chi_phi_hien_tai >= 0.8 * ngan_sach_ngay:
        phan_tram = (chi_phi_hien_tai / ngan_sach_ngay) * 100.0
        logger.warning(
            f"[Cảnh báo ngân sách] Chi phí hôm nay (${chi_phi_hien_tai:.4f}) đã đạt "
            f"{phan_tram:.1f}% ngân sách ngày (${ngan_sach_ngay:.2f} USD)."
        )

    return (chi_phi_hien_tai, ngan_sach_ngay)


def tinh_ty_le_roi_tang_1h() -> Tuple[float, str]:
    """Tính tỷ lệ phần trăm số lượt KHÔNG được tầng 1 phục vụ trong 1 giờ gần nhất.

    Nếu tỷ lệ vượt 20%, ghi nhật ký mức cảnh báo (WARNING) kèm lý do hỏng gần nhất của tầng 1.

    Returns:
        Tuple[float, str]: (ty_le_phan_tram, ly_do_hong_tang_1)
    """
    mot_gio_truoc = datetime.now(timezone.utc) - timedelta(hours=1)
    ly_do_hong = lay_ly_do_hong_tang_1_gan_nhat()

    try:
        with lay_phien_db() as phien:
            # Tổng số lượt gọi trong 1 giờ qua
            tong_luot_stmt = select(func.count(LuotGoi.id)).where(LuotGoi.thoi_diem >= mot_gio_truoc)
            tong_luot = phien.scalar(tong_luot_stmt) or 0

            if tong_luot == 0:
                return (0.0, ly_do_hong)

            # Số lượt không được tầng 1 phục vụ (hoặc tầng 1 bị hỏng)
            # Bao gồm: các lượt phục vụ bởi tầng 2, 3, 4 HOẶC lượt gọi thất bại
            roi_tang_stmt = select(func.count(LuotGoi.id)).where(
                LuotGoi.thoi_diem >= mot_gio_truoc,
                (LuotGoi.tang != 1) | (LuotGoi.thanh_cong.is_(False)),
            )
            so_luot_roi = phien.scalar(roi_tang_stmt) or 0

            ty_le = round((so_luot_roi / tong_luot) * 100.0, 2)

            # Cảnh báo nếu vượt quá ngưỡng 20%
            if ty_le > 20.0:
                logger.warning(
                    f"[CẢNH BÁO TỶ LỆ RƠI TẦNG] Tỷ lệ lượt gọi không được tầng 1 phục vụ "
                    f"trong 1 giờ qua là {ty_le:.1f}% (vượt ngưỡng 20%). "
                    f"Đây là dấu hiệu sớm của sự cố hoặc hoá đơn tăng cao. "
                    f"Lý do hỏng gần nhất của tầng 1: {ly_do_hong}"
                )

            return (ty_le, ly_do_hong)

    except Exception as e:
        logger.error(f"Lỗi khi tính tỷ lệ rơi tầng 1 giờ qua: {e}")
        return (0.0, ly_do_hong)


def lay_thong_ke_chi_phi_ngay() -> Dict[str, Any]:
    """Tổng hợp dữ liệu thống kê chi phí và số lượt gọi trong ngày phục vụ endpoint GET /chi-phi."""
    cau_hinh = lay_cau_hinh()
    ngan_sach_ngay = float(cau_hinh.env.NGAN_SACH_NGAY_USD)
    dau_ngay = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    chi_phi_hom_nay = 0.0
    phan_ra_theo_tang: Dict[str, float] = {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0}
    so_luot_theo_tang: Dict[str, int] = {"1": 0, "2": 0, "3": 0, "4": 0}

    try:
        with lay_phien_db() as phien:
            # Thống kê chi phí và số lượt theo từng tầng trong ngày
            stmt = (
                select(
                    LuotGoi.tang,
                    func.coalesce(func.sum(LuotGoi.chi_phi_usd), 0.0),
                    func.count(LuotGoi.id),
                )
                .where(LuotGoi.thoi_diem >= dau_ngay)
                .group_by(LuotGoi.tang)
            )
            for tang, chi_phi, so_luot in phien.execute(stmt):
                key = str(tang)
                phan_ra_theo_tang[key] = round(float(chi_phi or 0.0), 6)
                so_luot_theo_tang[key] = int(so_luot or 0)
                chi_phi_hom_nay += float(chi_phi or 0.0)

    except Exception as e:
        logger.error(f"Lỗi khi tổng hợp thống kê chi phí: {e}")

    chi_phi_hom_nay = round(chi_phi_hom_nay, 6)
    phan_tram_da_dung = (
        round((chi_phi_hom_nay / ngan_sach_ngay) * 100.0, 2) if ngan_sach_ngay > 0 else 0.0
    )

    ty_le_roi_tang, _ = tinh_ty_le_roi_tang_1h()

    return {
        "chi_phi_hom_nay_usd": chi_phi_hom_nay,
        "ngan_sach_ngay_usd": ngan_sach_ngay,
        "phan_tram_da_dung": phan_tram_da_dung,
        "phan_ra_theo_tang": phan_ra_theo_tang,
        "so_luot_theo_tang": so_luot_theo_tang,
        "ty_le_roi_tang_1_gio_qua": ty_le_roi_tang,
    }
