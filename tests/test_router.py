"""Bộ kiểm thử cho bộ định tuyến mô hình app/llm/router.py.

Toàn bộ kiểm thử sử dụng giả lập (mock), tuyệt đối không thực hiện cuộc gọi mạng thật:
1. Tầng 1 thành công thì không chạm tới tầng 2.
2. Tầng 1 trả 429 liên tiếp thì rơi xuống tầng 2 và kết quả ghi tang_phuc_vu = 2.
3. Tầng 1 trả 401 thì KHÔNG thử lại, rơi tầng ngay.
4. Cả bốn tầng hỏng thì ném ngoại lệ có đủ bốn lý do.
5. Lỗi đầu vào (400) ném lỗi ngay, không rơi tầng.
6. Tầng thiếu khoá API được bỏ qua lặng lẽ.
7. Phát theo dòng (phat_theo_dong=True) thành công.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from litellm.exceptions import (
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.config import doc_cau_hinh_models
from app.llm.router import (
    KetQuaGoi,
    LoiDauVaoError,
    TatCaTangDeuHongError,
    goi_mo_hinh,
)


def tao_mock_phan_hoi(
    noi_dung: str = "Xin chào", prompt_tokens: int = 10, completion_tokens: int = 20
) -> MagicMock:
    """Tạo đối tượng phản hồi giả lập cho litellm.acompletion (non-streaming)."""
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = noi_dung
    resp.choices = [choice]
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    return resp


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


@pytest.mark.asyncio
async def test_tang_1_thanh_cong_khong_cham_tang_2():
    """Tầng 1 thành công thì không chạm tới tầng 2."""
    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = tao_mock_phan_hoi("Chào bạn", 15, 30)

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        ket_qua = await goi_mo_hinh(tin_nhan)

        assert isinstance(ket_qua, KetQuaGoi)
        assert ket_qua.tang_phuc_vu == 1
        assert ket_qua.noi_dung == "Chào bạn"
        assert ket_qua.token_vao == 15
        assert ket_qua.token_ra == 30
        assert ket_qua.so_lan_thu == 1
        assert len(ket_qua.danh_sach_tang_da_hong) == 0
        assert ket_qua.chi_phi_usd > 0
        # Mock chỉ được gọi đúng 1 lần cho tầng 1; tầng 2 không hề bị chạm tới
        assert mock_call.call_count == 1
        call_kwargs = mock_call.call_args.kwargs
        assert "gemini" in call_kwargs["model"]


@pytest.mark.asyncio
async def test_tang_1_429_lien_tiep_roi_xuong_tang_2():
    """Tầng 1 trả 429 liên tiếp thì rơi xuống tầng 2 và kết quả ghi tang_phuc_vu = 2."""
    cau_hinh = doc_cau_hinh_models()
    so_lan_thu_lai = cau_hinh.cai_dat_chung.so_lan_thu_lai_moi_tang
    so_lan_goi_tang_1 = so_lan_thu_lai + 1  # 1 lần chính + N lần thử lại

    phan_hoi_thanh_cong = tao_mock_phan_hoi("Phản hồi từ tầng 2", 20, 40)
    loi_429 = RateLimitError("Rate limit exceeded", "google", "gemini-3.6-flash")

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        # Tầng 1 trả 429 cho tất cả các lần thử, tầng 2 thành công ở lần gọi đầu
        mock_call.side_effect = [loi_429] * so_lan_goi_tang_1 + [phan_hoi_thanh_cong]

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        ket_qua = await goi_mo_hinh(tin_nhan)

        assert ket_qua.tang_phuc_vu == 2
        assert ket_qua.noi_dung == "Phản hồi từ tầng 2"
        assert ket_qua.token_vao == 20
        assert ket_qua.token_ra == 40
        assert len(ket_qua.danh_sach_tang_da_hong) == 1
        assert ket_qua.danh_sach_tang_da_hong[0]["tang"] == 1
        assert "Lỗi tạm thời" in ket_qua.danh_sach_tang_da_hong[0]["ly_do"]
        # Tổng số lần gọi là: tầng 1 (so_lan_goi_tang_1) + tầng 2 (1 lần)
        assert mock_call.call_count == so_lan_goi_tang_1 + 1


@pytest.mark.asyncio
async def test_tang_1_401_khong_thu_lai_roi_tang_ngay():
    """Tầng 1 trả 401 thì KHÔNG thử lại, rơi tầng ngay."""
    phan_hoi_thanh_cong = tao_mock_phan_hoi("Phản hồi từ tầng 2", 10, 20)
    loi_401 = AuthenticationError("Invalid API key", "google", "gemini-3.6-flash")

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        # Tầng 1 trả 401 ngay lần đầu, tầng 2 thành công
        mock_call.side_effect = [loi_401, phan_hoi_thanh_cong]

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        ket_qua = await goi_mo_hinh(tin_nhan)

        assert ket_qua.tang_phuc_vu == 2
        assert ket_qua.noi_dung == "Phản hồi từ tầng 2"
        # Tầng 1 KHÔNG thử lại (chỉ gọi 1 lần) + tầng 2 gọi 1 lần = 2 lần
        assert mock_call.call_count == 2
        assert len(ket_qua.danh_sach_tang_da_hong) == 1
        assert ket_qua.danh_sach_tang_da_hong[0]["tang"] == 1
        assert "Lỗi vĩnh viễn" in ket_qua.danh_sach_tang_da_hong[0]["ly_do"]


@pytest.mark.asyncio
async def test_ca_bon_tang_hong_nem_ngoai_le_du_bon_ly_do():
    """Cả bốn tầng hỏng thì ném ngoại lệ có đủ bốn lý do."""
    import httpx

    req = httpx.Request("POST", "http://test")
    res_403 = httpx.Response(403, request=req)
    loi_401 = AuthenticationError("Sai khoá API", "google", "model1")
    loi_403 = PermissionDeniedError("Không có quyền", "openrouter", "model2", response=res_403)
    loi_404 = NotFoundError("Sai tên model", "model3", "anthropic")
    loi_500 = InternalServerError("Máy chủ quá tải", "openai", "model4")

    cau_hinh = doc_cau_hinh_models()
    so_lan_thu_lai = cau_hinh.cai_dat_chung.so_lan_thu_lai_moi_tang
    so_lan_500 = so_lan_thu_lai + 1

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        # Tầng 1: 401 (1 lần), Tầng 2: 403 (1 lần), Tầng 3: 404 (1 lần), Tầng 4: 500 (so_lan_500 lần)
        mock_call.side_effect = [loi_401, loi_403, loi_404] + [loi_500] * so_lan_500

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        with pytest.raises(TatCaTangDeuHongError) as exc_info:
            await goi_mo_hinh(tin_nhan)

        ngoai_le = exc_info.value
        assert len(ngoai_le.thong_tin_that_bai) == 4
        cac_tang_hong = [t["tang"] for t in ngoai_le.thong_tin_that_bai]
        assert cac_tang_hong == [1, 2, 3, 4]

        # Kiểm tra thông điệp ngoại lệ chứa thông tin của cả 4 tầng
        thong_diep = str(ngoai_le)
        for i in [1, 2, 3, 4]:
            assert f"Tầng {i}" in thong_diep


@pytest.mark.asyncio
async def test_loi_dau_vao_400_nem_ngay_khong_roi_tang():
    """Lỗi do đầu vào (400 lời nhắc quá dài, nội dung bị chặn): KHÔNG rơi tầng, ném lỗi lên trên ngay."""
    loi_400 = BadRequestError("Context window exceeded", "google", "gemini-3.6-flash")

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = loi_400

        tin_nhan = [{"role": "user", "content": "Tin nhắn rất dài..."}]
        with pytest.raises(LoiDauVaoError):
            await goi_mo_hinh(tin_nhan)

        # Chỉ gọi đúng 1 lần ở tầng 1, tuyệt đối không rơi xuống tầng 2, 3, 4
        assert mock_call.call_count == 1


@pytest.mark.asyncio
async def test_thieu_khoa_api_bo_qua_lang_le(monkeypatch):
    """Tầng nào thiếu khoá API trong môi trường thì bỏ qua lặng lẽ."""
    # Xoá khoá API của tầng 1 (GOOGLE_API_KEY)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    phan_hoi = tao_mock_phan_hoi("Phản hồi từ tầng 2", 10, 20)
    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = phan_hoi

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        ket_qua = await goi_mo_hinh(tin_nhan)

        # Tầng 1 bị bỏ qua lặng lẽ, phục vụ từ tầng 2
        assert ket_qua.tang_phuc_vu == 2
        assert len(ket_qua.danh_sach_tang_da_hong) == 1
        assert "Thiếu biến môi trường" in ket_qua.danh_sach_tang_da_hong[0]["ly_do"]


@pytest.mark.asyncio
async def test_phat_theo_dong_thanh_cong():
    """Kiểm tra gọi mô hình với phat_theo_dong=True phát ra các đoạn văn bản chính xác."""
    async def mock_stream_gen():
        for doan in ["Chào ", "bạn, ", "tôi là ", "Chatbot EVN."]:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = doan
            chunk.usage = None
            yield chunk

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_stream_gen()

        tin_nhan = [{"role": "user", "content": "Xin chào"}]
        ket_qua = await goi_mo_hinh(tin_nhan, phat_theo_dong=True)

        assert ket_qua.tang_phuc_vu == 1
        assert isinstance(ket_qua.noi_dung, AsyncIterator)
        cac_doan = []
        async for text in ket_qua.noi_dung:
            cac_doan.append(text)

        noi_dung_day_du = "".join(cac_doan)
        assert noi_dung_day_du == "Chào bạn, tôi là Chatbot EVN."
