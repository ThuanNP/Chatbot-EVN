"""Điểm khởi chạy ứng dụng FastAPI cho Chatbot EVN.

Bao gồm các endpoint theo đặc tả:
- POST /chat/stream: Luồng chính Server-Sent Events (SSE).
- POST /chat: Bản không phát theo dòng dành cho tích hợp máy-với-máy.
- GET /hoi-thoai: Danh sách hội thoại của người dùng hiện tại, phân trang, sắp xếp giảm dần theo cap_nhat_luc.
- GET /hoi-thoai/{id}: Toàn bộ tin nhắn của một hội thoại (trả 404 nếu không thuộc người dùng).
- DELETE /hoi-thoai/{id}: Xoá hội thoại và toàn bộ tin nhắn liên quan.
- GET /chi-phi: Thống kê chi phí hôm nay, ngân sách ngày, phân rã theo tầng và tỷ lệ rơi tầng 1h.
- GET /health: Kiểm tra tiến trình còn sống, phản hồi tức thì, không chạm cơ sở dữ liệu.
- GET /ready: Kiểm tra kết nối cơ sở dữ liệu và ít nhất một tầng model khả dụng (503 khi chưa sẵn sàng).

Tuân thủ nghiêm ngặt các quy tắc bất biến trong AGENTS.md.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.chat.hoi_thoai import (
    danh_sach_hoi_thoai,
    lay_hoi_thoai,
    lay_tin_nhan_hoi_thoai,
    luu_tin_nhan,
    tao_hoi_thoai,
    xoa_hoi_thoai,
)
from app.chat.ngu_canh import dung_ngu_canh
from app.config import lay_cau_hinh
from app.core.database import khoi_tao_db, lay_phien_db
from app.core.han_muc import VuotHanMucError, kiem_tra_han_muc
from app.llm.chi_phi import (
    VuotNganSachError,
    kiem_tra_ngan_sach,
    lay_thong_ke_chi_phi_ngay,
)
from app.llm.router import goi_mo_hinh, goi_mo_hinh_theo_dong

# Nạp biến môi trường từ tệp .env khi khởi chạy ứng dụng
load_dotenv()

# Cấu hình mức độ ghi log cấp hệ thống
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời ứng dụng: khởi tạo cơ sở dữ liệu khi khởi động."""
    try:
        khoi_tao_db()
    except Exception as e:
        logger.warning(f"Không thể khởi tạo cơ sở dữ liệu lúc khởi động: {e}")
    yield


# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="Chatbot EVN API",
    description="Hệ thống AI Chatbot phục vụ nghiệp vụ EVN với chuỗi dự phòng đa mô hình",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Cấu hình CORS
# ---------------------------------------------------------------------------
def _cau_hinh_cors(ung_dung: FastAPI) -> None:
    """Cấu hình CORS đọc từ biến môi trường, bảo đảm an toàn cho production."""
    try:
        cau_hinh = lay_cau_hinh()
        moi_truong = cau_hinh.env.MOI_TRUONG.lower()
        cors_raw = getattr(cau_hinh.env, "CORS_ORIGINS", "") or os.getenv("CORS_ORIGINS", "")
    except Exception:
        moi_truong = os.getenv("MOI_TRUONG", "development").lower()
        cors_raw = os.getenv("CORS_ORIGINS", "")

    if cors_raw:
        origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
    else:
        origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]

    # Quy tắc an toàn: Tuyệt đối không dùng dấu sao (*) trong môi trường chạy thật (production)
    if moi_truong == "production":
        origins = [o for o in origins if o != "*"]
        if not origins:
            origins = ["http://localhost:8000"]
        logger.info(f"[CORS] Môi trường production, danh sách origins được phép: {origins}")
    else:
        logger.info(f"[CORS] Môi trường {moi_truong}, danh sách origins được phép: {origins}")

    ung_dung.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_cau_hinh_cors(app)


# ---------------------------------------------------------------------------
# Middleware gắn mã yêu cầu (Request ID)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def gan_ma_yeu_cau(request: Request, call_next):
    """Gắn mã định danh yêu cầu duy nhất cho mỗi lượt gửi để theo dõi sự cố."""
    ma_yeu_cau = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.ma_yeu_cau = ma_yeu_cau
    response = await call_next(request)
    response.headers["X-Request-ID"] = ma_yeu_cau
    return response


