"""Bộ kiểm thử cho hệ thống xác thực người dùng và hạn mức 3 tầng (Prompt 10).

Bao gồm:
1. Xác thực Bearer token: hợp lệ, thiếu token (401), sai định dạng (401), token giả mạo (401), tài khoản bị khoá (401).
2. Tầng 1 IP: Chặn dồn dập trong 1 phút, trả về HTTP 429 kèm header Retry-After.
3. Tầng 2 Người dùng/giờ: Bậc free vs Bậc pro nhân hệ số, trả về HTTP 429 kèm header Retry-After.
4. Tầng 3 Chi phí ngày: Ngăn chặn vượt trần chi phí ngày cá nhân, trả về HTTP 429 kèm header Retry-After.
5. Endpoint GET /toi: Trả về đầy đủ thông tin bậc, đã dùng trong giờ, đã tiêu hôm nay, hạn mức còn lại.
6. Script CLI tao_nguoi_dung.py: Sinh token ngẫu nhiên, lưu dạng băm, không lưu thô.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from app.core.database import Base, LuotGoi, NguoiDung, dat_engine, lay_phien_db
from app.core.han_muc import (
    bam_ma_thong_bao,
    dat_lai_han_muc,
    sinh_ma_thong_bao_ngau_nhien,
)
from app.main import app
from scripts.tao_nguoi_dung import tao_hoac_cap_nhat_nguoi_dung

client = TestClient(app)


@pytest.fixture(autouse=True)
def thiet_lap_moi_truong_kiem_thu(monkeypatch):
    """Thiết lập CSDL SQLite in-memory biệt lập và biến môi trường cho từng ca kiểm thử."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    dat_engine(test_engine)

    monkeypatch.setenv("GOOGLE_API_KEY", "mock-google-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-openrouter-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-anthropic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-openai-key")
    monkeypatch.setenv("APP_SECRET", "mock-app-secret")  # gitleaks:allow
    monkeypatch.setenv("HAN_MUC_IP_PHUT", "20")
    monkeypatch.setenv("HAN_MUC_MOI_NGUOI_GIO", "60")
    monkeypatch.setenv("HE_SO_BAC_PRO", "5")
    monkeypatch.setenv("HAN_MUC_CHI_PHI_NGAY_FREE_USD", "1.0")
    monkeypatch.setenv("HAN_MUC_CHI_PHI_NGAY_PRO_USD", "5.0")
    monkeypatch.setenv("NGAN_SACH_NGAY_USD", "10.0")

    from app.config import lay_cau_hinh
    lay_cau_hinh(nap_lai=True)
    dat_lai_han_muc()

    yield

    Base.metadata.drop_all(bind=test_engine)
    dat_lai_han_muc()
    lay_cau_hinh(nap_lai=True)


def test_tao_nguoi_dung_va_luu_dang_bam():
    """Kiểm tra tạo người dùng sinh token ngẫu nhiên, lưu dạng băm, không lưu thô trong CSDL."""
    token_tho = tao_hoac_cap_nhat_nguoi_dung(email="nhanvien@evn.com.vn", bac="free")

    assert token_tho.startswith("evn_sec_")

    with lay_phien_db() as phien:
        stmt = select(NguoiDung).where(NguoiDung.email == "nhanvien@evn.com.vn")
        nd = phien.execute(stmt).scalar_one_or_none()

        assert nd is not None
        assert nd.email == "nhanvien@evn.com.vn"
        assert nd.bac == "free"
        assert nd.kich_hoat is True
        # Khẳng định token thô KHÔNG lưu trong CSDL
        assert nd.token_hash != token_tho
        # Khẳng định token hash khớp với hàm băm chuẩn HMAC-SHA256
        assert nd.token_hash == bam_ma_thong_bao(token_tho)


