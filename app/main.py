"""Điểm khởi chạy ứng dụng FastAPI cho Chatbot EVN."""

import json
import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from app.config import lay_cau_hinh
from app.llm.router import goi_mo_hinh_theo_dong

# Nạp biến môi trường từ tệp .env khi khởi chạy ứng dụng
load_dotenv()

logger = logging.getLogger(__name__)

# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="Chatbot EVN API",
    description="Hệ thống AI Chatbot phục vụ nghiệp vụ EVN với chuỗi dự phòng đa mô hình",
    version="0.1.0",
)


class YeuCauChatStream(BaseModel):
    """Mô hình dữ liệu cho yêu cầu chat phát theo dòng."""

    tin_nhan: Optional[Union[str, List[Dict[str, Any]]]] = None
    messages: Optional[List[Dict[str, Any]]] = None
    prompt: Optional[str] = None
    noi_dung: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tuy_chon: Optional[Dict[str, Any]] = None


def chuan_hoa_tin_nhan(yeu_cau: YeuCauChatStream) -> list[dict]:
    """Chuẩn hoá dữ liệu đầu vào thành danh sách tin nhắn [{'role': '...', 'content': '...'}]"""
    raw = yeu_cau.tin_nhan or yeu_cau.messages or yeu_cau.prompt or yeu_cau.noi_dung
    if isinstance(raw, list):
        return raw
    elif isinstance(raw, str):
        return [{"role": "user", "content": raw}]
    return [{"role": "user", "content": ""}]


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


@app.post("/chat/stream")
async def chat_stream(request: Request):
    """Endpoint phát phản hồi theo dòng Server-Sent Events (SSE).

    Hỗ trợ cả JSON chuẩn lẫn các chuỗi bị lỗi thoát dấu ngoặc kép trên terminal Windows/PowerShell.
    Trả về chuỗi sự kiện với header X-Accel-Buffering: no và Cache-Control: no-cache
    để vô hiệu hoá tính năng gom đệm của các proxy ngược (như Nginx).
    Mỗi sự kiện là một dòng data: chứa JSON với 3 loại sự kiện: 'manh', 'xong', 'loi'.
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8", errors="replace").strip()

    tin_nhan = []
    tham_so: Dict[str, Any] = {}

    # 1. Thử phân tích JSON chuẩn
    try:
        du_lieu = json.loads(body_str) if body_str else {}
        if isinstance(du_lieu, dict):
            raw = (
                du_lieu.get("tin_nhan")
                or du_lieu.get("messages")
                or du_lieu.get("prompt")
                or du_lieu.get("noi_dung")
            )
            if isinstance(raw, list):
                tin_nhan = raw
            elif isinstance(raw, str):
                tin_nhan = [{"role": "user", "content": raw}]
            if du_lieu.get("temperature") is not None:
                tham_so["temperature"] = du_lieu["temperature"]
            if du_lieu.get("max_tokens") is not None:
                tham_so["max_tokens"] = du_lieu["max_tokens"]
            if isinstance(du_lieu.get("tuy_chon"), dict):
                tham_so.update(du_lieu["tuy_chon"])
        elif isinstance(du_lieu, list):
            tin_nhan = du_lieu
    except Exception:
        pass

    # 2. Xử lý trường hợp chuỗi bị lỗi escape dấu ngoặc kép trên PowerShell (ví dụ: {tin_nhan:Giải thích...})
    if not tin_nhan and body_str:
        import re

        m = re.search(
            r'(?:tin_nhan|prompt|noi_dung|messages?)\s*[:=]\s*["\']?(.*?)["\']?\s*\}?\s*$',
            body_str,
            re.DOTALL | re.IGNORECASE,
        )
        if m:
            nd = m.group(1).strip().rstrip('"\'}')
            tin_nhan = [{"role": "user", "content": nd}]
        else:
            nd = body_str.strip().lstrip("{").rstrip("}").strip()
            tin_nhan = [{"role": "user", "content": nd}]

    if not tin_nhan:
        tin_nhan = [{"role": "user", "content": ""}]

    async def tao_su_kien_sse():
        van_ban_tich_luy = ""
        try:
            async for manh in goi_mo_hinh_theo_dong(tin_nhan, **tham_so):
                if manh.loai == "manh":
                    van_ban_tich_luy += manh.doan_van_ban
                    du_lieu = {
                        "loai": "manh",
                        "su_kien": "manh",
                        "doan_van_ban": manh.doan_van_ban,
                        "noi_dung": manh.doan_van_ban,
                    }
                    yield f"data: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"
                elif manh.loai == "xong":
                    du_lieu = {
                        "loai": "xong",
                        "su_kien": "xong",
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
                    du_lieu = {
                        "loai": "loi",
                        "su_kien": "loi",
                        "thong_diep_loi": manh.thong_diep_loi,
                        "loi": manh.thong_diep_loi,
                        "van_ban_da_nhan": manh.van_ban_da_nhan,
                    }
                    yield f"data: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"[Chat Stream Endpoint] Lỗi xảy ra trong luồng SSE: {e}")
            du_lieu_loi = {
                "loai": "loi",
                "su_kien": "loi",
                "thong_diep_loi": str(e),
                "loi": str(e),
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


