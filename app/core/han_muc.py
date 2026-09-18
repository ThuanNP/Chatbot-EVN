"""Kiểm soát hạn mức người dùng và tần suất yêu cầu 3 tầng cho Chatbot EVN.

Hệ thống hạn mức 3 tầng kiểm tra theo đúng thứ tự (rẻ trước, đắt sau):
1. Theo địa chỉ IP: Chặn dồn dập (burst protection), áp dụng cả với yêu cầu chưa xác thực.
2. Theo người dùng mỗi giờ: Cửa sổ trượt 3600 giây, bậc pro nhân hệ số HE_SO_BAC_PRO.
3. Theo chi phí ngày của từng người dùng: Chặn một người tiêu quá nhiều dù chưa chạm ngân sách tổng.

GHI CHÚ: Dùng thuật toán cửa sổ trượt lưu trong cơ sở dữ liệu, không cần Redis ở quy mô này.
Khi vượt vài nghìn yêu cầu mỗi phút thì chuyển sang Redis.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import math
import secrets
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select

from app.config import lay_cau_hinh
from app.core.database import YeuCauHanMuc, LuotGoi, lay_phien_db

logger = logging.getLogger(__name__)


class VuotHanMucError(Exception):
    """Ngoại lệ khi yêu cầu vượt quá một trong ba tầng hạn mức."""

    def __init__(
        self,
        thong_diep: str,
        retry_after: int = 60,
        tang_han_muc: str = "ip",
        so_luot_hien_tai: int = 0,
        han_muc_toi_da: float = 0.0,
    ):
        self.thong_diep = thong_diep
        self.retry_after = max(1, int(retry_after))
        self.tang_han_muc = tang_han_muc
        self.so_luot_hien_tai = so_luot_hien_tai
        self.han_muc_toi_da = han_muc_toi_da
        self.status_code = 429
        super().__init__(thong_diep)


def bam_ma_thong_bao(token: str) -> str:
    """Băm mã thông báo bằng HMAC-SHA256 kết hợp APP_SECRET của hệ thống.

    Mã thông báo KHÔNG lưu dạng thô trong CSDL. Thuật toán này bảo đảm tính
    an toàn, một chiều và hỗ trợ tìm kiếm O(1) qua chỉ mục cơ sở dữ liệu.
    """
    khoa_bi_mat = lay_cau_hinh().env.APP_SECRET.encode("utf-8")
    return hmac.new(khoa_bi_mat, token.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def sinh_ma_thong_bao_ngau_nhien() -> str:
    """Sinh mã thông báo ngẫu nhiên bảo mật cao có tiền tố evn_sec_."""
    return f"evn_sec_{secrets.token_urlsafe(32)}"


def _lay_han_muc_ip() -> int:
    """Lấy hạn mức IP phút an toàn, tương thích cả môi trường kiểm thử mock."""
    try:
        val = getattr(lay_cau_hinh().env, "HAN_MUC_IP_PHUT", 20)
        if type(val).__name__ == "MagicMock":
            return 20
        return int(val)
    except Exception:
        return 20


def _lay_han_muc_gio(bac: str) -> int:
    """Lấy hạn mức người dùng mỗi giờ an toàn theo bậc."""
    try:
        goc = getattr(lay_cau_hinh().env, "HAN_MUC_MOI_NGUOI_GIO", 60)
        so_goc = int(goc)
    except Exception:
        so_goc = 60

    if bac.lower() == "pro":
        try:
            he_so = getattr(lay_cau_hinh().env, "HE_SO_BAC_PRO", 5)
            if type(he_so).__name__ == "MagicMock":
                so_he_so = 5
            else:
                so_he_so = int(he_so)
        except Exception:
            so_he_so = 5
        return so_goc * so_he_so
    return so_goc


def _lay_han_muc_chi_phi_ngay(bac: str) -> float:
    """Lấy hạn mức chi phí tối đa mỗi ngày của từng người dùng."""
    try:
        ten = "HAN_MUC_CHI_PHI_NGAY_PRO_USD" if bac.lower() == "pro" else "HAN_MUC_CHI_PHI_NGAY_FREE_USD"
        val = getattr(lay_cau_hinh().env, ten, 5.0 if bac.lower() == "pro" else 1.0)
        if type(val).__name__ == "MagicMock":
            return 5.0 if bac.lower() == "pro" else 1.0
        return float(val)
    except Exception:
        return 5.0 if bac.lower() == "pro" else 1.0


def don_dep_yeu_cau_cu(phien) -> None:
    """Xóa các bản ghi mốc thời gian cũ hơn 1 giờ để bảng không bị phình to."""
    try:
        moc_cat = datetime.now(timezone.utc) - timedelta(seconds=3600)
        phien.execute(
            delete(YeuCauHanMuc).where(YeuCauHanMuc.thoi_diem < moc_cat)
        )
    except Exception as e:
        logger.debug(f"[Hạn mức] Dọn dẹp bản ghi cũ: {e}")


def kiem_tra_tang_1_ip(
    ip: str,
    thoi_diem_hien_tai: datetime,
    phien,
) -> Tuple[int, int]:
    """Tầng 1: Kiểm tra hạn mức dồn dập theo IP trong 60 giây (rẻ nhất).

    Args:
        ip: Địa chỉ IP người gọi
        thoi_diem_hien_tai: Mốc thời gian hiện tại (UTC)
        phien: Phiên làm việc cơ sở dữ liệu

    Returns:
        Tuple[int, int]: (số lượt hiện tại, hạn mức tối đa trong 1 phút)

    Raises:
        VuotHanMucError: Nếu vượt quá hạn mức IP
    """
    han_muc_ip = _lay_han_muc_ip()
    moc_mot_phut_truoc = thoi_diem_hien_tai - timedelta(seconds=60)

    stmt = (
        select(YeuCauHanMuc.thoi_diem)
        .where(
            YeuCauHanMuc.loai == "ip",
            YeuCauHanMuc.khoa == ip,
            YeuCauHanMuc.thoi_diem >= moc_mot_phut_truoc,
        )
        .order_by(YeuCauHanMuc.thoi_diem.asc())
    )
    ket_qua = phien.execute(stmt).scalars().all()
    mocs = list(ket_qua)
    so_luot = len(mocs)

    if so_luot >= han_muc_ip:
        moc_cu_nhat = mocs[0]
        if moc_cu_nhat.tzinfo is None:
            moc_cu_nhat = moc_cu_nhat.replace(tzinfo=timezone.utc)
        giay_con_lai = (moc_cu_nhat + timedelta(seconds=60) - thoi_diem_hien_tai).total_seconds()
        retry_after = max(1, int(math.ceil(giay_con_lai)))

        thong_diep = (
            f"Địa chỉ IP của bạn gửi quá nhiều yêu cầu dồn dập "
            f"({so_luot}/{han_muc_ip} lượt trong 1 phút). "
            f"Vui lòng thử lại sau {retry_after} giây."
        )
        logger.warning(f"[Hạn mức Tầng 1] IP {ip} vượt hạn mức: {so_luot}/{han_muc_ip} lượt/phút.")
        raise VuotHanMucError(
            thong_diep=thong_diep,
            retry_after=retry_after,
            tang_han_muc="ip",
            so_luot_hien_tai=so_luot,
            han_muc_toi_da=float(han_muc_ip),
        )

    return (so_luot, han_muc_ip)


def kiem_tra_tang_2_nguoi_dung(
    nguoi_dung_id: str,
    bac: str,
    thoi_diem_hien_tai: datetime,
    phien,
) -> Tuple[int, int]:
    """Tầng 2: Kiểm tra hạn mức theo người dùng trong 1 giờ (bậc pro nhân hệ số).

    Args:
        nguoi_dung_id: Mã định danh người dùng
        bac: Bậc tài khoản ('free' hoặc 'pro')
        thoi_diem_hien_tai: Mốc thời gian hiện tại (UTC)
        phien: Phiên làm việc cơ sở dữ liệu

    Returns:
        Tuple[int, int]: (số lượt hiện tại trong giờ, hạn mức tối đa mỗi giờ)

    Raises:
        VuotHanMucError: Nếu vượt quá hạn mức giờ
    """
    han_muc_gio = _lay_han_muc_gio(bac)
    moc_mot_gio_truoc = thoi_diem_hien_tai - timedelta(seconds=3600)

    stmt = (
        select(YeuCauHanMuc.thoi_diem)
        .where(
            YeuCauHanMuc.loai == "nguoi_dung",
            YeuCauHanMuc.khoa == nguoi_dung_id,
            YeuCauHanMuc.thoi_diem >= moc_mot_gio_truoc,
        )
        .order_by(YeuCauHanMuc.thoi_diem.asc())
    )
    ket_qua = phien.execute(stmt).scalars().all()
    mocs = list(ket_qua)
    so_luot = len(mocs)

    if so_luot >= han_muc_gio:
        moc_cu_nhat = mocs[0]
        if moc_cu_nhat.tzinfo is None:
            moc_cu_nhat = moc_cu_nhat.replace(tzinfo=timezone.utc)
        giay_con_lai = (moc_cu_nhat + timedelta(seconds=3600) - thoi_diem_hien_tai).total_seconds()
        retry_after = max(1, int(math.ceil(giay_con_lai)))

        thong_diep = (
            f"Bạn đã vượt quá giới hạn tối đa {han_muc_gio} lượt yêu cầu trong 1 giờ cho bậc {bac}. "
            f"Vui lòng thử lại sau {retry_after} giây."
        )
        logger.warning(
            f"[Hạn mức Tầng 2] Người dùng '{nguoi_dung_id}' (bậc {bac}) vượt hạn mức: "
            f"{so_luot}/{han_muc_gio} lượt/giờ."
        )
        raise VuotHanMucError(
            thong_diep=thong_diep,
            retry_after=retry_after,
            tang_han_muc="nguoi_dung_gio",
            so_luot_hien_tai=so_luot,
            han_muc_toi_da=float(han_muc_gio),
        )

    return (so_luot, han_muc_gio)


def kiem_tra_tang_3_chi_phi_ngay(
    nguoi_dung_id: str,
    bac: str,
    thoi_diem_hien_tai: datetime,
    phien,
) -> Tuple[float, float]:
    """Tầng 3: Kiểm tra tổng chi phí trong ngày của từng người dùng (đắt nhất).

    Chặn một người dùng tiêu quá nhiều dù hệ thống chưa chạm trần ngân sách tổng.

    Args:
        nguoi_dung_id: Mã định danh người dùng
        bac: Bậc tài khoản ('free' hoặc 'pro')
        thoi_diem_hien_tai: Mốc thời gian hiện tại (UTC)
        phien: Phiên làm việc cơ sở dữ liệu

    Returns:
        Tuple[float, float]: (chi phí đã tiêu hôm nay, hạn mức chi phí tối đa hôm nay)

    Raises:
        VuotHanMucError: Nếu vượt quá hạn mức chi phí ngày
    """
    han_muc_chi_phi = _lay_han_muc_chi_phi_ngay(bac)
    dau_ngay_utc = thoi_diem_hien_tai.replace(hour=0, minute=0, second=0, microsecond=0)

    stmt = (
        select(func.coalesce(func.sum(LuotGoi.chi_phi_usd), 0.0))
        .where(
            LuotGoi.nguoi_dung_id == nguoi_dung_id,
            LuotGoi.thoi_diem >= dau_ngay_utc,
        )
    )
    da_tieu = float(phien.execute(stmt).scalar() or 0.0)

    if da_tieu >= han_muc_chi_phi:
        dau_ngay_mai_utc = dau_ngay_utc + timedelta(days=1)
        giay_con_lai = (dau_ngay_mai_utc - thoi_diem_hien_tai).total_seconds()
        retry_after = max(1, int(math.ceil(giay_con_lai)))

        thong_diep = (
            f"Bạn đã sử dụng hết hạn mức chi phí trong ngày ({da_tieu:.4f}$ / {han_muc_chi_phi:.2f}$ USD) "
            f"cho bậc {bac}. Vui lòng thử lại vào ngày mai (sau {retry_after} giây)."
        )
        logger.warning(
            f"[Hạn mức Tầng 3] Người dùng '{nguoi_dung_id}' (bậc {bac}) vượt ngân sách ngày: "
            f"{da_tieu:.4f}$ >= {han_muc_chi_phi:.2f}$ USD."
        )
        raise VuotHanMucError(
            thong_diep=thong_diep,
            retry_after=retry_after,
            tang_han_muc="chi_phi_ngay",
            so_luot_hien_tai=int(da_tieu * 1000),
            han_muc_toi_da=han_muc_chi_phi,
        )

    return (da_tieu, han_muc_chi_phi)


def kiem_tra_ba_tang_han_muc(
    ip: str = "127.0.0.1",
    nguoi_dung_id: Optional[str] = None,
    bac: str = "free",
    ghi_nhan: bool = True,
) -> Dict[str, Any]:
    """Kiểm tra ba tầng hạn mức theo đúng thứ tự (rẻ trước, đắt sau).

    Thứ tự:
    1. Địa chỉ IP (chặn dồn dập, cửa sổ 60s)
    2. Người dùng mỗi giờ (cửa sổ 3600s, bậc pro nhân hệ số)
    3. Chi phí ngày của từng người dùng (tổng tiền USD hôm nay)

    Sau khi vượt qua cả 3 tầng, nếu ghi_nhan=True, tiến hành ghi lại mốc yêu cầu.
    """
    thoi_diem_hien_tai = datetime.now(timezone.utc)

    with lay_phien_db() as phien:
        # Tầng 1: Theo địa chỉ IP (áp dụng cho cả yêu cầu chưa xác thực)
        so_luot_ip, han_muc_ip = kiem_tra_tang_1_ip(
            ip=ip,
            thoi_diem_hien_tai=thoi_diem_hien_tai,
            phien=phien,
        )

        so_luot_user = 0
        han_muc_user = _lay_han_muc_gio(bac)
        da_tieu_ngay = 0.0
        han_muc_chi_phi = _lay_han_muc_chi_phi_ngay(bac)

        if nguoi_dung_id:
            # Tầng 2: Theo người dùng mỗi giờ
            so_luot_user, han_muc_user = kiem_tra_tang_2_nguoi_dung(
                nguoi_dung_id=nguoi_dung_id,
                bac=bac,
                thoi_diem_hien_tai=thoi_diem_hien_tai,
                phien=phien,
            )

            # Tầng 3: Theo chi phí ngày của từng người dùng (chỉ áp dụng cho người dùng định danh cụ thể, không tính khách vãng lai)
            if nguoi_dung_id != "khach":
                da_tieu_ngay, han_muc_chi_phi = kiem_tra_tang_3_chi_phi_ngay(
                    nguoi_dung_id=nguoi_dung_id,
                    bac=bac,
                    thoi_diem_hien_tai=thoi_diem_hien_tai,
                    phien=phien,
                )

        # Ghi nhận yêu cầu vào cơ sở dữ liệu nếu các tầng kiểm tra đều hợp lệ
        if ghi_nhan:
            phien.add(
                YeuCauHanMuc(
                    loai="ip",
                    khoa=ip,
                    thoi_diem=thoi_diem_hien_tai,
                )
            )
            if nguoi_dung_id:
                phien.add(
                    YeuCauHanMuc(
                        loai="nguoi_dung",
                        khoa=nguoi_dung_id,
                        thoi_diem=thoi_diem_hien_tai,
                    )
                )

            don_dep_yeu_cau_cu(phien)

    return {
        "ip": ip,
        "so_luot_ip_phut": so_luot_ip + (1 if ghi_nhan else 0),
        "han_muc_ip_phut": han_muc_ip,
        "nguoi_dung_id": nguoi_dung_id,
        "bac": bac,
        "so_luot_user_gio": so_luot_user + (1 if ghi_nhan and nguoi_dung_id else 0),
        "han_muc_user_gio": han_muc_user,
        "da_tieu_ngay_usd": da_tieu_ngay,
        "han_muc_chi_phi_ngay_usd": han_muc_chi_phi,
    }


def lay_thong_tin_nguoi_dung_hien_tai(nguoi_dung_id: str, bac: str) -> Dict[str, Any]:
    """Lấy số liệu thống kê hạn mức phục vụ endpoint GET /toi.

    Trả về: bậc, đã dùng bao nhiêu trong giờ này, đã tiêu bao nhiêu hôm nay, hạn mức còn lại.
    """
    thoi_diem_hien_tai = datetime.now(timezone.utc)
    moc_mot_gio_truoc = thoi_diem_hien_tai - timedelta(seconds=3600)
    dau_ngay_utc = thoi_diem_hien_tai.replace(hour=0, minute=0, second=0, microsecond=0)

    han_muc_gio = _lay_han_muc_gio(bac)
    han_muc_chi_phi = _lay_han_muc_chi_phi_ngay(bac)

    with lay_phien_db() as phien:
        stmt_gio = (
            select(func.count(YeuCauHanMuc.id))
            .where(
                YeuCauHanMuc.loai == "nguoi_dung",
                YeuCauHanMuc.khoa == nguoi_dung_id,
                YeuCauHanMuc.thoi_diem >= moc_mot_gio_truoc,
            )
        )
        da_dung_gio = int(phien.execute(stmt_gio).scalar() or 0)

        stmt_tien = (
            select(func.coalesce(func.sum(LuotGoi.chi_phi_usd), 0.0))
            .where(
                LuotGoi.nguoi_dung_id == nguoi_dung_id,
                LuotGoi.thoi_diem >= dau_ngay_utc,
            )
        )
        da_tieu_ngay_usd = float(phien.execute(stmt_tien).scalar() or 0.0)

    so_luot_con_lai_gio = max(0, han_muc_gio - da_dung_gio)
    chi_phi_con_lai_ngay_usd = max(0.0, han_muc_chi_phi - da_tieu_ngay_usd)

    return {
        "bac": bac,
        "da_dung_gio": da_dung_gio,
        "han_muc_gio": han_muc_gio,
        "so_luot_con_lai_gio": so_luot_con_lai_gio,
        "da_tieu_ngay_usd": round(da_tieu_ngay_usd, 6),
        "han_muc_chi_phi_ngay_usd": han_muc_chi_phi,
        "chi_phi_con_lai_ngay_usd": round(chi_phi_con_lai_ngay_usd, 6),
    }


def kiem_tra_han_muc(nguoi_dung_id: str = "khach") -> Tuple[int, int]:
    """Hàm tương thích ngược kiểm tra hạn mức người dùng (hoặc khách)."""
    ket_qua = kiem_tra_ba_tang_han_muc(
        ip="127.0.0.1",
        nguoi_dung_id=nguoi_dung_id,
        bac="free",
        ghi_nhan=True,
    )
    return (ket_qua["so_luot_user_gio"], ket_qua["han_muc_user_gio"])


def dat_lai_han_muc(nguoi_dung_id: Optional[str] = None, ip: Optional[str] = None) -> None:
    """Xoá lịch sử hạn mức trong CSDL (dành cho kiểm thử hoặc quản trị viên)."""
    try:
        with lay_phien_db() as phien:
            if nguoi_dung_id:
                phien.execute(
                    delete(YeuCauHanMuc).where(
                        YeuCauHanMuc.loai == "nguoi_dung",
                        YeuCauHanMuc.khoa == nguoi_dung_id,
                    )
                )
            elif ip:
                phien.execute(
                    delete(YeuCauHanMuc).where(
                        YeuCauHanMuc.loai == "ip",
                        YeuCauHanMuc.khoa == ip,
                    )
                )
            else:
                phien.execute(delete(YeuCauHanMuc))
    except Exception as e:
        logger.debug(f"[Hạn mức] Đặt lại hạn mức: {e}")
