"""Bộ kiểm thử cho module chi phí, trần ngân sách và giám sát tỷ lệ rơi tầng (app/llm/chi_phi.py).

Bao gồm các kịch bản kiểm thử:
1. Hàm uoc_tinh_chi_phi tính đúng theo bảng giá config/models.yaml cho các tầng.
2. Ghi nhận lượt gọi vào bảng luot_goi và kiểm tra sự tồn tại của chỉ mục.
3. Kiểm tra trần ngân sách: dưới ngân sách, đạt 80% (cảnh báo log), vượt 100% (từ chối 503, không gọi mô hình).
4. Giám sát tỷ lệ rơi tầng 1 trong 1 giờ qua (dưới 20% bình thường, vượt 20% cảnh báo kèm lý do hỏng tầng 1).
5. OpenRouter Auto: đọc model thực tế từ phản hồi, ghi log và đánh dấu ước tính thô.
6. Endpoint GET /chi-phi trả về đầy đủ các trường yêu cầu.
7. Endpoint POST /chat/stream từ chối với HTTP 503 khi vượt trần ngân sách.
"""

from datetime import datetime, timedelta, timezone
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, LuotGoi, dat_engine, lay_phien_db
from app.llm.chi_phi import (
    VuotNganSachError,
    cap_nhat_ly_do_hong_tang_1,
    ghi_nhan_luot_goi,
    kiem_tra_ngan_sach,
    lay_thong_ke_chi_phi_ngay,
    lay_tong_chi_phi_hom_nay,
    tinh_ty_le_roi_tang_1h,
    uoc_tinh_chi_phi,
)
from app.llm.router import goi_mo_hinh
from app.main import app


from sqlalchemy.pool import StaticPool


