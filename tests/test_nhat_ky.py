"""Bộ kiểm thử cho hệ thống nhật ký có cấu trúc và mã truy vết (app/core/nhat_ky.py).

Kiểm tra:
1. Sinh ma_yeu_cau đúng 12 ký tự hex; lưu trong ContextVar biệt lập giữa các luồng async.
2. Định dạng JSON một dòng: mọi dòng log là JSON hợp lệ, chứa đủ 7 trường cố định.
3. Chặng goi_mo_hinh chứa đủ 7 trường mở rộng: tang, model, token_vao, token_ra, chi_phi_usd, so_lan_thu, danh_sach_tang_da_hong.
4. Bảo mật dữ liệu: Không ghi nội dung tin nhắn người dùng vào nhật ký khi GHI_NOI_DUNG=false; chỉ ghi khi cờ bật.
5. Middleware HTTP: Tiếp nhận mã X-Ma-Yeu-Cau từ client hoặc tự sinh 12 ký tự; trả lại trong header X-Ma-Yeu-Cau.
6. Ghi nhận đúng 6 chặng chuẩn cho một yêu cầu POST /chat (http_vao, kiem_tra_han_muc, dung_ngu_canh, goi_mo_hinh, luu_hoi_thoai, http_ra).
7. Bộ xử lý ngoại lệ toàn cục: Ghi nguyên vết lỗi (traceback) vào nhật ký kèm ma_yeu_cau, phản hồi ra ngoài CHỈ có ma và ma_yeu_cau.
"""

from contextlib import asynccontextmanager
import io
import json
import logging
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, dat_engine
from app.core.han_muc import dat_lai_han_muc
from app.core.nhat_ky import (
    DinhDangNhatKyJson,
    dat_ma_yeu_cau,
    dat_nguoi_dung_id,
    duoc_phep_ghi_noi_dung,
    ghi_dung_ngu_canh,
    ghi_goi_mo_hinh,
    ghi_http_ra,
    ghi_http_vao,
    ghi_kiem_tra_han_muc,
    ghi_luu_hoi_thoai,
    ghi_nhat_ky,
    lay_ma_yeu_cau_hien_tai,
    lay_nguoi_dung_id_hien_tai,
    loc_truong_nhay_cam,
    sinh_ma_yeu_cau,
)
from app.llm.router import KetQuaGoi
from app.main import app