# ---------------------------------------------------------------------------
# Tiện ích trích xuất người dùng và mã yêu cầu
# ---------------------------------------------------------------------------
def lay_ma_yeu_cau(request: Request) -> str:
    """Lấy mã yêu cầu từ request.state hoặc sinh mới nếu chưa có."""
    return getattr(request.state, "ma_yeu_cau", None) or str(uuid.uuid4())


def lay_nguoi_dung_id(request: Request) -> str:
    """Xác định định danh người dùng từ header hoặc mặc định 'khach'."""
    nguoi_dung_id = (
        request.headers.get("X-User-Id")
        or request.headers.get("X-Nguoi-Dung-Id")
        or request.query_params.get("user_id")
        or "khach"
    )
    return str(nguoi_dung_id).strip() or "khach"


# ---------------------------------------------------------------------------
# Bộ xử lý lỗi thống nhất (Global Exception Handlers)
# ---------------------------------------------------------------------------
def tao_phan_hoi_loi(status_code: int, thong_diep: str, ma_yeu_cau: str) -> JSONResponse:
    """Tạo đối tượng JSONResponse lỗi theo đúng định dạng {loi: {ma, thong_diep, ma_yeu_cau}}."""
    noi_dung = {
        "loi": {
            "ma": status_code,
            "thong_diep": thong_diep,
            "ma_yeu_cau": ma_yeu_cau,
        },
        "detail": thong_diep,
    }
    return JSONResponse(status_code=status_code, content=noi_dung)


@app.exception_handler(VuotHanMucError)
async def xu_ly_vuot_han_muc(request: Request, exc: VuotHanMucError):
    """Bắt lỗi khi người dùng vượt quá hạn mức yêu cầu trong 1 giờ."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    logger.warning(f"[Hạn mức 429] ma_yeu_cau={ma_yeu_cau}: {exc}")
    thong_diep = str(exc) or "Bạn đã vượt quá số lượt yêu cầu cho phép trong 1 giờ. Vui lòng thử lại sau."
    return tao_phan_hoi_loi(status.HTTP_429_TOO_MANY_REQUESTS, thong_diep, ma_yeu_cau)


@app.exception_handler(VuotNganSachError)
async def xu_ly_vuot_ngan_sach(request: Request, exc: VuotNganSachError):
    """Bắt lỗi khi tổng chi phí trong ngày vượt quá ngân sách cho phép."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    logger.error(f"[Ngân sách 503] ma_yeu_cau={ma_yeu_cau}: {exc}")
    thong_diep = str(exc) or "Hệ thống đã đạt giới hạn ngân sách hàng ngày. Vui lòng thử lại sau."
    return tao_phan_hoi_loi(status.HTTP_503_SERVICE_UNAVAILABLE, thong_diep, ma_yeu_cau)


@app.exception_handler(StarletteHTTPException)
async def xu_ly_http_exception(request: Request, exc: StarletteHTTPException):
    """Bắt các lỗi HTTP tiêu chuẩn (404, 400, 403, 503...)."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    logger.warning(f"[HTTP {exc.status_code}] ma_yeu_cau={ma_yeu_cau}: {exc.detail}")

    thong_diep_map = {
        400: "Yêu cầu không hợp lệ. Vui lòng kiểm tra lại thông tin gửi lên.",
        401: "Yêu cầu xác thực không hợp lệ hoặc thiếu thông tin định danh.",
        403: "Bạn không có quyền thực hiện thao tác này.",
        404: "Không tìm thấy tài nguyên yêu cầu hoặc phiên hội thoại không thuộc sở hữu của bạn.",
        422: "Dữ liệu gửi lên không đúng định dạng quy định.",
        503: "Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau.",
    }
    # Dùng thông điệp chi tiết nếu đã được viết tiếng Việt rõ nghĩa, ngược lại ánh xạ theo bảng
    thong_diep = str(exc.detail) if exc.detail and isinstance(exc.detail, str) and not exc.detail.startswith("Not Found") else thong_diep_map.get(exc.status_code, "Đã xảy ra lỗi khi xử lý yêu cầu.")
    return tao_phan_hoi_loi(exc.status_code, thong_diep, ma_yeu_cau)


@app.exception_handler(RequestValidationError)
async def xu_ly_validation_error(request: Request, exc: RequestValidationError):
    """Bắt lỗi khi dữ liệu đầu vào không vượt qua xác thực Pydantic."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    # Ghi chi tiết kỹ thuật vào nhật ký hệ thống, không để lộ ra ngoài
    logger.warning(f"[Validation Error 422] ma_yeu_cau={ma_yeu_cau}: {exc.errors()}")
    thong_diep = "Dữ liệu gửi lên không hợp lệ hoặc thiếu trường bắt buộc. Vui lòng kiểm tra lại."
    return tao_phan_hoi_loi(status.HTTP_422_UNPROCESSABLE_ENTITY, thong_diep, ma_yeu_cau)


