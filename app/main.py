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
from pathlib import Path
import time
import traceback
from typing import Any, Dict, List, Optional, Union
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
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
from app.core.bao_mat import (
    LoiBaoMatError,
    TiemLoiNhacError,
    TinNhanQuaDaiError,
    che_du_lieu_ca_nhan,
    dong_khung_noi_dung_nguoi_dung,
    kiem_duyet_dau_vao,
    kiem_duyet_dau_ra,
    kiem_tra_dau_vao,
)
from app.core.database import NguoiDung as NguoiDungDB, khoi_tao_db, lay_phien_db
from app.core.nhat_ky import (
    dat_ma_yeu_cau,
    dat_nguoi_dung_id,
    ghi_goi_mo_hinh,
    ghi_http_ra,
    ghi_http_vao,
    ghi_kiem_tra_han_muc,
    ghi_luu_hoi_thoai,
    ghi_nhat_ky,
    lay_ma_yeu_cau_hien_tai,
    lay_nguoi_dung_id_hien_tai,
    sinh_ma_yeu_cau,
    thiet_lap_nhat_ky,
)
from app.core.han_muc import (
    VuotHanMucError,
    bam_ma_thong_bao,
    kiem_tra_ba_tang_han_muc,
    kiem_tra_han_muc,
    lay_thong_tin_nguoi_dung_hien_tai,
)
from app.llm.chi_phi import (
    VuotNganSachError,
    kiem_tra_ngan_sach,
    lay_thong_ke_chi_phi_ngay,
)
from app.llm.router import goi_mo_hinh, goi_mo_hinh_theo_dong

# Nạp biến môi trường từ tệp .env khi khởi chạy ứng dụng
load_dotenv()

# Cấu hình mức độ ghi log và định dạng JSON một dòng
thiet_lap_nhat_ky()

logger = logging.getLogger(__name__)

