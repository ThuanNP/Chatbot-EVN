"""Bộ kiểm thử cho module quản lý hội thoại app/chat/hoi_thoai.py.

Kiểm tra:
1. Khởi tạo, truy xuất, cập nhật tiêu đề và phân trang danh sách hội thoại.
2. Lưu tin nhắn, tính xấp xỉ token, kiểm tra ràng buộc vai trò (user/assistant).
3. Ràng buộc xoá phân tầng (ON DELETE CASCADE) khi xoá phiên hội thoại.
4. Cơ chế tự động đặt tiêu đề nền sau lượt trả lời đầu tiên (tối đa 8 từ, không lặp lại ở lượt 2).
5. Xử lý an toàn khi việc sinh tiêu đề nền gặp lỗi.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from app.core.database import Base, HoiThoai, TinNhan, dat_engine, lay_phien_db
from app.chat.hoi_thoai import (
    danh_sach_hoi_thoai,
    dem_so_tin_nhan,
    doi_tieu_de_hoi_thoai,
    lay_hoi_thoai,
    lay_tin_nhan_hoi_thoai,
    luu_tin_nhan,
    tao_hoi_thoai,
    tu_dong_dat_tieu_de_nen,
    xoa_hoi_thoai,
)
from app.llm.router import KetQuaGoi


@pytest.fixture(autouse=True)
def thiet_lap_sqlite_in_memory():
    """Thiết lập SQLite in-memory biệt lập với StaticPool cho từng test case."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    dat_engine(test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)


def test_tao_va_lay_hoi_thoai():
    """Kiểm tra tạo mới phiên hội thoại và truy vấn theo mã định danh."""
    ht = tao_hoi_thoai(nguoi_dung_id="user_123", tieu_de="Hỏi về giá điện")
    assert ht.id is not None
    assert ht.nguoi_dung_id == "user_123"
    assert ht.tieu_de == "Hỏi về giá điện"

    # Lấy lại từ DB
    ht_db = lay_hoi_thoai(ht.id)
    assert ht_db is not None
    assert ht_db.id == ht.id
    assert ht_db.tieu_de == "Hỏi về giá điện"

    # Trường hợp không tìm thấy
    assert lay_hoi_thoai("ma-khong-ton-tai") is None


def test_danh_sach_hoi_thoai_va_phan_trang():
    """Kiểm tra lấy danh sách hội thoại theo người dùng có sắp xếp và phân trang."""
    ht1 = tao_hoi_thoai(nguoi_dung_id="khach_a", tieu_de="Phần 1")
    ht2 = tao_hoi_thoai(nguoi_dung_id="khach_a", tieu_de="Phần 2")
    ht3 = tao_hoi_thoai(nguoi_dung_id="khach_b", tieu_de="Của khách B")

    danh_sach_a = danh_sach_hoi_thoai(nguoi_dung_id="khach_a", gioi_han=10)
    assert len(danh_sach_a) == 2
    # Sắp xếp mới nhất lên đầu
    assert [h.id for h in danh_sach_a] == [ht2.id, ht1.id]

    # Kiểm tra phân trang với limit và offset
    ds_trang_1 = danh_sach_hoi_thoai(nguoi_dung_id="khach_a", gioi_han=1, bo_qua=0)
    assert len(ds_trang_1) == 1
    assert ds_trang_1[0].id == ht2.id

    ds_trang_2 = danh_sach_hoi_thoai(nguoi_dung_id="khach_a", gioi_han=1, bo_qua=1)
    assert len(ds_trang_2) == 1
    assert ds_trang_2[0].id == ht1.id


def test_doi_tieu_de_hoi_thoai():
    """Kiểm tra đổi tiêu đề và thời điểm cập nhật của hội thoại."""
    ht = tao_hoi_thoai(nguoi_dung_id="user_test")
    thanh_cong = doi_tieu_de_hoi_thoai(ht.id, "Tiêu đề đã sửa đổi")
    assert thanh_cong is True

    ht_moi = lay_hoi_thoai(ht.id)
    assert ht_moi is not None
    assert ht_moi.tieu_de == "Tiêu đề đã sửa đổi"

    # Đổi tiêu đề cho phiên không tồn tại
    assert doi_tieu_de_hoi_thoai("khong-co", "abc") is False


def test_luu_tin_nhan_va_lay_danh_sach():
    """Kiểm tra lưu trữ tin nhắn hợp lệ và lấy danh sách theo thời gian tăng dần."""
    ht = tao_hoi_thoai()
    tn1 = luu_tin_nhan(
        hoi_thoai_id=ht.id,
        vai_tro="user",
        noi_dung="Cách tính tiền điện bậc 1?",
    )
    assert tn1.id is not None
    assert tn1.vai_tro == "user"
    assert tn1.token_uoc_tinh > 0

    tn2 = luu_tin_nhan(
        hoi_thoai_id=ht.id,
        vai_tro="assistant",
        noi_dung="Bậc 1 tính từ 0 đến 50 kWh...",
        tang_phuc_vu=1,
    )
    assert tn2.tang_phuc_vu == 1

    danh_sach = lay_tin_nhan_hoi_thoai(ht.id)
    assert len(danh_sach) == 2
    assert danh_sach[0].id == tn1.id
    assert danh_sach[1].id == tn2.id
    assert dem_so_tin_nhan(ht.id) == 2


