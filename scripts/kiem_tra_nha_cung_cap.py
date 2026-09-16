"""Kịch bản kiểm tra kết nối và tính khả dụng của các nhà cung cấp mô hình.

Kịch bản đọc cấu hình từ .env và config/models.yaml, sau đó gửi một truy vấn ngắn
đến từng tầng trong chuỗi dự phòng. Kết quả kiểm tra được xuất dưới dạng bảng:
Tầng, Model, Trạng thái (ĐẠT/HỎNG), Độ trễ (ms), Token vào, Token ra.

Nếu gặp lỗi tên model không hợp lệ, kịch bản sẽ in thông báo rõ ràng gợi ý
người dùng tra cứu danh mục mô hình chính thức và chỉnh sửa trong config/models.yaml.
"""

import os
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Bỏ qua các cảnh báo serializer nội bộ từ LiteLLM / Pydantic
warnings.filterwarnings("ignore")
os.environ["LITELLM_LOG"] = "ERROR"

# Đảm bảo đường dẫn gốc dự án nằm trong sys.path để import app.config
DUONG_DAN_GOC = Path(__file__).resolve().parent.parent
if str(DUONG_DAN_GOC) not in sys.path:
    sys.path.insert(0, str(DUONG_DAN_GOC))

from app.config import CauHinhTang, lay_cau_hinh

# Danh mục đường dẫn tài liệu tra cứu model chính thức của từng nhà cung cấp
TAI_LIEU_MODEL = {
    "gemini": "https://ai.google.dev/gemini-api/docs/models/gemini",
    "openrouter_auto": "https://openrouter.ai/models",
    "openrouter": "https://openrouter.ai/models",
    "claude": "https://docs.anthropic.com/en/docs/about-claude/models",
    "anthropic": "https://docs.anthropic.com/en/docs/about-claude/models",
    "openai": "https://platform.openai.com/docs/models",
}


@dataclass
class KetQuaKiemTra:
    """Lưu trữ kết quả kiểm tra cho từng tầng mô hình."""

    tang: int
    ten: str
    model: str
    api_key_env: str
    trang_thai: str  # "ĐẠT" hoặc "HỎNG"
    do_tre_ms: int
    token_vao: int
    token_ra: int
    loi_ten_model: bool = False
    thong_bao_loi: Optional[str] = None
    huong_dan_khac_phuc: Optional[str] = None


def kiem_tra_khoa_api_hop_le(khoa_api: str) -> bool:
    """Kiểm tra xem khoá API đã được điền thực tế hay vẫn là placeholder."""
    if not khoa_api or not khoa_api.strip():
        return False
    khoa_mau = ["dan-khoa-that-vao-day", "your-api-key", "placeholder", "xxx"]
    return khoa_api.strip().lower() not in khoa_mau


