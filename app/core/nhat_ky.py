"""Hệ thống nhật ký có cấu trúc và mã truy vết cho toàn bộ ứng dụng Chatbot EVN.

Tuân thủ nghiêm ngặt các quy tắc:
1. Sinh mã yêu cầu (ma_yeu_cau) 12 ký tự hex ngẫu nhiên, lưu trong contextvars,
   hỗ trợ lấy từ header X-Ma-Yeu-Cau hoặc X-Request-ID để nối chuỗi truy vết.
2. Định dạng JSON một dòng (JSON single-line), các trường cố định:
   thoi_diem, muc, ma_yeu_cau, nguoi_dung_id, chang, thong_diep, do_tre_ms.
3. Đúng sáu chặng chuẩn:
   http_vao, kiem_tra_han_muc, dung_ngu_canh, goi_mo_hinh, luu_hoi_thoai, http_ra.
   Riêng chặng goi_mo_hinh ghi thêm: tang, model, token_vao, token_ra,
   chi_phi_usd, so_lan_thu, danh_sach_tang_da_hong.
4. QUAN TRỌNG: Tuyệt đối không ghi nội dung tin nhắn người dùng vào nhật ký khi
   cờ GHI_NOI_DUNG tắt (mặc định tắt). Chỉ ghi độ dài và số token.
   Chỉ cho phép bật GHI_NOI_DUNG=true trong môi trường phát triển (development).
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
import secrets
import sys
from typing import Any, Dict, List, Optional

# Biến ngữ cảnh lưu mã yêu cầu (12 ký tự) và định danh người dùng
var_ma_yeu_cau: ContextVar[str] = ContextVar("ma_yeu_cau", default="")
var_nguoi_dung_id: ContextVar[str] = ContextVar("nguoi_dung_id", default="khach")

# Sáu chặng chuẩn theo đặc tả hệ thống
SAU_CHANG_CHUAN = {
    "http_vao",
    "kiem_tra_han_muc",
    "dung_ngu_canh",
    "goi_mo_hinh",
    "luu_hoi_thoai",
    "http_ra",
}

# Các trường nhạy cảm cần lọc nếu cờ GHI_NOI_DUNG tắt
TRUONG_NHAY_CAM = {
    "tin_nhan",
    "noi_dung",
    "prompt",
    "messages",
    "cau_tra_loi",
    "content",
    "user_message",
}


def sinh_ma_yeu_cau() -> str:
    """Sinh mã định danh yêu cầu duy nhất gồm đúng 12 ký tự hex (6 bytes)."""
    return secrets.token_hex(6)


def lay_ma_yeu_cau_hien_tai() -> str:
    """Lấy mã yêu cầu từ contextvar hiện tại, nếu chưa có thì sinh mới 12 ký tự."""
    ma = var_ma_yeu_cau.get()
    if not ma:
        ma = sinh_ma_yeu_cau()
        var_ma_yeu_cau.set(ma)
    return ma


def dat_ma_yeu_cau(ma: str) -> None:
    """Thiết lập mã yêu cầu vào contextvar của luồng xử lý hiện tại."""
    var_ma_yeu_cau.set(ma)


def lay_nguoi_dung_id_hien_tai() -> str:
    """Lấy định danh người dùng từ contextvar hiện tại (mặc định 'khach')."""
    return var_nguoi_dung_id.get() or "khach"


def dat_nguoi_dung_id(nguoi_dung_id: str) -> None:
    """Thiết lập định danh người dùng vào contextvar của luồng xử lý hiện tại."""
    var_nguoi_dung_id.set(nguoi_dung_id or "khach")


def duoc_phep_ghi_noi_dung() -> bool:
    """Kiểm tra cờ môi trường GHI_NOI_DUNG có được bật hay không.

    Mặc định TẮT (False).
    CẢNH BÁO: Chỉ bật cờ GHI_NOI_DUNG=true trong môi trường phát triển (development)
    để phục vụ gỡ lỗi nội dung prompt/response.
    Tuyệt đối KHÔNG bật trên môi trường staging hoặc production để tránh rò rỉ dữ liệu.
    """
    val = os.getenv("GHI_NOI_DUNG")
    gia_tri = (val if val is not None else "false").strip().lower()
    return gia_tri in ("true", "1", "yes")


def loc_truong_nhay_cam(du_lieu: Dict[str, Any]) -> Dict[str, Any]:
    """Loại bỏ hoặc che nội dung văn bản nhạy cảm nếu cờ GHI_NOI_DUNG không bật."""
    if duoc_phep_ghi_noi_dung():
        return du_lieu

    ket_qua: Dict[str, Any] = {}
    for khoa, gia_tri in du_lieu.items():
        if khoa in TRUONG_NHAY_CAM:
            if isinstance(gia_tri, str):
                ket_qua[f"do_dai_{khoa}"] = len(gia_tri)
            elif isinstance(gia_tri, list):
                ket_qua[f"so_luong_{khoa}"] = len(gia_tri)
            else:
                ket_qua[f"co_{khoa}"] = True
        else:
            ket_qua[khoa] = gia_tri
    return ket_qua


class DinhDangNhatKyJson(logging.Formatter):
    """Bộ định dạng nhật ký JSON một dòng dùng chung cho toàn bộ ứng dụng.

    Đảm bảo:
    - 7 trường cố định: thoi_diem, muc, ma_yeu_cau, nguoi_dung_id, chang, thong_diep, do_tre_ms.
    - Chặng 'goi_mo_hinh' có thêm: tang, model, token_vao, token_ra, chi_phi_usd, so_lan_thu, danh_sach_tang_da_hong.
    - Không lộ nội dung tin nhắn nếu GHI_NOI_DUNG=false.
    - Ghi nhận đầy đủ vết lỗi (vet_loi) nếu có ngoại lệ.
    """

    def format(self, record: logging.LogRecord) -> str:
        # 1. Trích xuất thời điểm UTC định dạng ISO 8601
        thoi_diem = datetime.now(timezone.utc).isoformat()

        # 2. Xác định mã yêu cầu và người dùng từ record hoặc ContextVar
        ma_yeu_cau = getattr(record, "ma_yeu_cau", None) or lay_ma_yeu_cau_hien_tai()
        nguoi_dung_id = getattr(record, "nguoi_dung_id", None) or lay_nguoi_dung_id_hien_tai()

        # 3. Xác định chặng và thông điệp
        chang = getattr(record, "chang", "he_thong")
        thong_diep = record.getMessage()

        # 4. Xác định độ trễ
        raw_do_tre = getattr(record, "do_tre_ms", 0.0)
        try:
            do_tre_ms = round(float(raw_do_tre), 2)
        except (ValueError, TypeError):
            do_tre_ms = 0.0

        # Cấu trúc 7 trường cố định bắt buộc
        ban_ghi: Dict[str, Any] = {
            "thoi_diem": thoi_diem,
            "muc": record.levelname,
            "ma_yeu_cau": ma_yeu_cau,
            "nguoi_dung_id": nguoi_dung_id,
            "chang": chang,
            "thong_diep": thong_diep,
            "do_tre_ms": do_tre_ms,
        }

        # 5. Bổ sung các trường chuyên biệt cho chặng goi_mo_hinh
        if chang == "goi_mo_hinh":
            ban_ghi["tang"] = getattr(record, "tang", None)
            ban_ghi["model"] = getattr(record, "model", "")
            ban_ghi["token_vao"] = int(getattr(record, "token_vao", 0) or 0)
            ban_ghi["token_ra"] = int(getattr(record, "token_ra", 0) or 0)
            ban_ghi["chi_phi_usd"] = float(getattr(record, "chi_phi_usd", 0.0) or 0.0)
            ban_ghi["so_lan_thu"] = int(getattr(record, "so_lan_thu", 1) or 1)
            ban_ghi["danh_sach_tang_da_hong"] = getattr(record, "danh_sach_tang_da_hong", [])

        # 6. Bổ sung vết lỗi nếu có ngoại lệ (phục vụ bộ phận kỹ thuật xem log)
        if record.exc_info:
            ban_ghi["vet_loi"] = self.formatException(record.exc_info)
        elif hasattr(record, "vet_loi") and record.vet_loi:
            ban_ghi["vet_loi"] = str(record.vet_loi)

        # 7. Thu thập các trường phụ khác được truyền qua extra
        cac_thuoc_tinh_he_thong = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "module", "msecs",
            "msg", "name", "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName", "taskName", "thoi_diem",
            "muc", "ma_yeu_cau", "nguoi_dung_id", "chang", "thong_diep", "do_tre_ms",
            "tang", "model", "token_vao", "token_ra", "chi_phi_usd", "so_lan_thu",
            "danh_sach_tang_da_hong", "vet_loi",
        }

        du_lieu_phu: Dict[str, Any] = {}
        for k, v in record.__dict__.items():
            if k not in cac_thuoc_tinh_he_thong and not k.startswith("_"):
                du_lieu_phu[k] = v

        # Lọc bảo mật các trường phụ nếu GHI_NOI_DUNG=false
        du_lieu_phu_an_toan = loc_truong_nhay_cam(du_lieu_phu)
        ban_ghi.update(du_lieu_phu_an_toan)

        # Trả về JSON một dòng duy nhất (single line JSON)
        return json.dumps(ban_ghi, ensure_ascii=False)


# Logger chính thức của module nhật ký
logger_nhat_ky = logging.getLogger("chatbot_evn.nhat_ky")


def ghi_nhat_ky(
    chang: str,
    thong_diep: str,
    do_tre_ms: float = 0.0,
    muc: str = "INFO",
    ma_yeu_cau: Optional[str] = None,
    nguoi_dung_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """Ghi nhật ký có cấu trúc cho một sự kiện hoặc chặng trong hệ thống.

    Tham số:
        chang: Tên chặng (ví dụ: http_vao, kiem_tra_han_muc, dung_ngu_canh, goi_mo_hinh, luu_hoi_thoai, http_ra).
        thong_diep: Tóm tắt nội dung hành động hoặc kết quả chặng.
        do_tre_ms: Độ trễ thực thi (mili-giây).
        muc: Mức ghi log ('INFO', 'WARNING', 'ERROR', 'DEBUG').
        ma_yeu_cau: Mã yêu cầu (nếu None sẽ lấy tự động từ contextvars).
        nguoi_dung_id: ID người dùng (nếu None sẽ lấy từ contextvars).
        **extra: Các trường bổ sung cần ghi kèm vào JSON log.
    """
    level = getattr(logging, muc.upper(), logging.INFO)
    extra_payload = dict(extra)
    extra_payload["chang"] = chang
    extra_payload["do_tre_ms"] = do_tre_ms
    if ma_yeu_cau:
        extra_payload["ma_yeu_cau"] = ma_yeu_cau
    if nguoi_dung_id:
        extra_payload["nguoi_dung_id"] = nguoi_dung_id

    # Lọc bảo mật các trường nhạy cảm trong extra
    extra_an_toan = loc_truong_nhay_cam(extra_payload)
    logger_nhat_ky.log(level, thong_diep, extra=extra_an_toan)


# ---------------------------------------------------------------------------
# Các hàm trợ giúp ghi nhận đúng 6 chặng chuẩn
# ---------------------------------------------------------------------------
def ghi_http_vao(phuong_thuc: str, duong_dan: str, do_tre_ms: float = 0.0, **extra: Any) -> None:
    """Chặng 1: Ghi nhận yêu cầu HTTP vừa đi vào hệ thống."""
    thong_diep = f"Bắt đầu tiếp nhận yêu cầu HTTP {phuong_thuc} {duong_dan}"
    ghi_nhat_ky(chang="http_vao", thong_diep=thong_diep, do_tre_ms=do_tre_ms, muc="INFO", **extra)


def ghi_kiem_tra_han_muc(nguoi_dung_id: str, bac: str, do_tre_ms: float = 0.0, **extra: Any) -> None:
    """Chặng 2: Ghi nhận kiểm tra ba tầng hạn mức và ngân sách thành công."""
    thong_diep = f"Kiểm tra hạn mức thành công: người dùng '{nguoi_dung_id}', bậc '{bac}'"
    ghi_nhat_ky(chang="kiem_tra_han_muc", thong_diep=thong_diep, do_tre_ms=do_tre_ms, muc="INFO", **extra)


def ghi_dung_ngu_canh(
    so_luong_tin_nhan: int,
    do_dai_tin_nhan_moi: int,
    tong_token_uoc_tinh: int = 0,
    do_tre_ms: float = 0.0,
    **extra: Any,
) -> None:
    """Chặng 3: Ghi nhận dựng ngữ cảnh hội thoại hoàn tất (chỉ ghi độ dài và token, CẤM ghi nội dung)."""
    thong_diep = (
        f"Dựng ngữ cảnh hoàn tất: {so_luong_tin_nhan} tin nhắn lịch sử, "
        f"tin nhắn mới {do_dai_tin_nhan_moi} ký tự, "
        f"ước tính {tong_token_uoc_tinh} token"
    )
    ghi_nhat_ky(
        chang="dung_ngu_canh",
        thong_diep=thong_diep,
        do_tre_ms=do_tre_ms,
        muc="INFO",
        so_luong_tin_nhan=so_luong_tin_nhan,
        do_dai_tin_nhan=do_dai_tin_nhan_moi,
        tong_token_uoc_tinh=tong_token_uoc_tinh,
        **extra,
    )


def ghi_goi_mo_hinh(
    tang: int,
    model: str,
    token_vao: int,
    token_ra: int,
    chi_phi_usd: float,
    so_lan_thu: int,
    danh_sach_tang_da_hong: Optional[List[Dict[str, Any]]] = None,
    do_tre_ms: float = 0.0,
    **extra: Any,
) -> None:
    """Chặng 4: Ghi nhận gọi mô hình thành công với đầy đủ 7 trường mở rộng bắt buộc."""
    thong_diep = (
        f"Gọi mô hình thành công từ tầng {tang} ({model}): "
        f"token_vao={token_vao}, token_ra={token_ra}, "
        f"chi_phi_usd=${chi_phi_usd:.6f}, so_lan_thu={so_lan_thu}"
    )
    ghi_nhat_ky(
        chang="goi_mo_hinh",
        thong_diep=thong_diep,
        do_tre_ms=do_tre_ms,
        muc="INFO",
        tang=tang,
        model=model,
        token_vao=token_vao,
        token_ra=token_ra,
        chi_phi_usd=chi_phi_usd,
        so_lan_thu=so_lan_thu,
        danh_sach_tang_da_hong=danh_sach_tang_da_hong or [],
        **extra,
    )


def ghi_luu_hoi_thoai(hoi_thoai_id: str, do_tre_ms: float = 0.0, **extra: Any) -> None:
    """Chặng 5: Ghi nhận lưu tin nhắn và cập nhật hội thoại vào cơ sở dữ liệu."""
    thong_diep = f"Lưu tin nhắn vào cơ sở dữ liệu thành công cho phiên '{hoi_thoai_id}'"
    ghi_nhat_ky(
        chang="luu_hoi_thoai",
        thong_diep=thong_diep,
        do_tre_ms=do_tre_ms,
        muc="INFO",
        hoi_thoai_id=hoi_thoai_id,
        **extra,
    )


def ghi_http_ra(
    phuong_thuc: str,
    duong_dan: str,
    ma_trang_thai: int,
    do_tre_ms: float = 0.0,
    **extra: Any,
) -> None:
    """Chặng 6: Ghi nhận hoàn tất xử lý và trả lời HTTP ra ngoài."""
    thong_diep = f"Hoàn tất yêu cầu HTTP {phuong_thuc} {duong_dan} - Mã {ma_trang_thai}"
    muc = "INFO" if ma_trang_thai < 400 else ("WARNING" if ma_trang_thai < 500 else "ERROR")
    ghi_nhat_ky(
        chang="http_ra",
        thong_diep=thong_diep,
        do_tre_ms=do_tre_ms,
        muc=muc,
        ma_trang_thai=ma_trang_thai,
        **extra,
    )


def thiet_lap_nhat_ky(muc_log: str = "INFO") -> None:
    """Cấu hình định dạng JSON một dòng thống nhất cho toàn bộ hệ thống logging.

    Áp dụng DinhDangNhatKyJson cho root logger và các logger con.
    """
    root_logger = logging.getLogger()
    level = getattr(logging, muc_log.upper(), logging.INFO)
    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(DinhDangNhatKyJson())

    # Thay thế các handlers hiện tại bằng JSON handler duy nhất
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Đảm bảo logger con kế thừa handler
    logger_nhat_ky.setLevel(level)