@pytest.fixture(autouse=True)
def thiet_lap_moi_truong_test(monkeypatch):
    """Thiết lập CSDL SQLite in-memory và cấu hình môi trường kiểm thử biệt lập."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    dat_engine(engine)

    monkeypatch.setenv("GOOGLE_API_KEY", "mock-google-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-openrouter-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-openai-key")
    monkeypatch.setenv("NGAN_SACH_NGAY_USD", "10.0")
    monkeypatch.setenv("HAN_MUC_MOI_NGUOI_GIO", "60")
    monkeypatch.setenv("GHI_NOI_DUNG", "false")

    dat_lai_han_muc()
    dat_ma_yeu_cau("")
    dat_nguoi_dung_id("khach")

    yield

    Base.metadata.drop_all(bind=engine)
    dat_lai_han_muc()


client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Kiểm tra sinh mã và ContextVars
# ---------------------------------------------------------------------------
def test_sinh_ma_yeu_cau_12_ky_tu():
    """Mã yêu cầu sinh ra phải đúng 12 ký tự hex (lowercase chữ số và ký tự hex)."""
    ma1 = sinh_ma_yeu_cau()
    ma2 = sinh_ma_yeu_cau()

    assert len(ma1) == 12
    assert len(ma2) == 12
    assert ma1 != ma2
    # Phải là chuỗi hex hợp lệ
    int(ma1, 16)
    int(ma2, 16)


@pytest.mark.asyncio
async def test_contextvars_biet_lap_giua_cac_tac_vu_async():
    """ContextVars ma_yeu_cau và nguoi_dung_id phải biệt lập hoàn toàn giữa các tác vụ async."""
    import asyncio

    ket_qua = {}

    async def tac_vu(ma: str, uid: str, delay: float):
        dat_ma_yeu_cau(ma)
        dat_nguoi_dung_id(uid)
        await asyncio.sleep(delay)
        ket_qua[ma] = (lay_ma_yeu_cau_hien_tai(), lay_nguoi_dung_id_hien_tai())

    await asyncio.gather(
        tac_vu("ma_111111111", "user_1", 0.02),
        tac_vu("ma_222222222", "user_2", 0.01),
        tac_vu("ma_333333333", "user_3", 0.03),
    )

    assert ket_qua["ma_111111111"] == ("ma_111111111", "user_1")
    assert ket_qua["ma_222222222"] == ("ma_222222222", "user_2")
    assert ket_qua["ma_333333333"] == ("ma_333333333", "user_3")


# ---------------------------------------------------------------------------
# 2. Kiểm tra bộ định dạng JSON một dòng
# ---------------------------------------------------------------------------
def test_dinh_dang_json_mot_dong_day_du_7_truong_co_dinh():
    """Mọi dòng nhật ký phải là JSON hợp lệ và chứa đủ 7 trường cố định bắt buộc."""
    formatter = DinhDangNhatKyJson()
    dat_ma_yeu_cau("req_test_123")
    dat_nguoi_dung_id("user_evn_test")

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=100,
        msg="Kiểm thử ghi nhật ký",
        args=(),
        exc_info=None,
    )
    record.chang = "http_vao"
    record.do_tre_ms = 12.34

    formatted = formatter.format(record)

    # 1. Phải là một dòng duy nhất (không có dấu xuống dòng chưa escape)
    assert "\n" not in formatted

    # 2. Phải là JSON hợp lệ
    data = json.loads(formatted)

    # 3. Chứa đủ 7 trường cố định
    cac_truong_bat_buoc = [
        "thoi_diem",
        "muc",
        "ma_yeu_cau",
        "nguoi_dung_id",
        "chang",
        "thong_diep",
        "do_tre_ms",
    ]
    for truong in cac_truong_bat_buoc:
        assert truong in data, f"Thiếu trường bắt buộc '{truong}' trong dòng JSON log"

    assert data["muc"] == "INFO"
    assert data["ma_yeu_cau"] == "req_test_123"
    assert data["nguoi_dung_id"] == "user_evn_test"
    assert data["chang"] == "http_vao"
    assert data["thong_diep"] == "Kiểm thử ghi nhật ký"
    assert data["do_tre_ms"] == 12.34


# ---------------------------------------------------------------------------
# 3. Kiểm tra chặng goi_mo_hinh có đủ 7 trường mở rộng
# ---------------------------------------------------------------------------
def test_chang_goi_mo_hinh_chua_du_7_truong_mo_rong():
    """Chặng goi_mo_hinh phải ghi thêm 7 trường: tang, model, token_vao, token_ra, chi_phi_usd, so_lan_thu, danh_sach_tang_da_hong."""
    formatter = DinhDangNhatKyJson()
    dat_ma_yeu_cau("call_llm_123")

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=120,
        msg="Gọi mô hình thành công",
        args=(),
        exc_info=None,
    )
    record.chang = "goi_mo_hinh"
    record.do_tre_ms = 245.50
    record.tang = 1
    record.model = "gemini/gemini-3.6-flash"
    record.token_vao = 35
    record.token_ra = 60
    record.chi_phi_usd = 0.000025
    record.so_lan_thu = 2
    record.danh_sach_tang_da_hong = [{"tang": 1, "ly_do": "Lỗi tạm thời lần 1"}]

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["chang"] == "goi_mo_hinh"
    assert data["tang"] == 1
    assert data["model"] == "gemini/gemini-3.6-flash"
    assert data["token_vao"] == 35
    assert data["token_ra"] == 60
    assert data["chi_phi_usd"] == 0.000025
    assert data["so_lan_thu"] == 2
    assert len(data["danh_sach_tang_da_hong"]) == 1
    assert data["danh_sach_tang_da_hong"][0]["tang"] == 1


# ---------------------------------------------------------------------------
# 4. Kiểm tra bảo vệ quyền riêng tư người dùng (GHI_NOI_DUNG)
# ---------------------------------------------------------------------------
def test_khong_ghi_noi_dung_tin_nhan_khi_co_tat(monkeypatch):
    """Khi GHI_NOI_DUNG=false, nội dung tin nhắn KHÔNG bị lọt vào nhật ký; chỉ ghi độ dài."""
    monkeypatch.setenv("GHI_NOI_DUNG", "false")
    assert duoc_phep_ghi_noi_dung() is False

    tin_nhan_bi_mat = "Mật khẩu bí mật của tài khoản EVN là 123456"
    du_lieu = {
        "tin_nhan": tin_nhan_bi_mat,
        "noi_dung": "Nội dung phản hồi không được lọt",
        "do_tre_ms": 10.0,
    }

    du_lieu_loc = loc_truong_nhay_cam(du_lieu)
    # Nội dung thô không còn
    assert "tin_nhan" not in du_lieu_loc
    assert "noi_dung" not in du_lieu_loc
    # Chỉ ghi độ dài
    assert du_lieu_loc["do_dai_tin_nhan"] == len(tin_nhan_bi_mat)
    assert du_lieu_loc["do_dai_noi_dung"] == len("Nội dung phản hồi không được lọt")
    assert du_lieu_loc["do_tre_ms"] == 10.0


def test_cho_phep_ghi_noi_dung_khi_bat_co_dev(monkeypatch):
    """Khi bật GHI_NOI_DUNG=true trong môi trường phát triển, cho phép giữ nội dung để gỡ lỗi."""
    monkeypatch.setenv("GHI_NOI_DUNG", "true")
    assert duoc_phep_ghi_noi_dung() is True

    du_lieu = {
        "tin_nhan": "Gỡ lỗi tin nhắn dev",
        "noi_dung": "Gỡ lỗi câu trả lời dev",
    }
    du_lieu_loc = loc_truong_nhay_cam(du_lieu)
    assert du_lieu_loc["tin_nhan"] == "Gỡ lỗi tin nhắn dev"
    assert du_lieu_loc["noi_dung"] == "Gỡ lỗi câu trả lời dev"


# ---------------------------------------------------------------------------
# 5. Kiểm tra Middleware và header X-Ma-Yeu-Cau
# ---------------------------------------------------------------------------
def test_middleware_sinh_ma_yeu_cau_12_ky_tu_va_tra_ve_header():
    """Nếu client không gửi mã yêu cầu, middleware tự sinh 12 ký tự và trả lại trong header X-Ma-Yeu-Cau."""
    resp = client.get("/health")
    assert resp.status_code == 200

    assert "X-Ma-Yeu-Cau" in resp.headers
    ma = resp.headers["X-Ma-Yeu-Cau"]
    assert len(ma) == 12
    # Đồng thời tương thích ngược X-Request-ID
    assert resp.headers.get("X-Request-ID") == ma


def test_middleware_tiep_nhan_ma_tu_phong_goi():
    """Nếu client gửi header X-Ma-Yeu-Cau hoặc X-Request-ID, middleware giữ nguyên mã đó để nối chuỗi truy vết."""
    ma_truyen_vao = "service_trace_001"
    resp = client.get("/health", headers={"X-Ma-Yeu-Cau": ma_truyen_vao})
    assert resp.status_code == 200
    assert resp.headers.get("X-Ma-Yeu-Cau") == ma_truyen_vao
    assert resp.headers.get("X-Request-ID") == ma_truyen_vao


# ---------------------------------------------------------------------------
# 6. Kiểm tra đủ 6 chặng chuẩn cho một yêu cầu POST /chat
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chuoi_sau_chang_chuan_cho_yeu_cau_post_chat(caplog):
    """Kiểm tra gọi POST /chat ghi nhận đúng 6 chặng: http_vao, kiem_tra_han_muc, dung_ngu_canh, goi_mo_hinh, luu_hoi_thoai, http_ra mang cùng ma_yeu_cau."""
    ket_qua_gia = KetQuaGoi(
        noi_dung="Điện lực EVN kính chào.",
        tang_phuc_vu=1,
        ten_model="gemini/gemini-3.6-flash",
        token_vao=20,
        token_ra=30,
        do_tre_ms=105.0,
        so_lan_thu=1,
        danh_sach_tang_da_hong=[],
        chi_phi_usd=0.00002,
    )

    with patch("app.main.goi_mo_hinh", new_callable=AsyncMock) as mock_goi:
        mock_goi.return_value = ket_qua_gia

        caplog.set_level(logging.INFO)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/chat",
                headers={"X-User-Id": "nhan_vien_evn"},
                json={"tin_nhan": "Thông tin giá điện sinh hoạt"},
            )

            assert resp.status_code == 200
            ma_yeu_cau = resp.headers.get("X-Ma-Yeu-Cau")
            assert ma_yeu_cau is not None
            assert len(ma_yeu_cau) == 12

            # Trích xuất các bản ghi nhật ký thuộc về mã yêu cầu này
            formatter = DinhDangNhatKyJson()
            cac_dong_log = []
            for r in caplog.records:
                dong_json_str = formatter.format(r)
                du_lieu = json.loads(dong_json_str)
                if du_lieu.get("ma_yeu_cau") == ma_yeu_cau:
                    cac_dong_log.append(du_lieu)

            # Thu thập danh sách các chặng đã đi qua
            cac_chang = [d.get("chang") for d in cac_dong_log]

            # Khẳng định phải có đủ 6 chặng chuẩn theo đúng yêu cầu
            assert "http_vao" in cac_chang, "Thiếu chặng http_vao"
            assert "kiem_tra_han_muc" in cac_chang, "Thiếu chặng kiem_tra_han_muc"
            assert "dung_ngu_canh" in cac_chang, "Thiếu chặng dung_ngu_canh"
            assert "goi_mo_hinh" in cac_chang, "Thiếu chặng goi_mo_hinh"
            assert "luu_hoi_thoai" in cac_chang, "Thiếu chặng luu_hoi_thoai"
            assert "http_ra" in cac_chang, "Thiếu chặng http_ra"

            # Kiểm tra chặng goi_mo_hinh có đầy đủ siêu dữ liệu
            log_model = next(d for d in cac_dong_log if d.get("chang") == "goi_mo_hinh")
            assert log_model["tang"] == 1
            assert log_model["model"] == "gemini/gemini-3.6-flash"
            assert log_model["token_vao"] == 20
            assert log_model["token_ra"] == 30
            assert log_model["chi_phi_usd"] == 0.00002

            # Khẳng định nội dung tin nhắn KHÔNG xuất hiện trong bất kỳ dòng log nào
            for dong in cac_dong_log:
                dong_str = json.dumps(dong)
                assert "Thông tin giá điện sinh hoạt" not in dong_str


# ---------------------------------------------------------------------------
# 7. Kiểm tra xử lý ngoại lệ toàn cục (HTTP 500)
# ---------------------------------------------------------------------------
def test_ngoai_le_toan_cuc_ghi_vet_loi_nhung_chi_tra_ma_va_ma_yeu_cau(caplog):
    """Khi có lỗi nội bộ (500), log ghi vết lỗi đầy đủ kèm ma_yeu_cau, còn phản hồi chỉ có 'ma' và 'ma_yeu_cau'."""
    caplog.set_level(logging.ERROR)
    client_500 = TestClient(app, raise_server_exceptions=False)

    # Giả lập lỗi bất ngờ trong hàm kiểm tra hạn mức
    with patch("app.main.kiem_tra_ba_tang_han_muc", side_effect=RuntimeError("Sự cố cơ sở hạ tầng nội bộ 2h sáng")):
        resp = client_500.post("/chat", json={"tin_nhan": "Gây lỗi thử nghiệm"})

        assert resp.status_code == 500
        ma_yeu_cau = resp.headers.get("X-Ma-Yeu-Cau")
        assert ma_yeu_cau is not None

        # 1. Phản hồi ngoài CHỈ chứa 'ma' và 'ma_yeu_cau'
        du_lieu_loi = resp.json()
        assert du_lieu_loi.get("ma") == 500
        assert du_lieu_loi.get("ma_yeu_cau") == ma_yeu_cau
        # Tuyệt đối không để lộ thông điệp lỗi kỹ thuật hoặc traceback ra client
        assert "Sự cố cơ sở hạ tầng" not in resp.text
        assert "Traceback" not in resp.text

        # 2. Nhật ký máy chủ phải ghi nguyên vết lỗi (traceback) kèm ma_yeu_cau
        formatter = DinhDangNhatKyJson()
        cac_dong_log_500 = []
        for r in caplog.records:
            d = json.loads(formatter.format(r))
            if d.get("ma_yeu_cau") == ma_yeu_cau and d.get("muc") == "ERROR":
                cac_dong_log_500.append(d)

        assert len(cac_dong_log_500) >= 1
        log_loi = cac_dong_log_500[0]
        assert "Sự cố cơ sở hạ tầng nội bộ 2h sáng" in log_loi.get("thong_diep", "") or "Sự cố" in log_loi.get("vet_loi", "")
        assert "vet_loi" in log_loi
        assert "Traceback" in log_loi["vet_loi"]