def kiem_tra_tang(tang_config: CauHinhTang, khoa_api: str) -> KetQuaKiemTra:
    """Gửi yêu cầu thử nghiệm tới một tầng mô hình cụ thể."""
    import litellm

    litellm.suppress_debug_info = True

    # 1. Kiểm tra khoá API trước khi gọi
    if not kiem_tra_khoa_api_hop_le(khoa_api):
        return KetQuaKiemTra(
            tang=tang_config.tang,
            ten=tang_config.ten,
            model=tang_config.model,
            api_key_env=tang_config.api_key_env,
            trang_thai="HỎNG",
            do_tre_ms=0,
            token_vao=0,
            token_ra=0,
            loi_ten_model=False,
            thong_bao_loi=f"Khoá API '{tang_config.api_key_env}' chưa được thiết lập trong tệp .env (vẫn giữ giá trị placeholder mặc định).",
            huong_dan_khac_phuc=f"Mở tệp .env và điền khoá API thật vào biến {tang_config.api_key_env}.",
        )

    # 2. Câu hỏi thử nghiệm ngắn gọn
    cau_hoi_thu = [{"role": "user", "content": "Xin chào! Hãy trả lời 'OK' đúng một từ."}]

    tham_so_goi: Dict[str, Any] = {
        "model": tang_config.model,
        "messages": cau_hoi_thu,
        "api_key": khoa_api,
        "timeout": tang_config.timeout_giay,
        "max_tokens": 128,
    }

    if tang_config.tham_so_them:
        tham_so_goi["extra_body"] = tang_config.tham_so_them

    thoi_gian_bat_dau = time.perf_counter()
    try:
        phan_hoi = litellm.completion(**tham_so_goi)
        thoi_gian_ket_thuc = time.perf_counter()
        do_tre_ms = int((thoi_gian_ket_thuc - thoi_gian_bat_dau) * 1000)

        token_vao = 0
        token_ra = 0
        if hasattr(phan_hoi, "usage") and phan_hoi.usage:
            token_vao = getattr(phan_hoi.usage, "prompt_tokens", 0) or 0
            token_ra = getattr(phan_hoi.usage, "completion_tokens", 0) or 0

        return KetQuaKiemTra(
            tang=tang_config.tang,
            ten=tang_config.ten,
            model=tang_config.model,
            api_key_env=tang_config.api_key_env,
            trang_thai="ĐẠT",
            do_tre_ms=do_tre_ms,
            token_vao=token_vao,
            token_ra=token_ra,
        )

    except Exception as e:
        thoi_gian_ket_thuc = time.perf_counter()
        do_tre_ms = int((thoi_gian_ket_thuc - thoi_gian_bat_dau) * 1000)
        chuoi_loi = str(e)
        chuoi_loi_thuong = chuoi_loi.lower()

        cac_dau_hieu_sai_model = [
            "not found",
            "not_found",
            "does not exist",
            "invalid model",
            "model_not_found",
            "unknown model",
            "no longer available",
            "404",
        ]
        loi_ten_model = any(dau_hieu in chuoi_loi_thuong for dau_hieu in cac_dau_hieu_sai_model)

        link_tai_lieu = TAI_LIEU_MODEL.get(tang_config.ten, "https://openrouter.ai/models")

        if loi_ten_model:
            huong_dan = (
                f"Tên model '{tang_config.model}' có thể đã cũ, không tồn tại hoặc không được hỗ trợ.\n"
                f"   1. Tra cứu danh mục model mới nhất tại: {link_tai_lieu}\n"
                f"   2. Mở config/models.yaml và cập nhật trường 'model' của tầng {tang_config.tang}."
            )
        elif "authentication" in chuoi_loi_thuong or "api key" in chuoi_loi_thuong or "401" in chuoi_loi_thuong:
            huong_dan = (
                f"Khoá API '{tang_config.api_key_env}' không hợp lệ hoặc đã bị vô hiệu hoá.\n"
                f"   Vui lòng kiểm tra lại giá trị khoá trong tệp .env."
            )
        elif "rate limit" in chuoi_loi_thuong or "quota" in chuoi_loi_thuong or "429" in chuoi_loi_thuong:
            huong_dan = (
                f"Tài khoản nhà cung cấp bị vượt hạn mức gọi hoặc hết số dư khả dụng (Rate limit / Quota).\n"
                f"   Vui lòng kiểm tra quota/billing trên bảng điều khiển của nhà cung cấp."
            )
        elif "timeout" in chuoi_loi_thuong:
            huong_dan = (
                f"Quá thời gian chờ phản hồi ({tang_config.timeout_giay}s).\n"
                f"   Vui lòng kiểm tra kết nối mạng hoặc tăng timeout_giay trong config/models.yaml."
            )
        else:
            huong_dan = f"Chi tiết lỗi: {chuoi_loi}"

        return KetQuaKiemTra(
            tang=tang_config.tang,
            ten=tang_config.ten,
            model=tang_config.model,
            api_key_env=tang_config.api_key_env,
            trang_thai="HỎNG",
            do_tre_ms=do_tre_ms,
            token_vao=0,
            token_ra=0,
            loi_ten_model=loi_ten_model,
            thong_bao_loi=chuoi_loi,
            huong_dan_khac_phuc=huong_dan,
        )