def test_xac_thuc_bearer_token_thanh_cong():
    """Kiểm tra gọi GET /toi thành công với header Authorization: Bearer <token>."""
    token_tho = tao_hoac_cap_nhat_nguoi_dung(email="chuyengia@evn.com.vn", bac="pro")

    resp = client.get("/toi", headers={"Authorization": f"Bearer {token_tho}"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["email"] == "chuyengia@evn.com.vn"
    assert data["bac"] == "pro"
    assert data["da_dung_gio"] == 1
    # Bậc pro có hạn mức giờ = 60 * 5 = 300
    assert data["han_muc_gio"] == 300
    assert data["so_luot_con_lai_gio"] == 299
    assert data["han_muc_chi_phi_ngay_usd"] == 5.0


def test_xac_thuc_that_bai_khi_thieu_hoac_sai_token():
    """Kiểm tra từ chối HTTP 401 khi thiếu token, sai định dạng hoặc token không tồn tại."""
    # 1. Thiếu header Authorization
    resp_thieu = client.get("/toi")
    assert resp_thieu.status_code == 401
    assert "Thiếu mã thông báo xác thực" in resp_thieu.json()["detail"]

    # 2. Sai định dạng (không có tiền tố Bearer)
    resp_sai_dinh_dang = client.get("/toi", headers={"Authorization": "Token 12345"})
    assert resp_sai_dinh_dang.status_code == 401
    assert "Định dạng mã thông báo không hợp lệ" in resp_sai_dinh_dang.json()["detail"]

    # 3. Token không tồn tại trong cơ sở dữ liệu
    resp_khong_ton_tai = client.get("/toi", headers={"Authorization": "Bearer evn_sec_gia_mao_99999"})
    assert resp_khong_ton_tai.status_code == 401
    assert "Mã thông báo không hợp lệ" in resp_khong_ton_tai.json()["detail"]


def test_xac_thuc_that_bai_khi_tai_khoan_bi_khoa():
    """Kiểm tra từ chối HTTP 401 khi tài khoản người dùng có kich_hoat = False."""
    token_tho = tao_hoac_cap_nhat_nguoi_dung(email="khoa@evn.com.vn", bac="free")

    # Vô hiệu hóa tài khoản trong CSDL
    with lay_phien_db() as phien:
        stmt = select(NguoiDung).where(NguoiDung.email == "khoa@evn.com.vn")
        nd = phien.execute(stmt).scalar_one_or_none()
        assert nd is not None
        nd.kich_hoat = False

    resp = client.get("/toi", headers={"Authorization": f"Bearer {token_tho}"})
    assert resp.status_code == 401
    assert "Mã thông báo không hợp lệ hoặc tài khoản đã bị vô hiệu hóa" in resp.json()["detail"]


def test_han_muc_tang_1_ip_chan_don_dap_kem_retry_after(monkeypatch):
    """Tầng 1: Kiểm tra chặn dồn dập theo IP trong 1 phút, trả về HTTP 429 kèm Retry-After."""
    # Giới hạn 3 yêu cầu / phút theo IP
    monkeypatch.setenv("HAN_MUC_IP_PHUT", "3")
    from app.config import lay_cau_hinh
    lay_cau_hinh(nap_lai=True)

    token_tho = tao_hoac_cap_nhat_nguoi_dung(email="ip_test@evn.com.vn", bac="free")
    headers = {"Authorization": f"Bearer {token_tho}", "X-Forwarded-For": "192.168.1.50"}

    # 3 yêu cầu đầu thành công
    for _ in range(3):
        r = client.get("/toi", headers=headers)
        assert r.status_code == 200

    # Yêu cầu thứ 4 bị chặn bởi Tầng 1 IP
    r4 = client.get("/toi", headers=headers)
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers
    retry_after = int(r4.headers["Retry-After"])
    assert retry_after >= 1

    data = r4.json()
    assert "loi" in data
    assert data["loi"]["ma"] == 429
    assert data["loi"]["tang_han_muc"] == "ip"
    assert "dồn dập" in data["loi"]["thong_diep"].lower()
    assert str(retry_after) in data["loi"]["thong_diep"]


def test_han_muc_tang_2_nguoi_dung_bac_free_va_pro(monkeypatch):
    """Tầng 2: Kiểm tra hạn mức mỗi giờ theo người dùng, bậc pro được nhân hệ số."""
    monkeypatch.setenv("HAN_MUC_IP_PHUT", "50")  # Đặt IP cao để không kích hoạt Tầng 1
    monkeypatch.setenv("HAN_MUC_MOI_NGUOI_GIO", "2")
    monkeypatch.setenv("HE_SO_BAC_PRO", "3")  # Free = 2, Pro = 6
    from app.config import lay_cau_hinh
    lay_cau_hinh(nap_lai=True)

    # 1. Kiểm tra người dùng bậc FREE (tối đa 2 lượt)
    token_free = tao_hoac_cap_nhat_nguoi_dung(email="user_free@evn.com.vn", bac="free")
    h_free = {"Authorization": f"Bearer {token_free}"}

    assert client.get("/toi", headers=h_free).status_code == 200
    assert client.get("/toi", headers=h_free).status_code == 200

    # Lần 3 của bậc free -> 429
    r_free_3 = client.get("/toi", headers=h_free)
    assert r_free_3.status_code == 429
    assert r_free_3.json()["loi"]["tang_han_muc"] == "nguoi_dung_gio"
    assert "Retry-After" in r_free_3.headers

    # 2. Kiểm tra người dùng bậc PRO (tối đa 2 * 3 = 6 lượt)
    token_pro = tao_hoac_cap_nhat_nguoi_dung(email="user_pro@evn.com.vn", bac="pro")
    h_pro = {"Authorization": f"Bearer {token_pro}"}

    for i in range(6):
        resp_pro = client.get("/toi", headers=h_pro)
        assert resp_pro.status_code == 200

    # Lần 7 của bậc pro -> 429
    r_pro_7 = client.get("/toi", headers=h_pro)
    assert r_pro_7.status_code == 429
    assert r_pro_7.json()["loi"]["tang_han_muc"] == "nguoi_dung_gio"


def test_han_muc_tang_3_chi_phi_ngay_tung_nguoi_dung(monkeypatch):
    """Tầng 3: Kiểm tra chặn người dùng tiêu vượt hạn mức chi phí ngày cá nhân."""
    monkeypatch.setenv("HAN_MUC_IP_PHUT", "50")
    monkeypatch.setenv("HAN_MUC_MOI_NGUOI_GIO", "50")
    monkeypatch.setenv("HAN_MUC_CHI_PHI_NGAY_FREE_USD", "0.50")
    from app.config import lay_cau_hinh
    lay_cau_hinh(nap_lai=True)

    token_tho = tao_hoac_cap_nhat_nguoi_dung(email="tieu_tien@evn.com.vn", bac="free")
    headers = {"Authorization": f"Bearer {token_tho}"}

    # Lấy ID của người dùng
    with lay_phien_db() as phien:
        stmt = select(NguoiDung).where(NguoiDung.email == "tieu_tien@evn.com.vn")
        nd = phien.execute(stmt).scalar_one_or_none()
        assert nd is not None
        user_id = nd.id

        # Giả lập người dùng đã tiêu 0.60 USD hôm nay (vượt hạn mức 0.50 USD)
        phien.add(
            LuotGoi(
                thoi_diem=datetime.now(timezone.utc),
                nguoi_dung_id=user_id,
                tang=1,
                model="gemini",
                token_vao=100,
                token_ra=200,
                chi_phi_usd=0.60,
                do_tre_ms=100.0,
                thanh_cong=True,
            )
        )

    # Gọi /toi -> Bị Tầng 3 chặn vì vượt trần chi phí ngày cá nhân
    resp = client.get("/toi", headers=headers)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    du_lieu = resp.json()
    assert du_lieu["loi"]["tang_han_muc"] == "chi_phi_ngay"
    assert "chi phí trong ngày" in du_lieu["loi"]["thong_diep"].lower()
    assert "ngày mai" in du_lieu["loi"]["thong_diep"].lower()


def test_tu_dong_kiem_chung_vong_lap_30_curl():
    """Tự kiểm chứng theo yêu cầu đặc tả: chạy 30 yêu cầu liên tiếp và thấy 429 xuất hiện."""
    token_tho = tao_hoac_cap_nhat_nguoi_dung(email="thu@vidu.com", bac="free")

    # Mặc định HAN_MUC_IP_PHUT = 20
    ma_trang_thai = []
    headers = {"Authorization": f"Bearer {token_tho}"}

    for _ in range(30):
        resp = client.get("/toi", headers=headers)
        ma_trang_thai.append(resp.status_code)

    # Các yêu cầu đầu (1..20) phải là 200
    assert ma_trang_thai[:20] == [200] * 20
    # Các yêu cầu sau (21..30) phải là 429 do vượt hạn mức dồn dập
    assert 429 in ma_trang_thai
    assert ma_trang_thai[20:] == [429] * 10