@app.exception_handler(Exception)
async def xu_ly_ngoai_le_chung(request: Request, exc: Exception):
    """Bắt toàn bộ các lỗi nội bộ hệ thống chưa được phân loại (500)."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    # Chi tiết kỹ thuật CHỈ ghi vào nhật ký máy chủ
    logger.error(f"[Lỗi hệ thống 500] ma_yeu_cau={ma_yeu_cau}: {exc}", exc_info=True)
    thong_diep = "Đã xảy ra lỗi trong quá trình xử lý hệ thống. Vui lòng liên hệ quản trị viên hoặc thử lại sau."
    return tao_phan_hoi_loi(status.HTTP_500_INTERNAL_SERVER_ERROR, thong_diep, ma_yeu_cau)


# ---------------------------------------------------------------------------
# Mô hình dữ liệu Pydantic
# ---------------------------------------------------------------------------
class YeuCauChatStream(BaseModel):
    """Mô hình dữ liệu đầu vào cho yêu cầu chat phát theo dòng (SSE)."""

    hoi_thoai_id: Optional[str] = Field(default=None, description="Mã định danh phiên hội thoại")
    tin_nhan: Optional[Union[str, List[Dict[str, Any]]]] = Field(default=None, description="Nội dung tin nhắn")
    prompt: Optional[str] = Field(default=None, description="Lời nhắc hoặc câu hỏi người dùng")
    noi_dung: Optional[str] = Field(default=None, description="Nội dung văn bản thay thế")
    messages: Optional[List[Dict[str, Any]]] = Field(default=None, description="Danh sách tin nhắn theo chuẩn OpenAI")
    temperature: Optional[float] = Field(default=None, description="Nhiệt độ sáng tạo của mô hình")
    max_tokens: Optional[int] = Field(default=None, description="Số lượng token tối đa đầu ra")
    tuy_chon: Optional[Dict[str, Any]] = Field(default=None, description="Các tuỳ chọn tham số bổ sung")

    @model_validator(mode="after")
    def kiem_tra_co_noi_dung(self):
        """Đảm bảo ít nhất một trường nội dung tin nhắn được cung cấp."""
        if not (self.tin_nhan or self.prompt or self.noi_dung or self.messages):
            raise ValueError("Cần cung cấp nội dung tin nhắn (tin_nhan, prompt hoặc messages)")
        return self


class YeuCauChat(BaseModel):
    """Mô hình dữ liệu đầu vào cho endpoint chat không stream máy-với-máy."""

    hoi_thoai_id: Optional[str] = Field(default=None, description="Mã định danh phiên hội thoại (tuỳ chọn)")
    tin_nhan: Optional[Union[str, List[Dict[str, Any]]]] = Field(default=None, description="Nội dung tin nhắn")
    prompt: Optional[str] = Field(default=None, description="Lời nhắc hoặc câu hỏi người dùng")
    noi_dung: Optional[str] = Field(default=None, description="Nội dung văn bản thay thế")
    messages: Optional[List[Dict[str, Any]]] = Field(default=None, description="Danh sách tin nhắn")
    temperature: Optional[float] = Field(default=None, description="Nhiệt độ sáng tạo của mô hình")
    max_tokens: Optional[int] = Field(default=None, description="Số lượng token tối đa đầu ra")
    tuy_chon: Optional[Dict[str, Any]] = Field(default=None, description="Các tham số bổ sung")

    @model_validator(mode="after")
    def kiem_tra_co_noi_dung(self):
        """Đảm bảo ít nhất một trường nội dung tin nhắn được cung cấp."""
        if not (self.tin_nhan or self.prompt or self.noi_dung or self.messages):
            raise ValueError("Cần cung cấp nội dung tin nhắn (tin_nhan, prompt hoặc messages)")
        return self


class PhanHoiChat(BaseModel):
    """Mô hình dữ liệu trả về cho endpoint chat máy-với-máy kèm đầy đủ siêu dữ liệu."""

    hoi_thoai_id: str = Field(description="Mã định danh phiên hội thoại")
    cau_tra_loi: str = Field(description="Nội dung câu trả lời hoàn chỉnh từ mô hình")
    tang_phuc_vu: int = Field(description="Tầng mô hình đã phục vụ (1, 2, 3, 4)")
    model: str = Field(description="Tên mô hình thực tế đã xử lý")
    token_vao: int = Field(description="Số lượng token đầu vào")
    token_ra: int = Field(description="Số lượng token đầu ra")
    chi_phi_usd: float = Field(description="Chi phí ước tính của lượt gọi (USD)")
    do_tre_ms: float = Field(description="Độ trễ phản hồi (mili-giây)")
    so_lan_thu: int = Field(default=1, description="Số lần thử trước khi thành công")
    danh_sach_tang_da_hong: List[Dict[str, Any]] = Field(
        default_factory=list, description="Danh sách các tầng đã bị hỏng trước đó nếu có"
    )


class ThongTinHoiThoai(BaseModel):
    """Thông tin tóm tắt của một phiên hội thoại."""

    id: str = Field(description="Mã định danh phiên hội thoại")
    nguoi_dung_id: str = Field(description="Định danh người dùng sở hữu")
    tieu_de: str = Field(description="Tiêu đề cuộc trò chuyện")
    tao_luc: datetime = Field(description="Thời điểm khởi tạo")
    cap_nhat_luc: datetime = Field(description="Thời điểm cập nhật mới nhất")


class ChiTietTinNhan(BaseModel):
    """Thông tin chi tiết một tin nhắn trong phiên hội thoại."""

    id: int = Field(description="ID tự tăng của tin nhắn")
    hoi_thoai_id: str = Field(description="Mã phiên hội thoại")
    vai_tro: str = Field(description="Vai trò người gửi ('user' hoặc 'assistant')")
    noi_dung: str = Field(description="Nội dung tin nhắn")
    token_uoc_tinh: int = Field(default=0, description="Số lượng token ước tính")
    tang_phuc_vu: Optional[int] = Field(default=None, description="Tầng mô hình đã phục vụ nếu có")
    tao_luc: datetime = Field(description="Thời điểm tạo tin nhắn")


class PhanHoiXoaHoiThoai(BaseModel):
    """Kết quả xoá một phiên hội thoại."""

    thanh_cong: bool = Field(default=True, description="Trạng thái xoá thành công")
    thong_diep: str = Field(description="Thông điệp kết quả")
    hoi_thoai_id: str = Field(description="Mã định danh phiên hội thoại vừa xoá")


def chuan_hoa_van_ban_dau_vao(yeu_cau: Union[YeuCauChatStream, YeuCauChat]) -> str:
    """Trích xuất chuỗi văn bản người dùng nhập vào từ các trường linh hoạt."""
    raw = yeu_cau.tin_nhan or yeu_cau.prompt or yeu_cau.noi_dung or yeu_cau.messages
    if isinstance(raw, str):
        return raw.strip()
    elif isinstance(raw, list):
        for item in reversed(raw):
            if isinstance(item, dict) and item.get("role") == "user":
                return str(item.get("content", "")).strip()
            elif isinstance(item, dict) and "content" in item:
                return str(item.get("content", "")).strip()
        if raw and isinstance(raw[0], dict):
            return str(raw[0].get("content", "")).strip()
    return ""


# ---------------------------------------------------------------------------
# Endpoint cơ bản và kiểm tra sức khoẻ
# ---------------------------------------------------------------------------
@app.get("/")
async def trang_chu():
    """Endpoint gốc thông báo thông tin ứng dụng."""
    return {
        "ten": "Chatbot EVN",
        "phien_ban": "0.1.0",
        "mo_ta": "Hệ thống AI Chatbot EVN đang hoạt động.",
    }


@app.get("/health")
async def kiem_tra_suc_khoe():
    """Kiểm tra tình trạng tiến trình còn sống, phản hồi tức thì, tuyệt đối không chạm cơ sở dữ liệu."""
    return {"trang_thai": "ok", "dich_vu": "Chatbot-EVN"}


@app.get("/ready")
async def kiem_tra_san_sang():
    """Kiểm tra tính sẵn sàng: kết nối cơ sở dữ liệu VÀ có ít nhất một tầng model khả dụng.

    Trả về HTTP 503 khi hệ thống chưa sẵn sàng.
    """
    # 1. Kiểm tra kết nối cơ sở dữ liệu
    db_san_sang = False
    try:
        with lay_phien_db() as phien:
            phien.execute(text("SELECT 1"))
            db_san_sang = True
    except Exception as e:
        logger.error(f"[Ready Check] Kiểm tra cơ sở dữ liệu thất bại: {e}")
        db_san_sang = False

    # 2. Kiểm tra có ít nhất một tầng model khả dụng (có khoá API hợp lệ)
    mo_hinh_san_sang = False
    so_tang_kha_dung = 0
    try:
        cau_hinh = lay_cau_hinh()
        for tang in cau_hinh.models.chuoi_du_phong:
            khoa = cau_hinh.lay_khoa_api(tang.api_key_env)
            if khoa and khoa.strip() and khoa != "dan-khoa-that-vao-day":
                so_tang_kha_dung += 1
        mo_hinh_san_sang = so_tang_kha_dung > 0
    except Exception as e:
        logger.error(f"[Ready Check] Lỗi khi đọc cấu hình chuỗi dự phòng: {e}")
        mo_hinh_san_sang = False

    if not db_san_sang or not mo_hinh_san_sang:
        ly_do = []
        if not db_san_sang:
            ly_do.append("Cơ sở dữ liệu chưa sẵn sàng")
        if not mo_hinh_san_sang:
            ly_do.append("Chưa có tầng mô hình nào khả dụng")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "trang_thai": "chua_san_sang",
                "ly_do": "; ".join(ly_do),
                "co_so_du_lieu": "san_sang" if db_san_sang else "chua_ket_noi",
                "so_tang_mo_hinh_kha_dung": so_tang_kha_dung,
            },
        )

    return {
        "trang_thai": "san_sang",
        "dich_vu": "Chatbot-EVN",
        "co_so_du_lieu": "san_sang",
        "so_tang_mo_hinh_kha_dung": so_tang_kha_dung,
    }


@app.get("/chi-phi")
async def xem_chi_phi():
    """Endpoint trả về chi phí hôm nay, ngân sách ngày, phân rã theo tầng và tỷ lệ rơi tầng (Prompt 6)."""
    return lay_thong_ke_chi_phi_ngay()


# ---------------------------------------------------------------------------
# Endpoints quản lý hội thoại
# ---------------------------------------------------------------------------
@app.get("/hoi-thoai", response_model=List[ThongTinHoiThoai])
async def lay_cac_hoi_thoai(
    request: Request,
    gioi_han: int = Query(default=50, ge=1, le=100, description="Số lượng hội thoại tối đa"),
    bo_qua: int = Query(default=0, ge=0, description="Số lượng hội thoại bỏ qua (phân trang)"),
):
    """Danh sách các phiên hội thoại của người dùng hiện tại, sắp xếp theo thời gian cập nhật giảm dần."""
    nguoi_dung_id = lay_nguoi_dung_id(request)
    cac_hoi_thoai = danh_sach_hoi_thoai(
        nguoi_dung_id=nguoi_dung_id,
        gioi_han=gioi_han,
        bo_qua=bo_qua,
    )
    return [
        ThongTinHoiThoai(
            id=ht.id,
            nguoi_dung_id=ht.nguoi_dung_id,
            tieu_de=ht.tieu_de,
            tao_luc=ht.tao_luc,
            cap_nhat_luc=ht.cap_nhat_luc,
        )
        for ht in cac_hoi_thoai
    ]


@app.get("/hoi-thoai/{id}", response_model=List[ChiTietTinNhan])
async def lay_chi_tiet_hoi_thoai(id: str, request: Request):
    """Toàn bộ tin nhắn của một hội thoại. Trả về 404 nếu hội thoại không thuộc người dùng hiện tại."""
    nguoi_dung_id = lay_nguoi_dung_id(request)
    hoi_thoai = lay_hoi_thoai(id)
    if not hoi_thoai or hoi_thoai.nguoi_dung_id != nguoi_dung_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiên hội thoại hoặc bạn không có quyền truy cập.",
        )

    cac_tin_nhan = lay_tin_nhan_hoi_thoai(id)
    return [
        ChiTietTinNhan(
            id=tn.id,
            hoi_thoai_id=tn.hoi_thoai_id,
            vai_tro=tn.vai_tro,
            noi_dung=tn.noi_dung,
            token_uoc_tinh=tn.token_uoc_tinh,
            tang_phuc_vu=tn.tang_phuc_vu,
            tao_luc=tn.tao_luc,
        )
        for tn in cac_tin_nhan
    ]


@app.delete("/hoi-thoai/{id}", response_model=PhanHoiXoaHoiThoai)
async def xoa_phien_hoi_thoai(id: str, request: Request):
    """Xoá một phiên hội thoại và toàn bộ tin nhắn liên quan. Trả 404 nếu không thuộc người dùng."""
    nguoi_dung_id = lay_nguoi_dung_id(request)
    hoi_thoai = lay_hoi_thoai(id)
    if not hoi_thoai or hoi_thoai.nguoi_dung_id != nguoi_dung_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiên hội thoại hoặc bạn không có quyền xoá.",
        )

    thanh_cong = xoa_hoi_thoai(id)
    if not thanh_cong:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiên hội thoại cần xoá.",
        )

    return PhanHoiXoaHoiThoai(
        thanh_cong=True,
        thong_diep="Đã xoá phiên hội thoại và toàn bộ tin nhắn thành công.",
        hoi_thoai_id=id,
    )


# ---------------------------------------------------------------------------
# POST /chat/stream: Luồng chính Server-Sent Events (SSE)
# ---------------------------------------------------------------------------
@app.post("/chat/stream")
async def chat_stream(yeu_cau: YeuCauChatStream, request: Request):
    """Endpoint phát phản hồi theo dòng Server-Sent Events (SSE).

    Luồng xử lý:
    1. Kiểm tra hạn mức người dùng (429 nếu vượt).
    2. Kiểm tra ngân sách ngày (503 nếu vượt).
    3. Kiểm tra hoặc tạo mới phiên hội thoại (nếu chưa có hoi_thoai_id).
    4. Dựng ngữ cảnh hội thoại từ lịch sử kết hợp câu hỏi mới.
    5. Phát sự kiện đầu tiên trả về hoi_thoai_id.
    6. Gọi mô hình theo dòng qua bộ định tuyến.
    7. Lưu tin nhắn người dùng và câu trả lời vào cơ sở dữ liệu.
    """
    nguoi_dung_id = lay_nguoi_dung_id(request)

    # 1. Kiểm tra hạn mức người dùng
    kiem_tra_han_muc(nguoi_dung_id)

    # 2. Kiểm tra trần ngân sách ngày
    kiem_tra_ngan_sach()

    # 3. Quản lý phiên hội thoại
    hoi_thoai_id = yeu_cau.hoi_thoai_id
    if hoi_thoai_id:
        hoi_thoai_ton_tai = lay_hoi_thoai(hoi_thoai_id)
        if not hoi_thoai_ton_tai or hoi_thoai_ton_tai.nguoi_dung_id != nguoi_dung_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy phiên hội thoại hoặc bạn không có quyền truy cập.",
            )
    else:
        # Nếu không có hoi_thoai_id, tạo hội thoại mới cho người dùng
        ht_moi = tao_hoi_thoai(nguoi_dung_id=nguoi_dung_id)
        hoi_thoai_id = ht_moi.id

    van_ban_user = chuan_hoa_van_ban_dau_vao(yeu_cau)

    # 4. Dựng ngữ cảnh có lịch sử cắt tỉa an toàn theo cặp
    tin_nhan_gui_llm = dung_ngu_canh(
        hoi_thoai_id=hoi_thoai_id,
        tin_nhan_moi=van_ban_user,
    )

    # Chuẩn bị tham số gọi mô hình
    tham_so: Dict[str, Any] = {"nguoi_dung_id": nguoi_dung_id}
    if yeu_cau.temperature is not None:
        tham_so["temperature"] = yeu_cau.temperature
    if yeu_cau.max_tokens is not None:
        tham_so["max_tokens"] = yeu_cau.max_tokens
    if isinstance(yeu_cau.tuy_chon, dict):
        tham_so.update(yeu_cau.tuy_chon)

    async def tao_su_kien_sse():
        # Sự kiện đầu tiên: Trả về hoi_thoai_id cho client
        su_kien_dau = {
            "loai": "bat_dau",
            "su_kien": "bat_dau",
            "hoi_thoai_id": hoi_thoai_id,
        }
        yield f"data: {json.dumps(su_kien_dau, ensure_ascii=False)}\n\n"

        van_ban_tich_luy = ""
        da_luu_tin_nhan = False

        try:
            async for manh in goi_mo_hinh_theo_dong(tin_nhan_gui_llm, **tham_so):
                if manh.loai == "manh":
                    van_ban_tich_luy += manh.doan_van_ban
                    du_lieu = {
                        "loai": "manh",
                        "su_kien": "manh",
                        "hoi_thoai_id": hoi_thoai_id,
                        "doan_van_ban": manh.doan_van_ban,
                        "noi_dung": manh.doan_van_ban,
                    }
                    yield f"data: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"

                elif manh.loai == "xong":
                    # Lưu cả tin nhắn người dùng và câu trả lời vào cơ sở dữ liệu
                    try:
                        if van_ban_user:
                            luu_tin_nhan(
                                hoi_thoai_id=hoi_thoai_id,
                                vai_tro="user",
                                noi_dung=van_ban_user,
                            )
                        cau_tra_loi_cuoi = manh.noi_dung or van_ban_tich_luy
                        luu_tin_nhan(
                            hoi_thoai_id=hoi_thoai_id,
                            vai_tro="assistant",
                            noi_dung=cau_tra_loi_cuoi,
                            tang_phuc_vu=manh.tang_phuc_vu,
                            token_uoc_tinh=manh.token_ra,
                        )
                        da_luu_tin_nhan = True
                    except Exception as e_db:
                        logger.error(f"[Chat Stream] Lỗi khi lưu tin nhắn vào CSDL: {e_db}")

                    du_lieu = {
                        "loai": "xong",
                        "su_kien": "xong",
                        "hoi_thoai_id": hoi_thoai_id,
                        "tang_phuc_vu": manh.tang_phuc_vu,
                        "ten_model": manh.ten_model,
                        "token_vao": manh.token_vao,
                        "token_ra": manh.token_ra,
                        "do_tre_ms": manh.do_tre_ms,
                        "chi_phi_usd": manh.chi_phi_usd,
                        "so_lan_thu": manh.so_lan_thu,
                        "danh_sach_tang_da_hong": manh.danh_sach_tang_da_hong,
                        "noi_dung": manh.noi_dung,
                        "van_ban_da_nhan": manh.van_ban_da_nhan,
                    }
                    yield f"data: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"

                elif manh.loai == "loi":
                    # Lỗi giữa chừng: nếu đã nhận được một phần câu trả lời thì vẫn lưu lại
                    if van_ban_tich_luy and not da_luu_tin_nhan:
                        try:
                            if van_ban_user:
                                luu_tin_nhan(
                                    hoi_thoai_id=hoi_thoai_id,
                                    vai_tro="user",
                                    noi_dung=van_ban_user,
                                )
                            luu_tin_nhan(
                                hoi_thoai_id=hoi_thoai_id,
                                vai_tro="assistant",
                                noi_dung=van_ban_tich_luy,
                                tang_phuc_vu=manh.tang_phuc_vu,
                            )
                        except Exception as e_db:
                            logger.warning(f"[Chat Stream] Lỗi lưu tin nhắn lỗi giữa chừng: {e_db}")

                    du_lieu = {
                        "loai": "loi",
                        "su_kien": "loi",
                        "hoi_thoai_id": hoi_thoai_id,
                        "thong_diep_loi": manh.thong_diep_loi,
                        "loi": manh.thong_diep_loi,
                        "van_ban_da_nhan": manh.van_ban_da_nhan,
                    }
                    yield f"data: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"

        except VuotNganSachError as e:
            logger.error(f"[Chat Stream] Vượt trần ngân sách ngày trong luồng phát: {e}")
            du_lieu_loi = {
                "loai": "loi",
                "su_kien": "loi",
                "hoi_thoai_id": hoi_thoai_id,
                "thong_diep_loi": str(e),
                "loi": str(e),
                "van_ban_da_nhan": van_ban_tich_luy,
            }
            yield f"data: {json.dumps(du_lieu_loi, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"[Chat Stream] Lỗi xảy ra trong luồng SSE: {e}", exc_info=True)
            du_lieu_loi = {
                "loai": "loi",
                "su_kien": "loi",
                "hoi_thoai_id": hoi_thoai_id,
                "thong_diep_loi": "Đã xảy ra sự cố trong quá trình truyền dữ liệu.",
                "loi": "Đã xảy ra sự cố trong quá trình truyền dữ liệu.",
                "van_ban_da_nhan": van_ban_tich_luy,
            }
            yield f"data: {json.dumps(du_lieu_loi, ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        tao_su_kien_sse(),
        media_type="text/event-stream",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# POST /chat: Bản không phát theo dòng cho máy-với-máy
# ---------------------------------------------------------------------------
@app.post("/chat", response_model=PhanHoiChat)
async def chat_dong_bo(yeu_cau: YeuCauChat, request: Request):
    """Bản chat không phát theo dòng dùng cho tích hợp máy-với-máy (M2M).

    Trả về đầy đủ siêu dữ liệu cuộc gọi: tầng phục vụ, model, token, chi phí, độ trễ.
    """
    nguoi_dung_id = lay_nguoi_dung_id(request)

    # 1. Kiểm tra hạn mức người dùng
    kiem_tra_han_muc(nguoi_dung_id)

    # 2. Kiểm tra trần ngân sách ngày
    kiem_tra_ngan_sach()

    # 3. Quản lý phiên hội thoại
    hoi_thoai_id = yeu_cau.hoi_thoai_id
    if hoi_thoai_id:
        hoi_thoai_ton_tai = lay_hoi_thoai(hoi_thoai_id)
        if not hoi_thoai_ton_tai or hoi_thoai_ton_tai.nguoi_dung_id != nguoi_dung_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy phiên hội thoại hoặc bạn không có quyền truy cập.",
            )
    else:
        ht_moi = tao_hoi_thoai(nguoi_dung_id=nguoi_dung_id)
        hoi_thoai_id = ht_moi.id

    van_ban_user = chuan_hoa_van_ban_dau_vao(yeu_cau)

    # 4. Dựng ngữ cảnh hội thoại
    tin_nhan_gui_llm = dung_ngu_canh(
        hoi_thoai_id=hoi_thoai_id,
        tin_nhan_moi=van_ban_user,
    )

    # Chuẩn bị tham số
    tham_so: Dict[str, Any] = {"nguoi_dung_id": nguoi_dung_id}
    if yeu_cau.temperature is not None:
        tham_so["temperature"] = yeu_cau.temperature
    if yeu_cau.max_tokens is not None:
        tham_so["max_tokens"] = yeu_cau.max_tokens
    if isinstance(yeu_cau.tuy_chon, dict):
        tham_so.update(yeu_cau.tuy_chon)

    # 5. Gọi mô hình qua bộ định tuyến (không phát theo dòng)
    ket_qua = await goi_mo_hinh(
        tin_nhan=tin_nhan_gui_llm,
        phat_theo_dong=False,
        **tham_so,
    )

    cau_tra_loi = str(ket_qua.noi_dung or "")

    # 6. Lưu tin nhắn người dùng và câu trả lời trợ lý
    try:
        if van_ban_user:
            luu_tin_nhan(
                hoi_thoai_id=hoi_thoai_id,
                vai_tro="user",
                noi_dung=van_ban_user,
            )
        luu_tin_nhan(
            hoi_thoai_id=hoi_thoai_id,
            vai_tro="assistant",
            noi_dung=cau_tra_loi,
            tang_phuc_vu=ket_qua.tang_phuc_vu,
            token_uoc_tinh=ket_qua.token_ra,
        )
    except Exception as e_db:
        logger.error(f"[Chat M2M] Lỗi khi lưu tin nhắn vào CSDL: {e_db}")

    return PhanHoiChat(
        hoi_thoai_id=hoi_thoai_id,
        cau_tra_loi=cau_tra_loi,
        tang_phuc_vu=ket_qua.tang_phuc_vu,
        model=ket_qua.ten_model,
        token_vao=ket_qua.token_vao,
        token_ra=ket_qua.token_ra,
        chi_phi_usd=ket_qua.chi_phi_usd,
        do_tre_ms=ket_qua.do_tre_ms,
        so_lan_thu=ket_qua.so_lan_thu,
        danh_sach_tang_da_hong=ket_qua.danh_sach_tang_da_hong,
    )