def in_bang_ket_qua(danh_sach_ket_qua: List[KetQuaKiemTra]) -> None:
    """In bảng kết quả kiểm định các tầng theo định dạng chuẩn."""
    ke_ngang = "+" + "-" * 6 + "+" + "-" * 18 + "+" + "-" * 38 + "+" + "-" * 11 + "+" + "-" * 13 + "+" + "-" * 11 + "+" + "-" * 11 + "+"
    tieu_de = (
        f"| {'Tầng':^4} | {'Tên':<16} | {'Model':<36} | {'Kết quả':^9} | {'Độ trễ (ms)':^11} | {'Token vào':^9} | {'Token ra':^9} |"
    )

    print("\n" + "=" * 116)
    print(f"{'KẾT QUẢ KIỂM TRA CÁC NHÀ CUNG CẤP MÔ HÌNH (CHUỖI DỰ PHÒNG)':^116}")
    print("=" * 116)
    print(ke_ngang)
    print(tieu_de)
    print(ke_ngang)

    for kq in danh_sach_ket_qua:
        ten_model_hien_thi = kq.model if len(kq.model) <= 36 else kq.model[:33] + "..."
        bieu_tuong = "[ ĐẠT ]" if kq.trang_thai == "ĐẠT" else "[ HỎNG ]"
        print(
            f"| {kq.tang:^4} | {kq.ten:<16} | {ten_model_hien_thi:<36} | {bieu_tuong:^9} | {kq.do_tre_ms:^11} | {kq.token_vao:^9} | {kq.token_ra:^9} |"
        )

    print(ke_ngang)

    co_tang_hong = any(kq.trang_thai == "HỎNG" for kq in danh_sach_ket_qua)
    if co_tang_hong:
        print("\n" + "!" * 116)
        print("CHI TIẾT VÀ GỢI Ý KHẮC PHỤC SỰ CỐ:")
        print("!" * 116)
        for kq in danh_sach_ket_qua:
            if kq.trang_thai == "HỎNG":
                print(f"\n-> [Tầng {kq.tang} - {kq.ten}] (Model: {kq.model} | Env: {kq.api_key_env})")
                if kq.loi_ten_model:
                    print("   [CẢNH BÁO LỖI TÊN MODEL]:")
                print(f"   Hướng dẫn: {kq.huong_dan_khac_phuc}")
                if kq.thong_bao_loi and not kq.loi_ten_model:
                    print(f"   Mô tả lỗi: {kq.thong_bao_loi[:200]}...")

    so_dat = sum(1 for kq in danh_sach_ket_qua if kq.trang_thai == "ĐẠT")
    tong_so = len(danh_sach_ket_qua)
    print("\n" + "-" * 116)
    print(f"TỔNG KẾT: {so_dat}/{tong_so} tầng hoạt động bình thường. ({tong_so - so_dat} tầng cần cấu hình thêm)")
    print("-" * 116 + "\n")


def chay_kiem_tra() -> int:
    """Hàm thực thi chính của kịch bản kiểm tra."""
    print("[*] Đang nạp cấu hình từ .env và config/models.yaml...")
    try:
        cau_hinh = lay_cau_hinh(nap_lai=True)
    except Exception as e:
        print(f"[X] LỖI NẠP CẤU HÌNH: {e}")
        print("    Vui lòng kiểm tra tệp .env và config/models.yaml!")
        return 1

    chuoi = cau_hinh.models.chuoi_du_phong
    print(f"[*] Tìm thấy {len(chuoi)} tầng trong chuỗi dự phòng. Bắt đầu kiểm tra từng tầng...")

    danh_sach_ket_qua: List[KetQuaKiemTra] = []

    for tang in chuoi:
        print(f"    -> Đang kiểm tra Tầng {tang.tang} ({tang.ten}: {tang.model})...")
        khoa_api = cau_hinh.lay_khoa_api(tang.api_key_env)
        ket_qua = kiem_tra_tang(tang, khoa_api)
        danh_sach_ket_qua.append(ket_qua)

    in_bang_ket_qua(danh_sach_ket_qua)

    co_tang_hoat_dong = any(kq.trang_thai == "ĐẠT" for kq in danh_sach_ket_qua)
    return 0 if co_tang_hoat_dong else 1


if __name__ == "__main__":
    sys.exit(chay_kiem_tra())
