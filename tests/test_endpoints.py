"""Bộ kiểm thử cho toàn bộ các endpoint trong app/main.py.

Bao gồm:
1. GET /health tách biệt rõ ràng, không chạm cơ sở dữ liệu.
2. GET /ready kiểm tra CSDL và tầng mô hình khả dụng, trả 503 khi chưa sẵn sàng.
3. POST /chat cho máy-với-máy trả về đủ siêu dữ liệu.
4. POST /chat/stream phát SSE, sinh hội thoại mới và trả hoi_thoai_id ở sự kiện đầu tiên.
5. GET /hoi-thoai lấy danh sách hội thoại của người dùng hiện tại, phân trang, sắp xếp giảm dần.
6. GET /hoi-thoai/{id} trả về toàn bộ tin nhắn, trả 404 với hội thoại của người khác.
7. DELETE /hoi-thoai/{id} xoá hội thoại và tin nhắn, trả 404 với người khác.
8. Bộ xử lý lỗi thống nhất trả về {loi: {ma, thong_diep, ma_yeu_cau}}, không lộ chi tiết kỹ thuật.
"""

from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.chat.hoi_thoai import lay_hoi_thoai, lay_tin_nhan_hoi_thoai, luu_tin_nhan, tao_hoi_thoai
from app.core.database import Base, dat_engine, lay_phien_db
from app.core.han_muc import dat_lai_han_muc
from app.llm.router import KetQuaGoi
from app.main import app


@pytest.fixture(autouse=True)
def thiet_lap_sqlite_in_memory(monkeypatch):
    """Thiết lập SQLite in-memory biệt lập với StaticPool cho từng test case."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    dat_engine(test_engine)

    # Đặt khoá API giả lập và cấu hình
    monkeypatch.setenv("GOOGLE_API_KEY", "mock-google-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-openrouter-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-openai-key")
    monkeypatch.setenv("NGAN_SACH_NGAY_USD", "10.0")
    monkeypatch.setenv("HAN_MUC_MOI_NGUOI_GIO", "60")

    dat_lai_han_muc()

    yield

    Base.metadata.drop_all(bind=test_engine)
    dat_lai_han_muc()


client = TestClient(app)


def test_health_khong_cham_co_so_du_lieu():
    """Kiểm tra GET /health trả về 200, phản hồi tức thì và TUYỆT ĐỐI không chạm CSDL."""
    with patch("app.main.lay_phien_db") as mock_db:
        resp = client.get("/health")
        assert resp.status_code == 200
        du_lieu = resp.json()
        assert du_lieu["trang_thai"] == "ok"
        assert du_lieu["dich_vu"] == "Chatbot-EVN"
        # Khẳng định hàm CSDL không hề được gọi
        mock_db.assert_not_called()


def test_ready_khi_he_thong_san_sang():
    """Kiểm tra GET /ready trả về 200 khi CSDL kết nối tốt và có ít nhất 1 tầng khả dụng."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert "no-cache" in resp.headers.get("cache-control", "")
    assert "no-store" in resp.headers.get("cache-control", "")
    du_lieu = resp.json()
    assert du_lieu["trang_thai"] == "san_sang"
    assert du_lieu["co_so_du_lieu"] == "san_sang"
    assert du_lieu["so_tang_mo_hinh_kha_dung"] >= 1


def test_ready_tra_ve_503_khi_csdl_loi():
    """Kiểm tra GET /ready trả về 503 khi kết nối cơ sở dữ liệu gặp lỗi."""
    with patch("app.main.lay_phien_db", side_effect=Exception("Mất kết nối PostgreSQL")):
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert "no-cache" in resp.headers.get("cache-control", "")
        assert "no-store" in resp.headers.get("cache-control", "")
        du_lieu = resp.json()
        assert du_lieu["trang_thai"] == "chua_san_sang"
        assert "Cơ sở dữ liệu chưa sẵn sàng" in du_lieu["ly_do"]


