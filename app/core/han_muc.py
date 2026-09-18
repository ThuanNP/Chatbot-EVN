"""Kiểm soát hạn mức người dùng và tần suất yêu cầu cho Chatbot EVN.

Quản lý hạn mức yêu cầu theo người dùng (hoặc khách) trong khung thời gian trượt 1 giờ.
Nếu vượt quá số lượt quy định (HAN_MUC_MOI_NGUOI_GIO), từ chối với HTTP 429.
"""

from datetime import datetime, timezone
import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from app.config import lay_cau_hinh

logger = logging.getLogger(__name__)

# Bảng lưu trữ mốc thời gian các lượt yêu cầu theo người dùng trong bộ nhớ
_lich_su_yeu_cau: Dict[str, List[float]] = {}
_khoa_han_muc = threading.Lock()


class VuotHanMucError(Exception):
    """Ngoại lệ khi người dùng vượt quá số lượt yêu cầu cho phép trong 1 giờ."""

    def __init__(
        self,
        thong_diep: str,
        so_luot_hien_tai: int = 0,
        han_muc_gio: int = 60,
    ):
        self.so_luot_hien_tai = so_luot_hien_tai
        self.han_muc_gio = han_muc_gio
        self.status_code = 429
        super().__init__(thong_diep)


def kiem_tra_han_muc(nguoi_dung_id: str = "khach") -> Tuple[int, int]:
    """Kiểm tra và ghi nhận một lượt yêu cầu của người dùng trong khung thời gian 1 giờ.

    Args:
        nguoi_dung_id: Định danh người dùng (mặc định 'khach')

    Returns:
        Tuple[int, int]: (số lượt hiện tại trong giờ, hạn mức tối đa mỗi giờ)

    Raises:
        VuotHanMucError: Khi số lượt yêu cầu đạt hoặc vượt quá hạn mức cho phép.
    """
    cau_hinh = lay_cau_hinh()
    han_muc_gio = int(cau_hinh.env.HAN_MUC_MOI_NGUOI_GIO)
    thoi_diem_hien_tai = time.time()
    moc_mot_gio_truoc = thoi_diem_hien_tai - 3600.0

    with _khoa_han_muc:
        # Lấy hoặc khởi tạo danh sách mốc thời gian của người dùng
        danh_sach = _lich_su_yeu_cau.get(nguoi_dung_id, [])

        # Dọn dẹp các yêu cầu cũ hơn 1 giờ trước
        danh_sach_moi = [t for t in danh_sach if t >= moc_mot_gio_truoc]

        # Kiểm tra vượt hạn mức
        if len(danh_sach_moi) >= han_muc_gio:
            thong_diep = (
                f"Bạn đã vượt quá giới hạn tối đa {han_muc_gio} lượt yêu cầu trong 1 giờ. "
                f"Vui lòng thử lại sau."
            )
            logger.warning(
                f"[Hạn mức] Người dùng '{nguoi_dung_id}' vượt hạn mức: "
                f"{len(danh_sach_moi)}/{han_muc_gio} lượt trong 1 giờ."
            )
            _lich_su_yeu_cau[nguoi_dung_id] = danh_sach_moi
            raise VuotHanMucError(
                thong_diep=thong_diep,
                so_luot_hien_tai=len(danh_sach_moi),
                han_muc_gio=han_muc_gio,
            )

        # Ghi nhận thời điểm yêu cầu mới
        danh_sach_moi.append(thoi_diem_hien_tai)
        _lich_su_yeu_cau[nguoi_dung_id] = danh_sach_moi
        so_luot_hien_tai = len(danh_sach_moi)

    return (so_luot_hien_tai, han_muc_gio)


def dat_lai_han_muc(nguoi_dung_id: Optional[str] = None) -> None:
    """Xoá lịch sử hạn mức (dành cho kiểm thử hoặc quản trị viên reset)."""
    with _khoa_han_muc:
        if nguoi_dung_id:
            _lich_su_yeu_cau.pop(nguoi_dung_id, None)
        else:
            _lich_su_yeu_cau.clear()