# Thư mục chứa giao diện web tĩnh
THU_MUC_WEB = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời ứng dụng: cấu hình nhật ký và khởi tạo cơ sở dữ liệu khi khởi động."""
    try:
        thiet_lap_nhat_ky()
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
# Middleware gắn mã yêu cầu và nhật ký truy vết (Request ID & Trace Middleware)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def gan_ma_yeu_cau(request: Request, call_next):
    """Gắn mã định danh yêu cầu 12 ký tự, lưu trong contextvars và ghi nhật ký 2 chặng HTTP."""
    # 1. Chấp nhận mã do phía gọi truyền vào (X-Ma-Yeu-Cau hoặc X-Request-ID) để nối chuỗi truy vết liên dịch vụ
    ma_truyen_vao = request.headers.get("X-Ma-Yeu-Cau") or request.headers.get("X-Request-ID")
    if ma_truyen_vao and ma_truyen_vao.strip():
        ma_yeu_cau = ma_truyen_vao.strip()
    else:
        ma_yeu_cau = sinh_ma_yeu_cau()

    # Lưu trong contextvars và request.state
    dat_ma_yeu_cau(ma_yeu_cau)
    request.state.ma_yeu_cau = ma_yeu_cau

    # Lưu nguoi_dung_id sơ bộ vào contextvars nếu có trong header
    nguoi_dung_id_header = (
        request.headers.get("X-User-Id")
        or request.headers.get("X-Nguoi-Dung-Id")
        or request.query_params.get("user_id")
        or "khach"
    )
    dat_nguoi_dung_id(str(nguoi_dung_id_header).strip())

    # Chặng 1: http_vao
    thoi_diem_bat_dau = time.perf_counter()
    ghi_http_vao(
        phuong_thuc=request.method,
        duong_dan=request.url.path,
        do_tre_ms=0.0,
    )

    # Tiếp tục luồng xử lý yêu cầu
    try:
        response = await call_next(request)
    except Exception as exc:
        do_tre_tong_ms = round((time.perf_counter() - thoi_diem_bat_dau) * 1000, 2)
        ghi_http_ra(
            phuong_thuc=request.method,
            duong_dan=request.url.path,
            ma_trang_thai=500,
            do_tre_ms=do_tre_tong_ms,
        )
        raise exc

    # Trả lại mã yêu cầu trong cả header X-Ma-Yeu-Cau và X-Request-ID
    response.headers["X-Ma-Yeu-Cau"] = ma_yeu_cau
    response.headers["X-Request-ID"] = ma_yeu_cau

    # Chặng 6: http_ra
    if isinstance(response, StreamingResponse):
        phan_hoi_goc = response.body_iterator

        async def bọc_luồng_phát():
            try:
                async for doan in phan_hoi_goc:
                    yield doan
            finally:
                do_tre_tong_ms = round((time.perf_counter() - thoi_diem_bat_dau) * 1000, 2)
                ghi_http_ra(
                    phuong_thuc=request.method,
                    duong_dan=request.url.path,
                    ma_trang_thai=response.status_code,
                    do_tre_ms=do_tre_tong_ms,
                )

        response.body_iterator = bọc_luồng_phát()
    else:
        do_tre_tong_ms = round((time.perf_counter() - thoi_diem_bat_dau) * 1000, 2)
        ghi_http_ra(
            phuong_thuc=request.method,
            duong_dan=request.url.path,
            ma_trang_thai=response.status_code,
            do_tre_ms=do_tre_tong_ms,
        )

    return response


# ---------------------------------------------------------------------------
# Tiện ích trích xuất người dùng, địa chỉ IP và mã yêu cầu
# ---------------------------------------------------------------------------
def lay_ma_yeu_cau(request: Optional[Request] = None) -> str:
    """Lấy mã yêu cầu từ contextvars hoặc request.state, sinh mới nếu chưa có."""
    ma = lay_ma_yeu_cau_hien_tai()
    if ma:
        return ma
    if request:
        return getattr(request.state, "ma_yeu_cau", None) or sinh_ma_yeu_cau()
    return sinh_ma_yeu_cau()


class NguoiDung(BaseModel):
    """Đối tượng người dùng nghiệp vụ.

    GHI CHÚ: Đây là chỗ sẽ thay bằng nhà cung cấp đăng nhập thật ở giai đoạn sau;
    mọi nơi khác chỉ phụ thuộc vào đối tượng NguoiDung nên chỉ cần thay ruột hàm này.
    """

    id: str = Field(description="Mã định danh người dùng")
    email: str = Field(default="", description="Địa chỉ email")
    bac: str = Field(default="free", description="Bậc tài khoản ('free' hoặc 'pro')")


def lay_dia_chi_ip(request: Request) -> str:
    """Trích xuất địa chỉ IP của máy khách phục vụ kiểm soát hạn mức Tầng 1."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
        if ip:
            return ip
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip and x_real_ip.strip():
        return x_real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def lay_nguoi_dung_hien_tai(request: Request) -> NguoiDung:
    """Dependency xác thực người dùng từ Bearer token.

    GHI CHÚ: Đây là chỗ sẽ thay bằng nhà cung cấp đăng nhập thật ở giai đoạn sau;
    mọi nơi khác chỉ phụ thuộc vào đối tượng NguoiDung nên chỉ cần thay ruột hàm này.

    Quy trình:
    1. Đọc mã thông báo từ header Authorization dạng 'Bearer <token>'.
    2. Băm mã thông báo bằng HMAC-SHA256 kết hợp APP_SECRET (chuẩn băm bảo mật, không lưu thô).
    3. Đối chiếu với bảng nguoi_dung trong cơ sở dữ liệu.
    4. Trả về đối tượng NguoiDung có trường id, email và bac ('free' hoặc 'pro').
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu mã thông báo xác thực. Vui lòng gửi header 'Authorization: Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    phan_doan = auth_header.strip().split()
    if len(phan_doan) != 2 or phan_doan[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Định dạng mã thông báo không hợp lệ. Vui lòng dùng dạng 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_tho = phan_doan[1].strip()
    token_hash = bam_ma_thong_bao(token_tho)

    with lay_phien_db() as phien:
        stmt = select(NguoiDungDB).where(
            NguoiDungDB.token_hash == token_hash,
            NguoiDungDB.kich_hoat == True,
        )
        nd_db = phien.execute(stmt).scalar_one_or_none()

        if not nd_db:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Mã thông báo không hợp lệ hoặc tài khoản đã bị vô hiệu hóa.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return NguoiDung(
            id=str(nd_db.id),
            email=str(nd_db.email),
            bac=str(nd_db.bac),
        )


def lay_nguoi_dung_id(request: Request) -> str:
    """Xác định định danh người dùng từ header hoặc mặc định 'khach'."""
    nguoi_dung_id = (
        request.headers.get("X-User-Id")
        or request.headers.get("X-Nguoi-Dung-Id")
        or request.query_params.get("user_id")
        or "khach"
    )
    return str(nguoi_dung_id).strip() or "khach"


def lay_dinh_danh_va_bac(request: Request) -> tuple[str, str]:
    """Lấy (nguoi_dung_id, bac) từ Bearer token nếu có, hoặc rơi về X-User-Id / khách."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.strip().lower().startswith("bearer "):
        try:
            nd = lay_nguoi_dung_hien_tai(request)
            return (nd.id, nd.bac)
        except HTTPException:
            pass

    nguoi_dung_id = lay_nguoi_dung_id(request)
    return (nguoi_dung_id, "free")