def test_ready_tra_ve_503_khi_khong_co_tang_model_nao():
    """Kiểm tra GET /ready trả về 503 khi không có bất kỳ khoá API nào được cấu hình."""
    with patch("app.config.CauHinhHeThong.lay_khoa_api", return_value=""):
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert "no-cache" in resp.headers.get("cache-control", "")
        assert "no-store" in resp.headers.get("cache-control", "")
        du_lieu = resp.json()
        assert du_lieu["trang_thai"] == "chua_san_sang"
        assert "Chưa có tầng mô hình nào khả dụng" in du_lieu["ly_do"]


def test_giao_dien_phan_anh_ready_theo_thoi_gian_thuc():
    """Kiểm tra giao diện web index.html có logic kiểm tra GET /ready theo thời gian thực."""
    resp = client.get("/")
    assert resp.status_code == 200
    noi_dung = resp.text
    # Phải gọi endpoint /ready thay vì chỉ kiểm tra /health
    assert "/ready" in noi_dung
    # Phải có hàm kiểm tra tính sẵn sàng checkSystemReady
    assert "checkSystemReady" in noi_dung
    # Phải có trạng thái 'Kết nối: Gián đoạn' khi hệ thống không sẵn sàng
    assert "Kết nối: Gián đoạn" in noi_dung
    # Phải có trạng thái 'Kết nối: Sẵn sàng' khi hệ thống sẵn sàng
    assert "Kết nối: Sẵn sàng" in noi_dung
    # Phải có cơ chế polling định kỳ theo thời gian thực (setInterval)
    assert "setInterval(checkSystemReady" in noi_dung
    # Phải có các event listener online/offline/visibilitychange
    assert "window.addEventListener('online'" in noi_dung
    assert "window.addEventListener('offline'" in noi_dung



def test_get_hoi_thoai_danh_sach_va_phan_trang():
    """Kiểm tra GET /hoi-thoai: lấy danh sách của người dùng hiện tại, phân trang, sắp xếp cap_nhat_luc giảm dần."""
    # Tạo hội thoại cho user_a và user_b
    ht1 = tao_hoi_thoai(nguoi_dung_id="user_a", tieu_de="Hội thoại 1")
    ht2 = tao_hoi_thoai(nguoi_dung_id="user_a", tieu_de="Hội thoại 2")
    tao_hoi_thoai(nguoi_dung_id="user_b", tieu_de="Hội thoại của user B")

    # Gọi với header của user_a
    resp = client.get("/hoi-thoai", headers={"X-User-Id": "user_a"})
    assert resp.status_code == 200
    du_lieu = resp.json()
    assert len(du_lieu) == 2
    # Sắp xếp mới nhất lên đầu
    assert du_lieu[0]["id"] == ht2.id
    assert du_lieu[1]["id"] == ht1.id
    assert du_lieu[0]["nguoi_dung_id"] == "user_a"

    # Kiểm tra phân trang với gioi_han=1, bo_qua=1
    resp_pt = client.get("/hoi-thoai?gioi_han=1&bo_qua=1", headers={"X-User-Id": "user_a"})
    assert resp_pt.status_code == 200
    pt_data = resp_pt.json()
    assert len(pt_data) == 1
    assert pt_data[0]["id"] == ht1.id


def test_get_hoi_thoai_id_tra_404_voi_hoi_thoai_cua_nguoi_khac():
    """Kiểm tra GET /hoi-thoai/{id}:

    - Lấy toàn bộ tin nhắn thành công nếu đúng chủ sở hữu.
    - Trả về HTTP 404 nếu hội thoại thuộc về người khác.
    """
    ht_cua_a = tao_hoi_thoai(nguoi_dung_id="user_a", tieu_de="Bảo mật EVN")
    luu_tin_nhan(ht_cua_a.id, vai_tro="user", noi_dung="Câu hỏi của A")
    luu_tin_nhan(ht_cua_a.id, vai_tro="assistant", noi_dung="Trả lời cho A")

    # 1. user_a truy cập chính hội thoại của mình -> 200, lấy đủ 2 tin nhắn
    resp_a = client.get(f"/hoi-thoai/{ht_cua_a.id}", headers={"X-User-Id": "user_a"})
    assert resp_a.status_code == 200
    tin_nhan_a = resp_a.json()
    assert len(tin_nhan_a) == 2
    assert tin_nhan_a[0]["vai_tro"] == "user"
    assert tin_nhan_a[0]["noi_dung"] == "Câu hỏi của A"
    assert tin_nhan_a[1]["vai_tro"] == "assistant"

    # 2. user_b truy cập vào hội thoại của user_a -> BẮT BUỘC TRẢ VỀ 404
    resp_b = client.get(f"/hoi-thoai/{ht_cua_a.id}", headers={"X-User-Id": "user_b"})
    assert resp_b.status_code == 404
    du_lieu_loi = resp_b.json()
    assert "loi" in du_lieu_loi
    assert du_lieu_loi["loi"]["ma"] == 404

    # 3. Truy cập ID không tồn tại -> 404
    resp_khong_co = client.get("/hoi-thoai/ma-khong-ton-tai", headers={"X-User-Id": "user_a"})
    assert resp_khong_co.status_code == 404