def test_rang_buoc_vai_tro_khong_hop_le():
    """Kiểm tra ném lỗi khi lưu tin nhắn với vai trò không phải 'user' hoặc 'assistant'."""
    ht = tao_hoi_thoai()
    with pytest.raises(ValueError, match="vai_tro chỉ được phép nhận giá trị"):
        luu_tin_nhan(hoi_thoai_id=ht.id, vai_tro="system", noi_dung="Lời nhắc cấm")

    with pytest.raises(ValueError, match="vai_tro chỉ được phép nhận giá trị"):
        luu_tin_nhan(hoi_thoai_id=ht.id, vai_tro="admin", noi_dung="Nội dung khác")


def test_xoa_hoi_thoai_cascade_tin_nhan():
    """Kiểm tra khi xoá hội thoại thì toàn bộ tin nhắn liên quan bị xoá tự động (cascade)."""
    ht = tao_hoi_thoai()
    luu_tin_nhan(ht.id, "user", "Câu hỏi kiểm tra cascade")
    luu_tin_nhan(ht.id, "assistant", "Câu trả lời")

    # Kiểm tra trước khi xoá có 2 tin nhắn trong DB
    assert dem_so_tin_nhan(ht.id) == 2

    # Thực hiện xoá hội thoại
    thanh_cong = xoa_hoi_thoai(ht.id)
    assert thanh_cong is True

    # Kiểm tra hội thoại đã biến mất
    assert lay_hoi_thoai(ht.id) is None

    # Kiểm tra tin nhắn trong bảng tin_nhan cũng đã bị xoá hoàn toàn
    with lay_phien_db() as phien:
        tin_con = (
            phien.execute(select(TinNhan).where(TinNhan.hoi_thoai_id == ht.id))
            .scalars()
            .all()
        )
        assert len(list(tin_con)) == 0


@pytest.mark.asyncio
async def test_tu_dong_dat_tieu_de_nen_sau_luot_dau():
    """Kiểm tra tác vụ nền gọi mô hình sinh tiêu đề và cắt tối đa 8 từ sau lượt đầu."""
    ht = tao_hoi_thoai()

    mock_ket_qua = KetQuaGoi(
        noi_dung="Hướng dẫn tra cứu hóa đơn tiền điện sinh hoạt EVN chi tiết nhanh",
        tang_phuc_vu=1,
        ten_model="gemini/gemini-3.6-flash",
        token_vao=20,
        token_ra=12,
        do_tre_ms=150.0,
        so_lan_thu=1,
    )

    with patch("app.chat.hoi_thoai.goi_mo_hinh", new_callable=AsyncMock) as mock_goi:
        mock_goi.return_value = mock_ket_qua

        tieu_de_moi = await tu_dong_dat_tieu_de_nen(
            hoi_thoai_id=ht.id,
            cau_hoi="Tôi muốn kiểm tra hóa đơn tiền điện tháng này?",
            cau_tra_loi="Bạn có thể tải app EVN CSKH hoặc tra cứu tại website...",
        )

        assert mock_goi.called
        # Kiểm tra tiêu đề tối đa 8 từ
        assert tieu_de_moi is not None
        cac_tu = tieu_de_moi.split()
        assert len(cac_tu) <= 8

        # Kiểm tra DB đã được cập nhật tiêu đề mới
        ht_cap_nhat = lay_hoi_thoai(ht.id)
        assert ht_cap_nhat is not None
        assert ht_cap_nhat.tieu_de == tieu_de_moi


@pytest.mark.asyncio
async def test_luot_hai_khong_kich_hoat_lai_dat_tieu_de():
    """Kiểm tra sau lượt 2 (đã có 4 tin nhắn), không kích hoạt lại tác vụ đặt tiêu đề."""
    ht = tao_hoi_thoai()

    with patch("app.chat.hoi_thoai.kich_hoat_tu_dong_dat_tieu_de") as mock_kich_hoat:
        # Lượt 1
        luu_tin_nhan(ht.id, "user", "Câu hỏi 1")
        luu_tin_nhan(ht.id, "assistant", "Câu trả lời 1")
        assert mock_kich_hoat.call_count == 1

        # Lượt 2
        luu_tin_nhan(ht.id, "user", "Câu hỏi 2")
        luu_tin_nhan(ht.id, "assistant", "Câu trả lời 2")
        # Vẫn chỉ là 1 lần gọi duy nhất từ lượt đầu, không gọi thêm ở lượt 2
        assert mock_kich_hoat.call_count == 1


@pytest.mark.asyncio
async def test_loi_mo_hinh_khi_dat_tieu_de_khong_gay_crash():
    """Kiểm tra nếu gọi mô hình sinh tiêu đề bị lỗi mạng/timeout thì không làm sập tiến trình."""
    ht = tao_hoi_thoai()

    with patch("app.chat.hoi_thoai.goi_mo_hinh", new_callable=AsyncMock) as mock_goi:
        mock_goi.side_effect = RuntimeError("Lỗi mạng kết nối LLM")

        ket_qua = await tu_dong_dat_tieu_de_nen(
            hoi_thoai_id=ht.id,
            cau_hoi="Hỏi?",
            cau_tra_loi="Đáp!",
        )

        assert ket_qua is None
        # Tiêu đề vẫn giữ nguyên ban đầu
        ht_sau = lay_hoi_thoai(ht.id)
        assert ht_sau is not None
        assert ht_sau.tieu_de == "Cuộc trò chuyện mới"