# ---------------------------------------------------------------------------
# Bộ xử lý lỗi thống nhất (Global Exception Handlers)
# ---------------------------------------------------------------------------
def tao_phan_hoi_loi(
    status_code: int,
    thong_diep: str,
    ma_yeu_cau: str,
    headers: Optional[dict] = None,
) -> JSONResponse:
    """Tạo đối tượng JSONResponse lỗi theo đúng định dạng {loi: {ma, thong_diep, ma_yeu_cau}}."""
    noi_dung = {
        "loi": {
            "ma": status_code,
            "thong_diep": thong_diep,
            "ma_yeu_cau": ma_yeu_cau,
        },
        "detail": thong_diep,
        "ma": status_code,
        "ma_yeu_cau": ma_yeu_cau,
    }
    phan_hoi_headers = dict(headers or {})
    phan_hoi_headers["X-Ma-Yeu-Cau"] = ma_yeu_cau
    phan_hoi_headers["X-Request-ID"] = ma_yeu_cau
    return JSONResponse(status_code=status_code, content=noi_dung, headers=phan_hoi_headers)


@app.exception_handler(VuotHanMucError)
async def xu_ly_vuot_han_muc(request: Request, exc: VuotHanMucError):
    """Bắt lỗi khi yêu cầu vượt quá một trong ba tầng hạn mức."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    ghi_nhat_ky(
        chang="kiem_tra_han_muc",
        thong_diep=f"[Hạn mức 429] tang={exc.tang_han_muc}, retry_after={exc.retry_after}s: {exc.thong_diep}",
        do_tre_ms=0.0,
        muc="WARNING",
        ma_yeu_cau=ma_yeu_cau,
        tang_han_muc=exc.tang_han_muc,
        retry_after=exc.retry_after,
    )
    headers = {
        "Retry-After": str(exc.retry_after),
        "X-Ma-Yeu-Cau": ma_yeu_cau,
        "X-Request-ID": ma_yeu_cau,
    }
    noi_dung = {
        "loi": {
            "ma": status.HTTP_429_TOO_MANY_REQUESTS,
            "thong_diep": exc.thong_diep,
            "ma_yeu_cau": ma_yeu_cau,
            "retry_after": exc.retry_after,
            "tang_han_muc": exc.tang_han_muc,
        },
        "detail": exc.thong_diep,
        "ma": status.HTTP_429_TOO_MANY_REQUESTS,
        "ma_yeu_cau": ma_yeu_cau,
    }
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=noi_dung,
        headers=headers,
    )


@app.exception_handler(VuotNganSachError)
async def xu_ly_vuot_ngan_sach(request: Request, exc: VuotNganSachError):
    """Bắt lỗi khi tổng chi phí trong ngày vượt quá ngân sách cho phép."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    ghi_nhat_ky(
        chang="kiem_tra_han_muc",
        thong_diep=f"[Ngân sách 503] {exc}",
        do_tre_ms=0.0,
        muc="ERROR",
        ma_yeu_cau=ma_yeu_cau,
    )
    thong_diep = str(exc) or "Hệ thống đã đạt giới hạn ngân sách hàng ngày. Vui lòng thử lại sau."
    return tao_phan_hoi_loi(status.HTTP_503_SERVICE_UNAVAILABLE, thong_diep, ma_yeu_cau)