def test_delete_hoi_thoai_id_va_cascade_tin_nhan():
    """Kiểm tra DELETE /hoi-thoai/{id}: xoá hội thoại, cascade tin nhắn, và trả 404 với người khác."""
    ht = tao_hoi_thoai(nguoi_dung_id="user_x", tieu_de="Cần xoá")
    luu_tin_nhan(ht.id, vai_tro="user", noi_dung="Tin nhắn 1")

    # Người khác (user_y) cố tình xoá -> 404
    resp_xoa_trom = client.delete(f"/hoi-thoai/{ht.id}", headers={"X-User-Id": "user_y"})
    assert resp_xoa_trom.status_code == 404

    # Chính chủ (user_x) xoá -> 200
    resp_xoa = client.delete(f"/hoi-thoai/{ht.id}", headers={"X-User-Id": "user_x"})
    assert resp_xoa.status_code == 200
    assert resp_xoa.json()["thanh_cong"] is True

    # Kiểm tra đã biến mất khỏi cơ sở dữ liệu
    assert lay_hoi_thoai(ht.id) is None
    assert len(lay_tin_nhan_hoi_thoai(ht.id)) == 0


@pytest.mark.asyncio
async def test_post_chat_may_voi_may_day_du_sieu_du_lieu():
    """Kiểm tra POST /chat: bản không stream cho máy-với-máy trả về đầy đủ siêu dữ liệu."""
    ket_qua_gia = KetQuaGoi(
        noi_dung="Chào bạn, đây là phản hồi M2M từ mô hình.",
        tang_phuc_vu=1,
        ten_model="gemini/gemini-3.6-flash",
        token_vao=25,
        token_ra=40,
        do_tre_ms=120.5,
        so_lan_thu=1,
        danh_sach_tang_da_hong=[],
        chi_phi_usd=0.000015,
    )

    with patch("app.main.goi_mo_hinh", new_callable=AsyncMock) as mock_goi:
        mock_goi.return_value = ket_qua_gia

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/chat",
                headers={"X-User-Id": "may_khach_01"},
                json={"tin_nhan": "Kiểm tra kết nối tích hợp"},
            )

            assert resp.status_code == 200
            du_lieu = resp.json()
            assert du_lieu["cau_tra_loi"] == "Chào bạn, đây là phản hồi M2M từ mô hình."
            assert du_lieu["tang_phuc_vu"] == 1
            assert du_lieu["model"] == "gemini/gemini-3.6-flash"
            assert du_lieu["token_vao"] == 25
            assert du_lieu["token_ra"] == 40
            assert du_lieu["chi_phi_usd"] == 0.000015
            assert du_lieu["do_tre_ms"] == 120.5
            assert du_lieu["so_lan_thu"] == 1
            assert "hoi_thoai_id" in du_lieu

            # Kiểm tra CSDL đã lưu lại cả 2 tin nhắn
            hoi_thoai_id = du_lieu["hoi_thoai_id"]
            cac_tn = lay_tin_nhan_hoi_thoai(hoi_thoai_id)
            assert len(cac_tn) == 2
            assert cac_tn[0].vai_tro == "user"
            assert cac_tn[0].noi_dung == "Kiểm tra kết nối tích hợp"
            assert cac_tn[1].vai_tro == "assistant"
            assert cac_tn[1].noi_dung == "Chào bạn, đây là phản hồi M2M từ mô hình."