@pytest.fixture(autouse=True)
def thiet_lap_sqlite_in_memory(monkeypatch):
    """Sử dụng cơ sở dữ liệu SQLite in-memory biệt lập với StaticPool cho từng test case."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    dat_engine(test_engine)

    # Đặt khoá API giả lập
    monkeypatch.setenv("GOOGLE_API_KEY", "mock-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    monkeypatch.setenv("NGAN_SACH_NGAY_USD", "10.0")

    yield

    Base.metadata.drop_all(bind=test_engine)


def tao_mock_phan_hoi(
    noi_dung: str = "Xin chào",
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
    model: str = "gemini/gemini-3.6-flash",
) -> MagicMock:
    """Tạo đối tượng phản hồi giả lập cho litellm.acompletion."""
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = noi_dung
    resp.choices = [choice]
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    resp.model = model
    return resp


def test_uoc_tinh_chi_phi_cac_tang():
    """Hàm uoc_tinh_chi_phi lấy giá từ config/models.yaml và tính toán chính xác."""
    # Tầng 1 (gemini): giá vào 0.075 USD/1M, giá ra 0.30 USD/1M
    chi_phi_tang_1 = uoc_tinh_chi_phi(1, token_vao=1_000_000, token_ra=1_000_000)
    assert chi_phi_tang_1 == pytest.approx(0.375, rel=1e-6)

    # Tầng 1 theo tên
    chi_phi_tang_gemini = uoc_tinh_chi_phi("gemini", token_vao=1000, token_ra=2000)
    assert chi_phi_tang_gemini == pytest.approx((1000 / 1e6) * 0.075 + (2000 / 1e6) * 0.30, rel=1e-6)

    # Tầng 2 (openrouter_auto): giá tham chiếu 0.20 và 0.80
    chi_phi_tang_2 = uoc_tinh_chi_phi("openrouter_auto", token_vao=1_000_000, token_ra=1_000_000)
    assert chi_phi_tang_2 == pytest.approx(1.0, rel=1e-6)

    # Tầng 3 (claude): giá 0.80 và 4.00
    chi_phi_tang_3 = uoc_tinh_chi_phi(3, token_vao=1_000_000, token_ra=1_000_000)
    assert chi_phi_tang_3 == pytest.approx(4.80, rel=1e-6)

    # Tầng 4 (openai): giá 0.15 và 0.60
    chi_phi_tang_4 = uoc_tinh_chi_phi(4, token_vao=1_000_000, token_ra=1_000_000)
    assert chi_phi_tang_4 == pytest.approx(0.75, rel=1e-6)


def test_ghi_nhan_luot_goi_va_chi_muc():
    """Kiểm tra ghi bản ghi vào bảng luot_goi và sự tồn tại của các chỉ mục bắt buộc."""
    with lay_phien_db() as phien:
        engine = phien.get_bind()
        inspector = inspect(engine)
        assert inspector is not None
        chi_muc = inspector.get_indexes("luot_goi")
        ten_chi_muc: list[str] = [idx.get("name") or "" for idx in chi_muc]

        # Kiểm tra chỉ mục trên thoi_diem và (nguoi_dung_id, thoi_diem)
        assert any("thoi_diem" in name for name in ten_chi_muc)
        assert any("nguoi_dung" in name for name in ten_chi_muc)

    # Ghi nhận một lượt gọi
    ban_ghi_id = ghi_nhan_luot_goi(
        tang=1,
        model="gemini/gemini-3.6-flash",
        token_vao=150,
        token_ra=350,
        chi_phi_usd=0.00012,
        do_tre_ms=120.5,
        thanh_cong=True,
        nguoi_dung_id="user_123",
        ghi_chu="test ghi chu",
    )
    assert ban_ghi_id is not None

    with lay_phien_db() as phien:
        bg = phien.get(LuotGoi, ban_ghi_id)
        assert bg is not None
        assert bg.tang == 1
        assert bg.model == "gemini/gemini-3.6-flash"
        assert bg.token_vao == 150
        assert bg.token_ra == 350
        assert bg.chi_phi_usd == pytest.approx(0.00012)
        assert bg.nguoi_dung_id == "user_123"
        assert bg.thanh_cong is True


def test_kiem_tra_ngan_sach_duoi_va_vuot(caplog):
    """Kiểm tra trần ngân sách: dưới ngân sách, cảnh báo 80%, và ném 503 khi vượt trần."""
    # 1. Ban đầu chi phí = 0 -> không lỗi
    chi_phi, ngan_sach = kiem_tra_ngan_sach()
    assert chi_phi == 0.0
    assert ngan_sach == 10.0

    # 2. Đạt 85% ngân sách ($8.5) -> ghi log WARNING mỗi lần kiểm tra
    ghi_nhan_luot_goi(
        tang=1,
        model="test",
        chi_phi_usd=8.5,
        thanh_cong=True,
    )
    with caplog.at_level(logging.WARNING):
        chi_phi, ngan_sach = kiem_tra_ngan_sach()
        assert chi_phi == pytest.approx(8.5)
        assert "đã đạt 85.0% ngân sách ngày" in caplog.text

    # 3. Vượt 100% ngân sách ($10.5 >= $10.0) -> ném ngoại lệ VuotNganSachError (HTTP 503)
    ghi_nhan_luot_goi(
        tang=1,
        model="test",
        chi_phi_usd=2.0,
        thanh_cong=True,
    )
    with pytest.raises(VuotNganSachError) as exc_info:
        kiem_tra_ngan_sach()
    assert exc_info.value.status_code == 503
    assert "Hệ thống đã đạt giới hạn ngân sách hàng ngày" in str(exc_info.value)


@pytest.mark.asyncio
async def test_router_tu_choi_goi_khi_vuot_ngan_sach():
    """Khi vượt ngân sách ngày, router từ chối ngay lập tức và KHÔNG gọi mô hình."""
    # Ghi nhận chi phí vượt ngân sách ($11 > $10)
    ghi_nhan_luot_goi(
        tang=1,
        model="test",
        chi_phi_usd=11.0,
        thanh_cong=True,
    )

    with patch("app.llm.router.litellm.acompletion", new_callable=AsyncMock) as mock_call:
        with pytest.raises(VuotNganSachError):
            await goi_mo_hinh([{"role": "user", "content": "Chào bạn"}])

        # Khẳng định litellm KHÔNG hề bị gọi tới
        assert mock_call.call_count == 0


def test_giam_sat_ty_le_roi_tang_1h(caplog):
    """Tính tỷ lệ phần trăm số lượt không được tầng 1 phục vụ trong 1 giờ qua.

    Vượt 20% thì ghi nhật ký cảnh báo kèm lý do hỏng gần nhất của tầng 1.
    """
    cap_nhat_ly_do_hong_tang_1("Google Gemini trả mã lỗi 429 RateLimit")

    # Giả lập 10 lượt gọi: 7 lượt tầng 1 thành công, 3 lượt rơi xuống tầng 2 (tỷ lệ rơi = 30% > 20%)
    for _ in range(7):
        ghi_nhan_luot_goi(tang=1, model="gemini", chi_phi_usd=0.001, thanh_cong=True)
    for _ in range(3):
        ghi_nhan_luot_goi(tang=2, model="openrouter/auto", chi_phi_usd=0.005, thanh_cong=True)

    with caplog.at_level(logging.WARNING):
        ty_le, ly_do = tinh_ty_le_roi_tang_1h()
        assert ty_le == 30.0
        assert "Google Gemini trả mã lỗi 429 RateLimit" in ly_do
        assert "CẢNH BÁO TỶ LỆ RƠI TẦNG" in caplog.text
        assert "30.0%" in caplog.text
        assert "Google Gemini trả mã lỗi 429 RateLimit" in caplog.text


@pytest.mark.asyncio
async def test_openrouter_auto_doc_model_thuc_te_va_uoc_tinh_tho(caplog):
    """Với openrouter_auto, đọc model thực tế từ phản hồi và đánh dấu ước tính thô."""
    # Mô phỏng tầng 1 thiếu khoá API để rơi xuống tầng 2 (openrouter_auto)
    with patch("app.llm.router.os.getenv") as mock_env, patch(
        "app.llm.router.litellm.acompletion", new_callable=AsyncMock
    ) as mock_call:
        mock_env.side_effect = lambda k: None if k == "GOOGLE_API_KEY" else "valid-key"

        # Giả lập phản hồi từ OpenRouter chứa model thực tế là meta-llama/llama-3-8b-instruct
        mock_call.return_value = tao_mock_phan_hoi(
            noi_dung="Chào từ OpenRouter Auto",
            prompt_tokens=50,
            completion_tokens=100,
            model="meta-llama/llama-3-8b-instruct",
        )

        with caplog.at_level(logging.INFO):
            ket_qua = await goi_mo_hinh([{"role": "user", "content": "Xin chào"}])

            assert ket_qua.tang_phuc_vu == 2
            assert ket_qua.ten_model == "meta-llama/llama-3-8b-instruct"
            # Kiểm tra ghi log thông báo ước tính thô
            assert "ước tính thô" in caplog.text

            # Kiểm tra cơ sở dữ liệu đã lưu bản ghi với model thực tế và ghi chú uoc_tinh_tho
            with lay_phien_db() as phien:
                bg = phien.query(LuotGoi).filter(LuotGoi.tang == 2).first()
                assert bg is not None
                assert bg.model == "meta-llama/llama-3-8b-instruct"
                assert bg.ghi_chu == "uoc_tinh_tho"


def test_endpoint_get_chi_phi():
    """Kiểm tra endpoint GET /chi-phi trả về đầy đủ các thông tin cần thiết."""
    client = TestClient(app)

    # Thêm một vài lượt gọi mẫu
    ghi_nhan_luot_goi(tang=1, model="gemini", chi_phi_usd=0.15, thanh_cong=True)
    ghi_nhan_luot_goi(tang=2, model="openrouter", chi_phi_usd=0.05, thanh_cong=True)

    resp = client.get("/chi-phi")
    assert resp.status_code == 200
    data = resp.json()

    assert "chi_phi_hom_nay_usd" in data
    assert "ngan_sach_ngay_usd" in data
    assert "phan_tram_da_dung" in data
    assert "phan_ra_theo_tang" in data
    assert "so_luot_theo_tang" in data
    assert "ty_le_roi_tang_1_gio_qua" in data

    assert data["chi_phi_hom_nay_usd"] == pytest.approx(0.20, rel=1e-4)
    assert data["phan_ra_theo_tang"]["1"] == pytest.approx(0.15, rel=1e-4)
    assert data["phan_ra_theo_tang"]["2"] == pytest.approx(0.05, rel=1e-4)
    assert data["so_luot_theo_tang"]["1"] == 1
    assert data["so_luot_theo_tang"]["2"] == 1


def test_endpoint_chat_stream_tu_choi_khi_vuot_ngan_sach():
    """Kiểm tra endpoint POST /chat/stream từ chối với HTTP 503 khi đã vượt trần ngân sách."""
    client = TestClient(app)

    # Đưa chi phí vượt trần ngân sách ($12 > $10)
    ghi_nhan_luot_goi(tang=1, model="gemini", chi_phi_usd=12.0, thanh_cong=True)

    resp = client.post("/chat/stream", json={"tin_nhan": "Xin chào"})
    assert resp.status_code == 503
    data = resp.json()
    assert "Hệ thống đã đạt giới hạn ngân sách hàng ngày" in data.get("detail", "")
