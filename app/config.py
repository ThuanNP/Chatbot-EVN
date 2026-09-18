"""Quản lý nạp cấu hình và biến môi trường của hệ thống Chatbot EVN.

Sử dụng Pydantic-Settings để đọc .env và PyYAML để nạp cấu hình config/models.yaml.
Phơi ra đối tượng cấu hình có kiểm tra kiểu dữ liệu (type validation).
Tuân thủ nghiêm ngặt: Không đặt giá trị mặc định cho bất kỳ khoá API nào.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Đường dẫn thư mục gốc dự án
DUONG_DAN_GOC = Path(__file__).resolve().parent.parent
DUONG_DAN_MODELS_YAML = DUONG_DAN_GOC / "config" / "models.yaml"


class CaiDatChung(BaseModel):
    """Cài đặt chung cho chuỗi dự phòng và lời gọi mô hình."""

    so_lan_thu_lai_moi_tang: int = Field(
        default=2, description="Số lần thử lại tối đa cho mỗi tầng trước khi chuyển tầng tiếp theo"
    )
    giay_gian_cach_dau: float = Field(
        default=1.0, description="Thời gian chờ ban đầu (giây) theo cấp số nhân"
    )
    timeout_mac_dinh_giay: int = Field(
        default=60, description="Thời gian chờ tối đa mặc định cho mỗi cuộc gọi"
    )
    gioi_han_token_ra: int = Field(
        default=4096, description="Giới hạn số lượng token tối đa trong phản hồi"
    )


class CauHinhTang(BaseModel):
    """Cấu hình chi tiết cho từng tầng trong chuỗi dự phòng."""

    tang: int = Field(description="Số thứ tự tầng (1, 2, 3, 4...)")
    ten: str = Field(description="Tên định danh của tầng (gemini, openrouter_auto, claude, openai)")
    model: str = Field(description="Chuỗi định danh model theo chuẩn LiteLLM")
    api_key_env: str = Field(description="Tên biến môi trường chứa khoá API của tầng")
    gia_vao_usd_moi_trieu: float = Field(
        default=0.0, description="Giá token đầu vào (USD / 1 triệu token)"
    )
    gia_ra_usd_moi_trieu: float = Field(
        default=0.0, description="Giá token đầu ra (USD / 1 triệu token)"
    )
    timeout_giay: int = Field(
        default=60, description="Thời gian chờ tối đa cho tầng này (giây)"
    )
    tham_so_them: Dict[str, Any] = Field(
        default_factory=dict, description="Các tham số bổ sung gửi kèm request"
    )
    ghi_chu: Optional[str] = Field(
        default=None, description="Ghi chú về model hoặc tầng"
    )


class CauHinhModels(BaseModel):
    """Cấu hình các tầng mô hình và tham số chung nạp từ config/models.yaml."""

    chuoi_du_phong: List[CauHinhTang] = Field(
        description="Danh sách các tầng mô hình sắp xếp theo thứ tự ưu tiên thử nghiệm"
    )
    cai_dat_chung: CaiDatChung = Field(
        description="Cài đặt chung cho các cuộc gọi mô hình"
    )


class CaiDatMoiTruong(BaseSettings):
    """Đọc cấu hình từ tệp .env hoặc biến môi trường hệ thống qua Pydantic-Settings.

    QUY TẮC BẤT BIẾN:
    Tuyệt đối không đặt giá trị mặc định cho bất kỳ khoá API nào.
    Các khoá bắt buộc phải được cung cấp qua môi trường hoặc tệp .env.
    """

    model_config = SettingsConfigDict(
        env_file=str(DUONG_DAN_GOC / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 4 khoá API của các nhà cung cấp - CẤM đặt giá trị mặc định
    GOOGLE_API_KEY: str = Field(
        description="Khoá API của Google Gemini"
    )
    OPENROUTER_API_KEY: str = Field(
        description="Khoá API của OpenRouter"
    )
    ANTHROPIC_API_KEY: str = Field(
        description="Khoá API của Anthropic (Claude)"
    )
    OPENAI_API_KEY: str = Field(
        description="Khoá API của OpenAI"
    )

    # Cấu hình cơ sở dữ liệu và bảo mật
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/chatbot_evn",
        description="Chuỗi kết nối cơ sở dữ liệu PostgreSQL"
    )
    APP_SECRET: str = Field(
        default="dev-secret-key-change-in-prod",
        description="Khoá bí mật dùng cho ứng dụng"
    )

    # Cấu hình hạn mức và ngân sách
    NGAN_SACH_NGAY_USD: float = Field(
        default=10.0,
        description="Ngân sách giới hạn tối đa mỗi ngày (USD)"
    )
    HAN_MUC_MOI_NGUOI_GIO: int = Field(
        default=60,
        description="Hạn mức số lượt yêu cầu tối đa mỗi người dùng trong một giờ"
    )
    HAN_MUC_IP_PHUT: int = Field(
        default=20,
        description="Hạn mức số lượt yêu cầu tối đa theo địa chỉ IP trong 1 phút (chặn dồn dập)"
    )
    HE_SO_BAC_PRO: int = Field(
        default=5,
        description="Hệ số nhân hạn mức mỗi giờ dành cho người dùng bậc pro"
    )
    HAN_MUC_CHI_PHI_NGAY_FREE_USD: float = Field(
        default=1.0,
        description="Hạn mức chi phí tối đa trong ngày cho bậc free (USD)"
    )
    HAN_MUC_CHI_PHI_NGAY_PRO_USD: float = Field(
        default=5.0,
        description="Hạn mức chi phí tối đa trong ngày cho bậc pro (USD)"
    )
    MOI_TRUONG: str = Field(
        default="development",
        description="Môi trường thực thi (development, staging, production)"
    )
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000",
        description="Danh sách các miền được phép truy cập CORS, phân tách bằng dấu phẩy"
    )
    GHI_NOI_DUNG: bool = Field(
        default=False,
        description="Cờ cho phép ghi nội dung tin nhắn vào nhật ký (chỉ bật trong dev để gỡ lỗi)"
    )


class CauHinhHeThong(BaseModel):
    """Đối tượng cấu hình tổng hợp toàn bộ hệ thống (biến môi trường + models.yaml)."""

    env: CaiDatMoiTruong
    models: CauHinhModels

    def lay_khoa_api(self, ten_bien_env: str) -> str:
        """Lấy giá trị khoá API từ biến môi trường tương ứng."""
        gia_tri = getattr(self.env, ten_bien_env, None)
        if gia_tri is None:
            import os
            return os.getenv(ten_bien_env, "")
        return gia_tri

    def lay_tang_theo_so(self, so_tang: int) -> Optional[CauHinhTang]:
        """Lấy cấu hình của tầng theo số thứ tự (1, 2, 3, 4)."""
        for tang in self.models.chuoi_du_phong:
            if tang.tang == so_tang:
                return tang
        return None

    def lay_tang_theo_ten(self, ten: str) -> Optional[CauHinhTang]:
        """Lấy cấu hình của tầng theo tên định danh."""
        for tang in self.models.chuoi_du_phong:
            if tang.ten == ten:
                return tang
        return None


def doc_cau_hinh_models(duong_dan_tep: Optional[Path] = None) -> CauHinhModels:
    """Nạp và kiểm tra kiểu nội dung tệp models.yaml.

    Args:
        duong_dan_tep: Đường dẫn tệp yaml (mặc định lấy config/models.yaml)

    Returns:
        CauHinhModels: Đối tượng dữ liệu đã kiểm tra kiểu
    """
    duong_dan = duong_dan_tep or DUONG_DAN_MODELS_YAML
    if not duong_dan.exists():
        raise FileNotFoundError(f"Không tìm thấy tệp cấu hình models tại: {duong_dan}")

    with open(duong_dan, "r", encoding="utf-8") as f:
        du_lieu = yaml.safe_load(f)

    return CauHinhModels.model_validate(du_lieu)


# Biến singleton lưu cấu hình đã nạp
_cau_hinh_he_thong: Optional[CauHinhHeThong] = None


def lay_cau_hinh(nap_lai: bool = False) -> CauHinhHeThong:
    """Khởi tạo và trả về đối tượng cấu hình hệ thống (singleton).

    Args:
        nap_lai: Nếu True, nạp lại cấu hình từ disk và .env

    Returns:
        CauHinhHeThong: Đối tượng cấu hình hệ thống hoàn chỉnh
    """
    global _cau_hinh_he_thong
    if _cau_hinh_he_thong is None or nap_lai:
        cai_dat_env = CaiDatMoiTruong()
        cai_dat_models = doc_cau_hinh_models()
        _cau_hinh_he_thong = CauHinhHeThong(env=cai_dat_env, models=cai_dat_models)
    return _cau_hinh_he_thong


# Bí danh tiếng Anh để thuận tiện import
get_config = lay_cau_hinh