@app.exception_handler(TinNhanQuaDaiError)
async def xu_ly_tin_nhan_qua_dai(request: Request, exc: TinNhanQuaDaiError):
    """Bắt lỗi khi độ dài tin nhắn người dùng vượt quá ngưỡng cho phép."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    ghi_nhat_ky(
        chang="bao_mat",
        thong_diep=f"[Bảo mật 400] {exc}",
        do_tre_ms=0.0,
        muc="WARNING",
        ma_yeu_cau=ma_yeu_cau,
        do_dai=exc.do_dai,
        gioi_han=exc.gioi_han,
    )
    return tao_phan_hoi_loi(status.HTTP_400_BAD_REQUEST, str(exc), ma_yeu_cau)


@app.exception_handler(TiemLoiNhacError)
async def xu_ly_tiem_loi_nhac(request: Request, exc: TiemLoiNhacError):
    """Bắt lỗi khi phát hiện mẫu tiêm lời nhắc cơ bản trong tin nhắn đầu vào."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    ghi_nhat_ky(
        chang="bao_mat",
        thong_diep=f"[Bảo mật 400] {exc}",
        do_tre_ms=0.0,
        muc="WARNING",
        ma_yeu_cau=ma_yeu_cau,
        mau_tiem=exc.mau_tiem,
    )
    return tao_phan_hoi_loi(status.HTTP_400_BAD_REQUEST, str(exc), ma_yeu_cau)