@pytest.mark.asyncio
async def test_post_chat_stream_tra_hoi_thoai_id_o_su_kien_dau_tien_va_luu_db():
    """Kiểm tra POST /chat/stream:

    - Khi không có hoi_thoai_id, tự động tạo mới và trả về hoi_thoai_id trong sự kiện đầu tiên.
    - Phát các mảnh và mảnh xong chứa đủ siêu dữ liệu.
    - Lưu cả tin nhắn người dùng và câu trả lời vào CSDL.
    """
    from app.llm.router import ManhPhatRa

    ket_qua_cuoi = KetQuaGoi(
        noi_dung="Điện lực Việt Nam xin kính chào quý khách.",
        tang_phuc_vu=1,
        ten_model="gemini/gemini-3.6-flash",
        token_vao=12,
        token_ra=24,
        do_tre_ms=250.0,
        so_lan_thu=1,
        danh_sach_tang_da_hong=[],
        chi_phi_usd=0.00001,
    )

    async def mock_generator(*args, **kwargs):
        yield ManhPhatRa.tao_manh_noi_dung("Điện lực ")
        yield ManhPhatRa.tao_manh_noi_dung("Việt Nam ")
        yield ManhPhatRa.tao_manh_noi_dung("xin kính chào quý khách.")
        yield ManhPhatRa.tao_manh_ket_thuc(ket_qua_cuoi)

    with patch("app.main.goi_mo_hinh_theo_dong", side_effect=mock_generator):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/chat/stream",
                headers={"X-User-Id": "nguoi_dung_moi"},
                json={"tin_nhan": "EVN là gì?"},
            )

            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            assert resp.headers.get("X-Accel-Buffering") == "no"

            lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
            su_kien = [json.loads(line[6:]) for line in lines]

            # 1. Sự kiện đầu tiên BẮT BUỘC là sự kiện khởi đầu trả về hoi_thoai_id
            su_kien_dau = su_kien[0]
            assert su_kien_dau["loai"] == "bat_dau"
            assert "hoi_thoai_id" in su_kien_dau
            hoi_thoai_id = su_kien_dau["hoi_thoai_id"]
            assert hoi_thoai_id is not None

            # 2. Các sự kiện mảnh nội dung
            manh_text = [s for s in su_kien if s.get("loai") == "manh"]
            assert len(manh_text) == 3
            assert "".join(m["doan_van_ban"] for m in manh_text) == "Điện lực Việt Nam xin kính chào quý khách."

            # 3. Sự kiện xong
            manh_xong = [s for s in su_kien if s.get("loai") == "xong"]
            assert len(manh_xong) == 1
            assert manh_xong[0]["tang_phuc_vu"] == 1
            assert manh_xong[0]["token_vao"] == 12

            # 4. Kiểm tra CSDL đã lưu lại cuộc hội thoại và cả 2 tin nhắn
            ht_db = lay_hoi_thoai(hoi_thoai_id)
            assert ht_db is not None
            assert ht_db.nguoi_dung_id == "nguoi_dung_moi"

            cac_tn = lay_tin_nhan_hoi_thoai(hoi_thoai_id)
            assert len(cac_tn) == 2
            assert cac_tn[0].vai_tro == "user"
            assert cac_tn[0].noi_dung == "EVN là gì?"
            assert cac_tn[1].vai_tro == "assistant"
            assert cac_tn[1].noi_dung == "Điện lực Việt Nam xin kính chào quý khách."


def test_xu_ly_loi_thong_nhat_khong_lo_chi_tiet_ky_thuat():
    """Kiểm tra bộ xử lý lỗi thống nhất {loi: {ma, thong_diep, ma_yeu_cau}}:

    - Không trả ra stack trace, không lộ thông tin kỹ thuật máy chủ.
    - Chứa ma_yeu_cau duy nhất để tra cứu log.
    """
    # 1. Thử gửi body không hợp lệ (thiếu tin nhắn) -> 422
    resp_422 = client.post("/chat", json={})
    assert resp_422.status_code == 422
    data_422 = resp_422.json()
    assert "loi" in data_422
    assert data_422["loi"]["ma"] == 422
    assert "ma_yeu_cau" in data_422["loi"]
    assert "thong_diep" in data_422["loi"]
    # Không để lộ internal pydantic stack trace
    assert "Traceback" not in resp_422.text

    # 2. Thử truy cập endpoint không tồn tại -> 404
    resp_404 = client.get("/khong-ton-tai")
    assert resp_404.status_code == 404
    data_404 = resp_404.json()
    assert "loi" in data_404
    assert data_404["loi"]["ma"] == 404
    assert "ma_yeu_cau" in data_404["loi"]


