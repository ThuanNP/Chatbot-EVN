"""Bộ kiểm thử cho tính năng phát theo dòng (Streaming) và chuỗi dự phòng.

Bao gồm:
1. Luồng phát ra ít nhất hai mảnh nội dung rồi tới mảnh xong, và mảnh xong chứa đủ siêu dữ liệu.
2. Tình huống khó 1: Lỗi trước khi phát mảnh đầu tiên -> rơi tầng bình thường.
3. Tình huống khó 2: Lỗi giữa chừng sau khi đã phát vài mảnh -> KHÔNG rơi tầng, dừng luồng và phát mảnh lỗi kèm văn bản đã nhận.
4. Tất cả 4 tầng lỗi trước mảnh đầu -> ném TatCaTangDeuHongError.
5. Lỗi đầu vào 400 trước mảnh đầu -> ném LoiDauVaoError ngay.
6. Endpoint POST /chat/stream trả về đúng chuẩn Server-Sent Events với các headers chống gom đệm.
7. Endpoint POST /chat/stream xử lý lỗi giữa chừng trả về sự kiện SSE loại 'loi'.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from litellm.exceptions import (
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.llm.router import (
    KetQuaGoi,
    LoiDauVaoError,
    ManhPhatRa,
    TatCaTangDeuHongError,
    goi_mo_hinh_theo_dong,
)
from app.main import app


@pytest.fixture(autouse=True)
def thiet_lap_moi_truong(monkeypatch):
    """Cung cấp khoá API giả lập cho toàn bộ 4 tầng trong môi trường test."""
    monkeypatch.setenv("GOOGLE_API_KEY", "mock-google-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-openrouter-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-openai-key")


@pytest.fixture(autouse=True)
def mock_asyncio_sleep():
    """Giả lập asyncio.sleep để các lần thử lại chạy ngay lập tức mà không phải chờ."""
    with patch("app.llm.router.asyncio.sleep", new_callable=AsyncMock) as m:
        yield m


def tao_chunk_stream(
    content: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    include_usage: bool = False,
) -> MagicMock:
    """Tạo một chunk giả lập cho litellm streaming."""
    chunk = MagicMock()
    if content:
        delta = MagicMock()
        delta.content = content
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]
    else:
        chunk.choices = []

    if include_usage:
        usage = MagicMock()
        usage.prompt_tokens = prompt_tokens
        usage.completion_tokens = completion_tokens
        chunk.usage = usage
    else:
        chunk.usage = None
    return chunk


@pytest.mark.asyncio
async def test_luong_phat_thanh_cong_it_nhat_hai_manh_va_manh_xong_du_sieu_du_lieu():
    """Kiểm chứng: luồng phát ra ít nhất hai mảnh nội dung rồi tới mảnh xong,

    và mảnh xong chứa đủ siêu dữ liệu như KetQuaGoi.
    """
    async def mock_stream():
        yield tao_chunk_stream("Chào ")
        yield tao_chunk_stream("bạn, ")
        yield tao_chunk_stream("tôi là EVN Chatbot.", prompt_tokens=15, completion_tokens=30, include_usage=True)

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_stream()

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        cac_manh: list[ManhPhatRa] = []
        async for manh in goi_mo_hinh_theo_dong(tin_nhan):
            cac_manh.append(manh)

        # 1. Kiểm tra có ít nhất hai mảnh nội dung
        manh_noi_dung = [m for m in cac_manh if m.loai == "manh"]
        assert len(manh_noi_dung) >= 2
        van_ban_ghep = "".join(m.doan_van_ban for m in manh_noi_dung)
        assert van_ban_ghep == "Chào bạn, tôi là EVN Chatbot."

        # 2. Kiểm tra mảnh cuối cùng là mảnh kết thúc (loai == 'xong')
        manh_ket_thuc = cac_manh[-1]
        assert manh_ket_thuc.loai == "xong"

        # 3. Mảnh xong chứa đủ siêu dữ liệu
        assert manh_ket_thuc.tang_phuc_vu == 1
        assert "gemini" in (manh_ket_thuc.ten_model or "")
        assert manh_ket_thuc.token_vao == 15
        assert manh_ket_thuc.token_ra == 30
        assert manh_ket_thuc.do_tre_ms >= 0.0
        assert manh_ket_thuc.chi_phi_usd > 0.0
        assert manh_ket_thuc.so_lan_thu == 1
        assert isinstance(manh_ket_thuc.danh_sach_tang_da_hong, list)
        assert len(manh_ket_thuc.danh_sach_tang_da_hong) == 0

        # Kiểm tra đối tượng ket_qua lồng bên trong
        assert isinstance(manh_ket_thuc.ket_qua, KetQuaGoi)
        assert manh_ket_thuc.ket_qua.noi_dung == "Chào bạn, tôi là EVN Chatbot."
        assert manh_ket_thuc.ket_qua.tang_phuc_vu == 1
        assert manh_ket_thuc.ket_qua.token_vao == 15
        assert manh_ket_thuc.ket_qua.token_ra == 30


@pytest.mark.asyncio
async def test_tinh_huong_1_loi_truoc_manh_dau_roi_xuong_tang_sau():
    """Tình huống 1: Nếu tầng hiện tại lỗi TRƯỚC khi phát ra mảnh đầu tiên:

    rơi xuống tầng sau bình thường, người dùng không thấy gì bất thường.
    """
    loi_429 = RateLimitError("Hết hạn ngạch tầng 1", "google", "gemini-3.6-flash")

    async def mock_stream_tang_2():
        yield tao_chunk_stream("Phản hồi ")
        yield tao_chunk_stream("từ tầng 2.", prompt_tokens=20, completion_tokens=25, include_usage=True)

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        # Tầng 1 thử 3 lần (1 lần chính + 2 lần thử lại) đều gặp lỗi 429 TRƯỚC khi phát mảnh nào,
        # sau đó Tầng 2 phục vụ thành công
        mock_call.side_effect = [loi_429, loi_429, loi_429, mock_stream_tang_2()]

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        cac_manh: list[ManhPhatRa] = []
        async for manh in goi_mo_hinh_theo_dong(tin_nhan):
            cac_manh.append(manh)

        # Người dùng KHÔNG nhận được bất kỳ mảnh lỗi nào
        cac_manh_loi = [m for m in cac_manh if m.loai == "loi"]
        assert len(cac_manh_loi) == 0

        # Nhận nội dung từ tầng 2 bình thường
        manh_noi_dung = [m for m in cac_manh if m.loai == "manh"]
        assert len(manh_noi_dung) >= 2
        assert "".join(m.doan_van_ban for m in manh_noi_dung) == "Phản hồi từ tầng 2."

        # Mảnh xong ghi nhận tầng phục vụ là tầng 2
        manh_xong = cac_manh[-1]
        assert manh_xong.loai == "xong"
        assert manh_xong.tang_phuc_vu == 2
        assert len(manh_xong.danh_sach_tang_da_hong) == 1
        assert manh_xong.danh_sach_tang_da_hong[0]["tang"] == 1


@pytest.mark.asyncio
async def test_tinh_huong_2_loi_giua_chung_khong_roi_tang_phat_manh_loi():
    """Tình huống 2: Nếu tầng hiện tại lỗi GIỮA CHỪNG, sau khi đã phát ra vài mảnh:

    KHÔNG được rơi tầng rồi phát lại từ đầu, vì người dùng sẽ thấy câu trả lời bị viết lại.
    Thay vào đó kết thúc luồng và phát ra một mảnh lỗi kèm phần văn bản đã nhận được.
    Ghi nhật ký rõ tình huống này.
    """
    async def mock_stream_loi_giua_chung():
        yield tao_chunk_stream("Đây là phần đầu ")
        yield tao_chunk_stream("của câu trả lời ")
        # Đứt kết nối giữa chừng sau khi đã phát 2 mảnh
        raise ConnectionError("Mất kết nối mạng đột ngột giữa chừng")

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_stream_loi_giua_chung()

        tin_nhan = [{"role": "user", "content": "Hỏi một câu dài"}]
        cac_manh: list[ManhPhatRa] = []
        async for manh in goi_mo_hinh_theo_dong(tin_nhan):
            cac_manh.append(manh)

        # 1. Đã nhận các mảnh nội dung đầu tiên
        manh_noi_dung = [m for m in cac_manh if m.loai == "manh"]
        assert len(manh_noi_dung) >= 2
        van_ban_da_nhan = "".join(m.doan_van_ban for m in manh_noi_dung)
        assert van_ban_da_nhan == "Đây là phần đầu của câu trả lời "

        # 2. Mảnh cuối cùng PHẢI là mảnh lỗi
        manh_cuoi = cac_manh[-1]
        assert manh_cuoi.loai == "loi"
        assert "Mất kết nối mạng đột ngột giữa chừng" in (manh_cuoi.thong_diep_loi or "")
        assert manh_cuoi.van_ban_da_nhan == "Đây là phần đầu của câu trả lời "

        # 3. Tuyệt đối KHÔNG được gọi sang tầng 2 (mock_call chỉ gọi đúng 1 lần ở tầng 1)
        assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_ca_bon_tang_loi_truoc_manh_dau_nem_tat_ca_tang_deu_hong():
    """Cả 4 tầng đều lỗi trước mảnh đầu tiên -> ném ngoại lệ TatCaTangDeuHongError."""
    loi_500 = InternalServerError("Máy chủ quá tải", "test", "model")

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = loi_500

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        with pytest.raises(TatCaTangDeuHongError) as exc_info:
            async for _ in goi_mo_hinh_theo_dong(tin_nhan):
                pass

        assert len(exc_info.value.thong_tin_that_bai) == 4


@pytest.mark.asyncio
async def test_loi_dau_vao_400_truoc_manh_dau_nem_loi_ngay():
    """Lỗi dữ liệu đầu vào (400) trước mảnh đầu tiên -> ném LoiDauVaoError ngay, không rơi tầng."""
    loi_400 = BadRequestError("Lời nhắc quá dài vượt ngưỡng", "test", "model")

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = loi_400

        tin_nhan = [{"role": "user", "content": "Tin nhắn lỗi"}]
        with pytest.raises(LoiDauVaoError):
            async for _ in goi_mo_hinh_theo_dong(tin_nhan):
                pass

        # Chỉ thử đúng 1 lần, không rơi sang các tầng sau
        assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_endpoint_post_chat_stream_sse_headers_va_du_lieu():
    """Kiểm tra endpoint POST /chat/stream:

    - Đặt đúng header X-Accel-Buffering: no và Cache-Control: no-cache
    - Trả về các dòng sự kiện Server-Sent Events đúng format data: <JSON>
    - Chứa sự kiện 'manh' và kết thúc bằng 'xong'
    """
    async def mock_stream():
        yield tao_chunk_stream("Chào mừng ")
        yield tao_chunk_stream("bạn đến với ")
        yield tao_chunk_stream("EVN.", prompt_tokens=10, completion_tokens=20, include_usage=True)

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_stream()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/chat/stream",
                json={"tin_nhan": [{"role": "user", "content": "Xin chào"}]},
            )

            # 1. Kiểm tra mã trạng thái và Content-Type
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            # 2. Kiểm tra các header hạ tầng chống gom mảnh của proxy ngược
            assert response.headers.get("X-Accel-Buffering") == "no"
            assert "no-cache" in response.headers.get("Cache-Control", "")

            # 3. Đọc dữ liệu dòng SSE
            lines = response.text.strip().split("\n\n")
            su_kien_list = []
            for item in lines:
                if item.startswith("data: "):
                    du_lieu = json.loads(item[6:])
                    su_kien_list.append(du_lieu)

            # Ít nhất 2 sự kiện manh và 1 sự kiện xong
            cac_manh = [s for s in su_kien_list if s.get("loai") == "manh"]
            assert len(cac_manh) >= 2
            assert "".join(s["doan_van_ban"] for s in cac_manh) == "Chào mừng bạn đến với EVN."

            su_kien_xong = [s for s in su_kien_list if s.get("loai") == "xong"]
            assert len(su_kien_xong) == 1
            xong = su_kien_xong[0]
            assert xong["tang_phuc_vu"] == 1
            assert xong["token_vao"] == 10
            assert xong["token_ra"] == 20
            assert xong["chi_phi_usd"] > 0


@pytest.mark.asyncio
async def test_endpoint_post_chat_stream_loi_giua_chung_tra_ve_sse_loi():
    """Kiểm tra endpoint POST /chat/stream phát sự kiện 'loi' khi xảy ra lỗi giữa chừng."""
    async def mock_stream_loi():
        yield tao_chunk_stream("Đang trả lời... ")
        raise RuntimeError("Sự cố máy chủ nhà cung cấp khi đang phát")

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_stream_loi()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/chat/stream",
                json={"prompt": "Hỏi một câu"},
            )

            assert response.status_code == 200
            lines = response.text.strip().split("\n\n")
            su_kien_list = [json.loads(item[6:]) for item in lines if item.startswith("data: ")]

            cac_manh = [s for s in su_kien_list if s.get("loai") == "manh"]
            assert len(cac_manh) >= 1
            assert "".join(s["doan_van_ban"] for s in cac_manh) == "Đang trả lời... "

            cac_loi = [s for s in su_kien_list if s.get("loai") == "loi"]
            assert len(cac_loi) == 1
            assert "Sự cố máy chủ" in cac_loi[0]["thong_diep_loi"]
            assert cac_loi[0]["van_ban_da_nhan"] == "Đang trả lời... "