@app.exception_handler(StarletteHTTPException)
async def xu_ly_http_exception(request: Request, exc: StarletteHTTPException):
    """Bắt các lỗi HTTP tiêu chuẩn (404, 400, 403, 503...)."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    ghi_nhat_ky(
        chang="http_ra",
        thong_diep=f"[HTTP {exc.status_code}] {exc.detail}",
        do_tre_ms=0.0,
        muc="WARNING" if exc.status_code < 500 else "ERROR",
        ma_yeu_cau=ma_yeu_cau,
        ma_trang_thai=exc.status_code,
    )

    thong_diep_map = {
        400: "Yêu cầu không hợp lệ. Vui lòng kiểm tra lại thông tin gửi lên.",
        401: "Yêu cầu xác thực không hợp lệ hoặc thiếu thông tin định danh.",
        403: "Bạn không có quyền thực hiện thao tác này.",
        404: "Không tìm thấy tài nguyên yêu cầu hoặc phiên hội thoại không thuộc sở hữu của bạn.",
        422: "Dữ liệu gửi lên không đúng định dạng quy định.",
        503: "Dịch vụ tạm thời không khả dụng. Vui lòng thử lại sau.",
    }
    thong_diep = str(exc.detail) if exc.detail and isinstance(exc.detail, str) and not exc.detail.startswith("Not Found") else thong_diep_map.get(exc.status_code, "Đã xảy ra lỗi khi xử lý yêu cầu.")
    return tao_phan_hoi_loi(exc.status_code, thong_diep, ma_yeu_cau)


@app.exception_handler(RequestValidationError)
async def xu_ly_validation_error(request: Request, exc: RequestValidationError):
    """Bắt lỗi khi dữ liệu đầu vào không vượt qua xác thực Pydantic."""
    ma_yeu_cau = lay_ma_yeu_cau(request)
    ghi_nhat_ky(
        chang="http_vao",
        thong_diep="Dữ liệu đầu vào không hợp lệ (Validation Error 422)",
        do_tre_ms=0.0,
        muc="WARNING",
        ma_yeu_cau=ma_yeu_cau,
        so_loi=len(exc.errors()),
    )
    thong_diep = "Dữ liệu gửi lên không hợp lệ hoặc thiếu trường bắt buộc. Vui lòng kiểm tra lại."
    return tao_phan_hoi_loi(status.HTTP_422_UNPROCESSABLE_ENTITY, thong_diep, ma_yeu_cau)


@app.exception_handler(Exception)
async def xu_ly_ngoai_le_chung(request: Request, exc: Exception):
    """Bắt toàn bộ các lỗi nội bộ hệ thống chưa được phân loại (500).

    QUY TẮC 5: Ghi nguyên vết lỗi (traceback) vào nhật ký kèm ma_yeu_cau,
    nhưng CHỈ trả ra ngoài mã lỗi và ma_yeu_cau để người dùng đọc cho bộ phận hỗ trợ.
    """
    ma_yeu_cau = lay_ma_yeu_cau(request)
    vet_loi = traceback.format_exc()
    # Chi tiết kỹ thuật CHỈ ghi vào nhật ký máy chủ kèm ma_yeu_cau
    ghi_nhat_ky(
        chang="he_thong",
        thong_diep=f"Lỗi hệ thống chưa phân loại: {type(exc).__name__}: {str(exc)}",
        do_tre_ms=0.0,
        muc="ERROR",
        ma_yeu_cau=ma_yeu_cau,
        vet_loi=vet_loi,
    )
    # Trả ra ngoài CHỈ có mã lỗi và ma_yeu_cau
    headers = {"X-Ma-Yeu-Cau": ma_yeu_cau, "X-Request-ID": ma_yeu_cau}
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "ma": 500,
            "ma_yeu_cau": ma_yeu_cau,
        },
        headers=headers,
    )


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


class ThongTinToi(BaseModel):
    """Mô hình dữ liệu trả về cho endpoint GET /toi."""

    id: str = Field(description="Mã định danh người dùng")
    email: str = Field(description="Địa chỉ email người dùng")
    bac: str = Field(description="Bậc tài khoản ('free' hoặc 'pro')")
    da_dung_gio: int = Field(description="Số lượt yêu cầu đã thực hiện trong 1 giờ qua")
    han_muc_gio: int = Field(description="Hạn mức số lượt yêu cầu tối đa trong 1 giờ")
    so_luot_con_lai_gio: int = Field(description="Số lượt yêu cầu còn lại trong giờ")
    da_tieu_ngay_usd: float = Field(description="Tổng chi phí đã tiêu hôm nay (USD)")
    han_muc_chi_phi_ngay_usd: float = Field(description="Hạn mức chi phí tối đa hôm nay (USD)")
    chi_phi_con_lai_ngay_usd: float = Field(description="Chi phí còn lại hôm nay (USD)")


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
@app.get("/", include_in_schema=False)
async def trang_chu():
    """Endpoint gốc phục vụ giao diện web hoặc thông tin dịch vụ."""
    tap_tin_index = THU_MUC_WEB / "index.html"
    if tap_tin_index.exists():
        return FileResponse(tap_tin_index)
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

    headers_khong_cache = {"Cache-Control": "no-cache, no-store, must-revalidate"}

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
            headers=headers_khong_cache,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "trang_thai": "san_sang",
            "dich_vu": "Chatbot-EVN",
            "co_so_du_lieu": "san_sang",
            "so_tang_mo_hinh_kha_dung": so_tang_kha_dung,
        },
        headers=headers_khong_cache,
    )


@app.get("/chi-phi")
async def xem_chi_phi():
    """Endpoint trả về chi phí hôm nay, ngân sách ngày, phân rã theo tầng và tỷ lệ rơi tầng (Prompt 6)."""
    return lay_thong_ke_chi_phi_ngay()


@app.get("/toi", response_model=ThongTinToi)
async def xem_thong_tin_toi(
    request: Request,
    nguoi_dung: NguoiDung = Depends(lay_nguoi_dung_hien_tai),
):
    """Trả về thông tin người dùng hiện tại: bậc, đã dùng bao nhiêu trong giờ này, đã tiêu bao nhiêu hôm nay, hạn mức còn lại.

    Kiểm tra ba tầng hạn mức theo đúng thứ tự (rẻ trước, đắt sau):
    1. Theo địa chỉ IP (chặn dồn dập, áp dụng cả với yêu cầu chưa xác thực)
    2. Theo người dùng mỗi giờ (HAN_MUC_MOI_NGUOI_GIO, bậc pro nhân hệ số)
    3. Theo chi phí ngày của từng người dùng (chặn tiêu quá nhiều dù chưa chạm ngân sách tổng)
    """
    ip_client = lay_dia_chi_ip(request)

    # 1. Kiểm tra và ghi nhận 3 tầng hạn mức
    kiem_tra_ba_tang_han_muc(
        ip=ip_client,
        nguoi_dung_id=nguoi_dung.id,
        bac=nguoi_dung.bac,
        ghi_nhan=True,
    )

    # 2. Lấy thống kê mức sử dụng
    thong_tin = lay_thong_tin_nguoi_dung_hien_tai(
        nguoi_dung_id=nguoi_dung.id,
        bac=nguoi_dung.bac,
    )

    return ThongTinToi(
        id=nguoi_dung.id,
        email=nguoi_dung.email,
        bac=nguoi_dung.bac,
        da_dung_gio=thong_tin["da_dung_gio"],
        han_muc_gio=thong_tin["han_muc_gio"],
        so_luot_con_lai_gio=thong_tin["so_luot_con_lai_gio"],
        da_tieu_ngay_usd=thong_tin["da_tieu_ngay_usd"],
        han_muc_chi_phi_ngay_usd=thong_tin["han_muc_chi_phi_ngay_usd"],
        chi_phi_con_lai_ngay_usd=thong_tin["chi_phi_con_lai_ngay_usd"],
    )


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
    nguoi_dung_id, _ = lay_dinh_danh_va_bac(request)
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
    nguoi_dung_id, _ = lay_dinh_danh_va_bac(request)
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
    nguoi_dung_id, _ = lay_dinh_danh_va_bac(request)
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
    ip_client = lay_dia_chi_ip(request)
    nguoi_dung_id, bac = lay_dinh_danh_va_bac(request)
    dat_nguoi_dung_id(nguoi_dung_id)

    # Chặng 2: kiem_tra_han_muc
    t_hm = time.perf_counter()
    kiem_tra_ba_tang_han_muc(
        ip=ip_client,
        nguoi_dung_id=nguoi_dung_id,
        bac=bac,
        ghi_nhan=True,
    )
    kiem_tra_ngan_sach()
    do_tre_hm = round((time.perf_counter() - t_hm) * 1000, 2)
    ghi_kiem_tra_han_muc(nguoi_dung_id=nguoi_dung_id, bac=bac, do_tre_ms=do_tre_hm)

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

    # Lớp 1: Kiểm tra đầu vào (độ dài ký tự và phát hiện tiêm lời nhắc)
    kiem_tra_dau_vao(van_ban_user)

    # Lớp 2: Điểm móc kiểm duyệt đầu vào (chỗ cắm dịch vụ kiểm duyệt khi cần)
    kd_vao = await kiem_duyet_dau_vao(van_ban_user)
    if not kd_vao.hop_le:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=kd_vao.ly_do or "Nội dung yêu cầu vi phạm chính sách kiểm duyệt.",
        )
    van_ban_user = kd_vao.van_ban

    # Lớp 3: Củng cố lời nhắc hệ thống - đóng khung ranh giới câu hỏi người dùng
    van_ban_gui_llm = dong_khung_noi_dung_nguoi_dung(van_ban_user)

    # 4. Dựng ngữ cảnh có lịch sử cắt tỉa an toàn theo cặp
    tin_nhan_gui_llm = dung_ngu_canh(
        hoi_thoai_id=hoi_thoai_id,
        tin_nhan_moi=van_ban_gui_llm,
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
                    # Lớp 2: Điểm móc kiểm duyệt đầu ra (chỗ cắm dịch vụ kiểm duyệt khi cần)
                    cau_tra_loi_cuoi = manh.noi_dung or van_ban_tich_luy
                    kd_ra = await kiem_duyet_dau_ra(cau_tra_loi_cuoi)
                    cau_tra_loi_cuoi = kd_ra.van_ban

                    # Chặng 5: luu_hoi_thoai (Lớp 1: Che dữ liệu cá nhân PII trước khi lưu DB)
                    t_db = time.perf_counter()
                    try:
                        if van_ban_user:
                            van_ban_user_da_che = che_du_lieu_ca_nhan(van_ban_user)
                            luu_tin_nhan(
                                hoi_thoai_id=hoi_thoai_id,
                                vai_tro="user",
                                noi_dung=van_ban_user_da_che,
                            )
                        cau_tra_loi_da_che = che_du_lieu_ca_nhan(cau_tra_loi_cuoi)
                        luu_tin_nhan(
                            hoi_thoai_id=hoi_thoai_id,
                            vai_tro="assistant",
                            noi_dung=cau_tra_loi_da_che,
                            tang_phuc_vu=manh.tang_phuc_vu,
                            token_uoc_tinh=manh.token_ra,
                        )
                        da_luu_tin_nhan = True
                        do_tre_db = round((time.perf_counter() - t_db) * 1000, 2)
                        ghi_luu_hoi_thoai(hoi_thoai_id=hoi_thoai_id, do_tre_ms=do_tre_db)
                    except Exception as e_db:
                        logger.error(f"[Chat Stream] Lỗi khi lưu tin nhắn vào CSDL: {e_db}")

                    # Chặng 4: goi_mo_hinh
                    ghi_goi_mo_hinh(
                        tang=manh.tang_phuc_vu or 1,
                        model=manh.ten_model or "",
                        token_vao=manh.token_vao,
                        token_ra=manh.token_ra,
                        chi_phi_usd=manh.chi_phi_usd,
                        so_lan_thu=manh.so_lan_thu,
                        danh_sach_tang_da_hong=manh.danh_sach_tang_da_hong,
                        do_tre_ms=manh.do_tre_ms,
                    )

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


@app.get("/chat/stream")
async def chat_stream_get(
    request: Request,
    tin_nhan: str = Query(..., description="Nội dung tin nhắn"),
    hoi_thoai_id: Optional[str] = Query(default=None, description="Mã định danh phiên hội thoại"),
):
    """Bản GET của SSE stream hỗ trợ trực tiếp trình duyệt EventSource."""
    yeu_cau = YeuCauChatStream(tin_nhan=tin_nhan, hoi_thoai_id=hoi_thoai_id)
    return await chat_stream(yeu_cau, request)


# ---------------------------------------------------------------------------
# POST /chat: Bản không phát theo dòng cho máy-với-máy
# ---------------------------------------------------------------------------
@app.post("/chat", response_model=PhanHoiChat)
async def chat_dong_bo(yeu_cau: YeuCauChat, request: Request):
    """Bản chat không phát theo dòng dùng cho tích hợp máy-với-máy (M2M).

    Trả về đầy đủ siêu dữ liệu cuộc gọi: tầng phục vụ, model, token, chi phí, độ trễ.
    """
    ip_client = lay_dia_chi_ip(request)
    nguoi_dung_id, bac = lay_dinh_danh_va_bac(request)
    dat_nguoi_dung_id(nguoi_dung_id)

    # Chặng 2: kiem_tra_han_muc
    t_hm = time.perf_counter()
    kiem_tra_ba_tang_han_muc(
        ip=ip_client,
        nguoi_dung_id=nguoi_dung_id,
        bac=bac,
        ghi_nhan=True,
    )
    kiem_tra_ngan_sach()
    do_tre_hm = round((time.perf_counter() - t_hm) * 1000, 2)
    ghi_kiem_tra_han_muc(nguoi_dung_id=nguoi_dung_id, bac=bac, do_tre_ms=do_tre_hm)

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

    # Lớp 1: Kiểm tra đầu vào (độ dài ký tự và phát hiện tiêm lời nhắc)
    kiem_tra_dau_vao(van_ban_user)

    # Lớp 2: Điểm móc kiểm duyệt đầu vào (chỗ cắm dịch vụ kiểm duyệt khi cần)
    kd_vao = await kiem_duyet_dau_vao(van_ban_user)
    if not kd_vao.hop_le:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=kd_vao.ly_do or "Nội dung yêu cầu vi phạm chính sách kiểm duyệt.",
        )
    van_ban_user = kd_vao.van_ban

    # Lớp 3: Củng cố lời nhắc hệ thống - đóng khung ranh giới câu hỏi người dùng
    van_ban_gui_llm = dong_khung_noi_dung_nguoi_dung(van_ban_user)

    # 4. Dựng ngữ cảnh hội thoại (Chặng 3: dung_ngu_canh được ghi nhận tự động trong dung_ngu_canh)
    tin_nhan_gui_llm = dung_ngu_canh(
        hoi_thoai_id=hoi_thoai_id,
        tin_nhan_moi=van_ban_gui_llm,
    )

    # Chuẩn bị tham số
    tham_so: Dict[str, Any] = {"nguoi_dung_id": nguoi_dung_id}
    if yeu_cau.temperature is not None:
        tham_so["temperature"] = yeu_cau.temperature
    if yeu_cau.max_tokens is not None:
        tham_so["max_tokens"] = yeu_cau.max_tokens
    if isinstance(yeu_cau.tuy_chon, dict):
        tham_so.update(yeu_cau.tuy_chon)

    # 5. Gọi mô hình qua bộ định tuyến
    ket_qua = await goi_mo_hinh(
        tin_nhan=tin_nhan_gui_llm,
        phat_theo_dong=False,
        **tham_so,
    )

    # Chặng 4: goi_mo_hinh
    ghi_goi_mo_hinh(
        tang=ket_qua.tang_phuc_vu,
        model=ket_qua.ten_model,
        token_vao=ket_qua.token_vao,
        token_ra=ket_qua.token_ra,
        chi_phi_usd=ket_qua.chi_phi_usd,
        so_lan_thu=ket_qua.so_lan_thu,
        danh_sach_tang_da_hong=ket_qua.danh_sach_tang_da_hong,
        do_tre_ms=ket_qua.do_tre_ms,
    )

    cau_tra_loi = str(ket_qua.noi_dung or "")

    # Lớp 2: Điểm móc kiểm duyệt đầu ra (chỗ cắm dịch vụ kiểm duyệt khi cần)
    kd_ra = await kiem_duyet_dau_ra(cau_tra_loi)
    cau_tra_loi = kd_ra.van_ban

    # Chặng 5: luu_hoi_thoai (Lớp 1: Che dữ liệu cá nhân PII trước khi lưu DB)
    t_db = time.perf_counter()
    try:
        if van_ban_user:
            van_ban_user_da_che = che_du_lieu_ca_nhan(van_ban_user)
            luu_tin_nhan(
                hoi_thoai_id=hoi_thoai_id,
                vai_tro="user",
                noi_dung=van_ban_user_da_che,
            )
        cau_tra_loi_da_che = che_du_lieu_ca_nhan(cau_tra_loi)
        luu_tin_nhan(
            hoi_thoai_id=hoi_thoai_id,
            vai_tro="assistant",
            noi_dung=cau_tra_loi_da_che,
            tang_phuc_vu=ket_qua.tang_phuc_vu,
            token_uoc_tinh=ket_qua.token_ra,
        )
    except Exception as e_db:
        logger.error(f"[Chat M2M] Lỗi khi lưu tin nhắn vào CSDL: {e_db}")
    do_tre_db = round((time.perf_counter() - t_db) * 1000, 2)
    ghi_luu_hoi_thoai(hoi_thoai_id=hoi_thoai_id, do_tre_ms=do_tre_db)

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


# ---------------------------------------------------------------------------
# Phục vụ thư mục web tại đường dẫn gốc
# ---------------------------------------------------------------------------
if THU_MUC_WEB.exists():
    app.mount("/", StaticFiles(directory=str(THU_MUC_WEB), html=True), name="web")