def test_vuot_han_muc_tra_ve_429():
    """Kiểm tra khi vượt hạn mức HAN_MUC_MOI_NGUOI_GIO thì trả về HTTP 429 đúng chuẩn {loi: {ma, thong_diep}}."""
    with patch("app.core.han_muc.lay_cau_hinh") as mock_conf:
        cai_dat = MagicMock()
        cai_dat.env.HAN_MUC_MOI_NGUOI_GIO = 2
        mock_conf.return_value = cai_dat

        user_id = "user_spam"
        # Gọi 2 lần hợp lệ
        with patch("app.main.goi_mo_hinh", new_callable=AsyncMock) as mock_goi:
            mock_goi.return_value = KetQuaGoi("OK", 1, "m", 1, 1, 10.0, 1)
            r1 = client.post("/chat", headers={"X-User-Id": user_id}, json={"tin_nhan": "1"})
            assert r1.status_code == 200
            r2 = client.post("/chat", headers={"X-User-Id": user_id}, json={"tin_nhan": "2"})
            assert r2.status_code == 200

            # Lần 3 vượt hạn mức -> 429
            r3 = client.post("/chat", headers={"X-User-Id": user_id}, json={"tin_nhan": "3"})
            assert r3.status_code == 429
            data_429 = r3.json()
            assert "loi" in data_429
            assert data_429["loi"]["ma"] == 429
            assert "vượt quá" in data_429["loi"]["thong_diep"].lower()


def test_get_trang_chu_phuc_vu_html():
    """Kiểm tra GET / phục vụ giao diện web index.html với mã 200 và Content-Type text/html."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Chatbot EVN" in resp.text
    assert "id=\"chat-input\"" in resp.text


@pytest.mark.asyncio
async def test_get_chat_stream_cho_eventsource():
    """Kiểm tra GET /chat/stream phát SSE với query parameters hỗ trợ trình duyệt EventSource."""
    from app.llm.router import ManhPhatRa

    ket_qua_cuoi = KetQuaGoi(
        noi_dung="Phản hồi qua GET SSE.",
        tang_phuc_vu=1,
        ten_model="gemini/gemini-3.6-flash",
        token_vao=10,
        token_ra=20,
        do_tre_ms=150.0,
        so_lan_thu=1,
        danh_sach_tang_da_hong=[],
        chi_phi_usd=0.00001,
    )

    async def mock_generator(*args, **kwargs):
        yield ManhPhatRa.tao_manh_noi_dung("Phản hồi ")
        yield ManhPhatRa.tao_manh_noi_dung("qua GET SSE.")
        yield ManhPhatRa.tao_manh_ket_thuc(ket_qua_cuoi)

    with patch("app.main.goi_mo_hinh_theo_dong", side_effect=mock_generator):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/chat/stream?tin_nhan=Chao+EVN",
                headers={"X-User-Id": "user_browser"},
            )

            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            lines = [line for line in resp.text.strip().split("\n\n") if line.startswith("data: ")]
            su_kien = [json.loads(line[6:]) for line in lines]

            assert len(su_kien) >= 3
            assert su_kien[0]["loai"] == "bat_dau"
            assert su_kien[-1]["loai"] == "xong"
            assert su_kien[-1]["tang_phuc_vu"] == 1


def test_trang_chu_phuc_vu_giao_dien_dashboard_va_chat():
    """Kiểm tra trang chủ / trả về mã 200 và chứa đầy đủ cấu trúc Dashboard và Chat."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "view-dashboard" in resp.text
    assert "view-chat" in resp.text
    assert "Dashboard Trợ lý ảo" in resp.text
    assert "nav-btn-dashboard" in resp.text
    assert "nav-btn-chat" in resp.text
    assert "btn-back-dashboard" in resp.text
    assert "dash-quick-input" in resp.text

