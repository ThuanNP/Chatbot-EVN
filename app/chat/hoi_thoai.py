"""Quản lý các phiên hội thoại và tin nhắn của người dùng trong Chatbot EVN.

Cung cấp các hàm nghiệp vụ truy xuất và lưu trữ phiên hội thoại (bảng hoi_thoai)
và tin nhắn (bảng tin_nhan), kèm cơ chế tự động đặt tiêu đề nền sau lượt trả lời đầu tiên.
Tuân thủ nghiêm ngặt các quy tắc bất biến trong AGENTS.md.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import List, Optional

from sqlalchemy import desc, func, select

from app.core.database import HoiThoai, TinNhan, lay_phien_db
from app.llm.router import goi_mo_hinh

logger = logging.getLogger(__name__)


def tao_hoi_thoai(
    nguoi_dung_id: str = "khach",
    tieu_de: Optional[str] = None,
) -> HoiThoai:
    """Tạo mới một phiên hội thoại cho người dùng.

    Args:
        nguoi_dung_id: Định danh người dùng (mặc định 'khach')
        tieu_de: Tiêu đề hội thoại ban đầu (mặc định 'Cuộc trò chuyện mới')

    Returns:
        HoiThoai: Phiên hội thoại vừa được khởi tạo và lưu vào cơ sở dữ liệu
    """
    tieu_de_mac_dinh = tieu_de or "Cuộc trò chuyện mới"
    with lay_phien_db() as phien:
        hoi_thoai = HoiThoai(
            nguoi_dung_id=nguoi_dung_id,
            tieu_de=tieu_de_mac_dinh,
        )
        phien.add(hoi_thoai)
        phien.flush()
        # Nạp dữ liệu vào phiên trước khi commit và đóng context manager
        phien.refresh(hoi_thoai)
        # Giữ lại các thuộc tính độc lập để trả về an toàn ngoài session
        phien.expunge(hoi_thoai)
        return hoi_thoai


def lay_hoi_thoai(hoi_thoai_id: str) -> Optional[HoiThoai]:
    """Truy vấn thông tin chi tiết của một phiên hội thoại theo mã định danh.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại (UUID)

    Returns:
        Optional[HoiThoai]: Đối tượng hội thoại nếu tìm thấy, ngược lại trả về None
    """
    with lay_phien_db() as phien:
        hoi_thoai = phien.get(HoiThoai, hoi_thoai_id)
        if hoi_thoai:
            phien.expunge(hoi_thoai)
        return hoi_thoai


def danh_sach_hoi_thoai(
    nguoi_dung_id: str = "khach",
    gioi_han: int = 50,
    bo_qua: int = 0,
) -> List[HoiThoai]:
    """Lấy danh sách các phiên hội thoại của người dùng, sắp xếp mới nhất lên đầu.

    Tận dụng chỉ mục ix_hoi_thoai_nguoi_dung_cap_nhat để tăng tốc truy vấn.

    Args:
        nguoi_dung_id: Định danh người dùng
        gioi_han: Số lượng hội thoại tối đa cần lấy
        bo_qua: Số lượng bản ghi bỏ qua (hỗ trợ phân trang)

    Returns:
        List[HoiThoai]: Danh sách các phiên hội thoại sắp xếp theo thời điểm cập nhật giảm dần
    """
    with lay_phien_db() as phien:
        cau_lenh = (
            select(HoiThoai)
            .where(HoiThoai.nguoi_dung_id == nguoi_dung_id)
            .order_by(desc(HoiThoai.cap_nhat_luc))
            .offset(bo_qua)
            .limit(gioi_han)
        )
        ket_qua = phien.execute(cau_lenh).scalars().all()
        danh_sach = list(ket_qua)
        for ht in danh_sach:
            phien.expunge(ht)
        return danh_sach


def xoa_hoi_thoai(hoi_thoai_id: str) -> bool:
    """Xoá một phiên hội thoại khỏi cơ sở dữ liệu.

    Toàn bộ tin nhắn liên quan sẽ tự động bị xoá nhờ ràng buộc ON DELETE CASCADE.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại cần xoá

    Returns:
        bool: True nếu tìm thấy và xoá thành công, False nếu phiên không tồn tại
    """
    with lay_phien_db() as phien:
        hoi_thoai = phien.get(HoiThoai, hoi_thoai_id)
        if not hoi_thoai:
            return False
        phien.delete(hoi_thoai)
        return True


def doi_tieu_de_hoi_thoai(hoi_thoai_id: str, tieu_de_moi: str) -> bool:
    """Cập nhật tiêu đề hiển thị cho phiên hội thoại.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại
        tieu_de_moi: Nội dung tiêu đề mới

    Returns:
        bool: True nếu cập nhật thành công, False nếu phiên không tồn tại
    """
    with lay_phien_db() as phien:
        hoi_thoai = phien.get(HoiThoai, hoi_thoai_id)
        if not hoi_thoai:
            return False
        hoi_thoai.tieu_de = tieu_de_moi
        hoi_thoai.cap_nhat_luc = datetime.now(timezone.utc)
        return True


def dem_so_tin_nhan(hoi_thoai_id: str) -> int:
    """Đếm tổng số lượng tin nhắn hiện có trong một phiên hội thoại.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại

    Returns:
        int: Tổng số tin nhắn
    """
    with lay_phien_db() as phien:
        cau_lenh = (
            select(func.count(TinNhan.id))
            .where(TinNhan.hoi_thoai_id == hoi_thoai_id)
        )
        tong = phien.execute(cau_lenh).scalar()
        return int(tong or 0)


def lay_tin_nhan_hoi_thoai(
    hoi_thoai_id: str,
    gioi_han: Optional[int] = None,
) -> List[TinNhan]:
    """Lấy danh sách tin nhắn của phiên hội thoại theo thứ tự thời gian tăng dần.

    Tận dụng chỉ mục ix_tin_nhan_hoi_thoai_tao_luc.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại
        gioi_han: Số lượng tin nhắn tối đa cần lấy (None = lấy tất cả)

    Returns:
        List[TinNhan]: Danh sách tin nhắn sắp xếp từ cũ đến mới
    """
    with lay_phien_db() as phien:
        cau_lenh = (
            select(TinNhan)
            .where(TinNhan.hoi_thoai_id == hoi_thoai_id)
            .order_by(TinNhan.tao_luc.asc())
        )
        if gioi_han:
            cau_lenh = cau_lenh.limit(gioi_han)
        ket_qua = phien.execute(cau_lenh).scalars().all()
        danh_sach = list(ket_qua)
        for tn in danh_sach:
            phien.expunge(tn)
        return danh_sach


def luu_tin_nhan(
    hoi_thoai_id: str,
    vai_tro: str,
    noi_dung: str,
    tang_phuc_vu: Optional[int] = None,
    token_uoc_tinh: Optional[int] = None,
) -> TinNhan:
    """Lưu một tin nhắn mới vào phiên hội thoại và cập nhật thời điểm sửa đổi.

    Nếu là lượt trả lời ĐẦU TIÊN (sau khi lưu tin nhắn assistant đầu tiên),
    hàm sẽ tự động kích hoạt tác vụ nền để sinh tiêu đề mà không chặn luồng chính.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại
        vai_tro: Vai trò tin nhắn ('user' hoặc 'assistant')
        noi_dung: Nội dung văn bản của tin nhắn
        tang_phuc_vu: Tầng mô hình đã phục vụ (cho phép rỗng)
        token_uoc_tinh: Số lượng token ước tính (tự động tính nếu không truyền)

    Returns:
        TinNhan: Bản ghi tin nhắn đã được lưu

    Raises:
        ValueError: Nếu vai_tro không thuộc tập hợp ('user', 'assistant')
    """
    if vai_tro not in ("user", "assistant"):
        raise ValueError("vai_tro chỉ được phép nhận giá trị 'user' hoặc 'assistant'")

    # Tính toán xấp xỉ token nếu chưa có sẵn
    if token_uoc_tinh is None:
        from app.chat.ngu_canh import uoc_tinh_token
        token_uoc_tinh = uoc_tinh_token(noi_dung)

    with lay_phien_db() as phien:
        hoi_thoai = phien.get(HoiThoai, hoi_thoai_id)
        if not hoi_thoai:
            raise ValueError(f"Không tìm thấy phiên hội thoại với id={hoi_thoai_id}")

        tin_nhan = TinNhan(
            hoi_thoai_id=hoi_thoai_id,
            vai_tro=vai_tro,
            noi_dung=noi_dung,
            token_uoc_tinh=token_uoc_tinh,
            tang_phuc_vu=tang_phuc_vu,
        )
        phien.add(tin_nhan)

        # Cập nhật thời điểm sửa đổi của phiên hội thoại
        hoi_thoai.cap_nhat_luc = datetime.now(timezone.utc)
        phien.flush()
        phien.refresh(tin_nhan)
        phien.expunge(tin_nhan)

    # Kiểm tra kích hoạt tự động đặt tiêu đề nền:
    # Điều kiện: Sau lượt trả lời ĐẦU TIÊN (khi lưu tin nhắn assistant đầu tiên,
    # cuộc hội thoại có đúng 2 tin nhắn: 1 user và 1 assistant).
    if vai_tro == "assistant":
        tong_tin_nhan = dem_so_tin_nhan(hoi_thoai_id)
        if tong_tin_nhan == 2:
            danh_sach = lay_tin_nhan_hoi_thoai(hoi_thoai_id)
            if len(danh_sach) == 2 and danh_sach[0].vai_tro == "user":
                cau_hoi_dau = danh_sach[0].noi_dung
                cau_tra_loi_dau = noi_dung
                kich_hoat_tu_dong_dat_tieu_de(
                    hoi_thoai_id=hoi_thoai_id,
                    cau_hoi=cau_hoi_dau,
                    cau_tra_loi=cau_tra_loi_dau,
                )

    return tin_nhan


async def tu_dong_dat_tieu_de_nen(
    hoi_thoai_id: str,
    cau_hoi: str,
    cau_tra_loi: str,
) -> Optional[str]:
    """Tác vụ nền gọi mô hình với lời nhắc rất ngắn để sinh tiêu đề tối đa 8 từ.

    Quy tắc AGENTS.md:
    - Đi qua duy nhất hàm goi_mo_hinh trong app/llm/router.py.
    - Không ghi cứng tên model trong mã Python.
    - Chạy nền độc lập, bắt toàn bộ ngoại lệ để không bao giờ ảnh hưởng tới luồng chính.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại
        cau_hoi: Câu hỏi đầu tiên của người dùng
        cau_tra_loi: Câu trả lời đầu tiên của trợ lý

    Returns:
        Optional[str]: Tiêu đề đã được cập nhật, hoặc None nếu có sự cố
    """
    logger.info(f"Bắt đầu tác vụ nền sinh tiêu đề cho phiên hội thoại: {hoi_thoai_id}")
    try:
        # Lời nhắc rất ngắn gọn yêu cầu tiêu đề tối đa 8 từ
        tin_nhan_loi_nhac = [
            {
                "role": "system",
                "content": (
                    "Bạn là chuyên gia tóm tắt. Hãy đặt một tiêu đề ngắn gọn (tối đa 8 từ), "
                    "không có dấu ngoặc kép, không có từ thừa mở đầu, tóm tắt chủ đề chính "
                    "của cuộc trao đổi sau."
                ),
            },
            {
                "role": "user",
                "content": f"Hỏi: {cau_hoi[:300]}\nĐáp: {cau_tra_loi[:300]}",
            },
        ]

        # Gọi mô hình thông qua router duy nhất (không stream, giới hạn token nhỏ)
        ket_qua = await goi_mo_hinh(
            tin_nhan=tin_nhan_loi_nhac,
            phat_theo_dong=False,
            max_tokens=30,
            temperature=0.3,
        )

        tieu_de_raw = ket_qua.noi_dung.strip().strip('"\'“”`')
        # Lấy dòng đầu tiên nếu mô hình sinh xuống dòng
        tieu_de_dong_dau = tieu_de_raw.split("\n")[0].strip()

        # Cắt tối đa 8 từ nếu kết quả dài hơn quy định
        cac_tu = tieu_de_dong_dau.split()
        if len(cac_tu) > 8:
            tieu_de_chuan = " ".join(cac_tu[:8])
        else:
            tieu_de_chuan = tieu_de_dong_dau

        if tieu_de_chuan:
            doi_tieu_de_hoi_thoai(hoi_thoai_id, tieu_de_chuan)
            logger.info(
                f"Đã tự động cập nhật tiêu đề cho phiên {hoi_thoai_id}: '{tieu_de_chuan}'"
            )
            return tieu_de_chuan

    except Exception as e:
        logger.warning(
            f"Không thể tự động đặt tiêu đề nền cho phiên {hoi_thoai_id}: {e}"
        )
    return None


def kich_hoat_tu_dong_dat_tieu_de(
    hoi_thoai_id: str,
    cau_hoi: str,
    cau_tra_loi: str,
) -> Optional[asyncio.Task]:
    """Kích hoạt tác vụ nền đặt tiêu đề mà không chặn luồng phản hồi cho người dùng.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại
        cau_hoi: Câu hỏi đầu tiên của người dùng
        cau_tra_loi: Câu trả lời đầu tiên của trợ lý

    Returns:
        Optional[asyncio.Task]: Tác vụ nền nếu event loop đang chạy, hoặc None
    """
    try:
        loop = asyncio.get_running_loop()
        return loop.create_task(
            tu_dong_dat_tieu_de_nen(
                hoi_thoai_id=hoi_thoai_id,
                cau_hoi=cau_hoi,
                cau_tra_loi=cau_tra_loi,
            )
        )
    except RuntimeError:
        # Khi chạy ngoài luồng async (ví dụ gọi từ script đồng bộ thuần túy)
        logger.debug(
            "Không có running asyncio event loop, bỏ qua đặt tiêu đề nền tự động."
        )
        return None
