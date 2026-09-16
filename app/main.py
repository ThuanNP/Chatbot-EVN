"""Điểm khởi chạy ứng dụng FastAPI cho Chatbot EVN."""

from fastapi import FastAPI
from app.config import lay_cau_hinh

# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="Chatbot EVN API",
    description="Hệ thống AI Chatbot phục vụ nghiệp vụ EVN với chuỗi dự phòng đa mô hình",
    version="0.1.0",
)


@app.get("/health")
async def kiem_tra_suc_khoe():
    """Kiểm tra tình trạng hoạt động của dịch vụ."""
    return {"trang_thai": "ok", "dich_vu": "Chatbot-EVN"}


@app.get("/")
async def trang_chu():
    """Endpoint gốc thông báo thông tin ứng dụng."""
    return {
        "ten": "Chatbot EVN",
        "phien_ban": "0.1.0",
        "mo_ta": "Hệ thống AI Chatbot EVN đang hoạt động.",
    }

