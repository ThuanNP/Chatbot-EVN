"""Bộ kiểm thử cho quản lý cửa sổ ngữ cảnh app/chat/ngu_canh.py.

Kiểm tra:
1. Thuật toán ước tính token bằng công thức xấp xỉ cho tiếng Việt và tiếng Anh.
2. Lời nhắc hệ thống trung lập đọc từ prompts/he_thong.md nằm ngoài mã, có số phiên bản.
3. Giới hạn token mặc định an toàn theo tầng có cửa sổ nhỏ nhất (OpenRouter Auto 8k).
4. Cắt tỉa ngữ cảnh theo nguyên CẶP (user, assistant), tuyệt đối không cắt lẻ một nửa cặp.
5. Mô phỏng trò chuyện 20 lượt: kiểm tra lời nhắc đầu vào (token_vao) không phình vô hạn.
"""

from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import DUONG_DAN_GOC
from app.core.database import Base, dat_engine
from app.chat.hoi_thoai import luu_tin_nhan, tao_hoi_thoai
from app.chat.ngu_canh import (
    DUONG_DAN_PROMPT_HE_THONG,
    GIOI_HAN_TOKEN_AN_TOAN_MAC_DINH,
    doc_loi_nhac_he_thong,
    dung_ngu_canh,
    uoc_tinh_token,
)


@pytest.fixture(autouse=True)
def thiet_lap_sqlite_in_memory():
    """Thiết lập SQLite in-memory biệt lập cho từng test case."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    dat_engine(test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)


def test_uoc_tinh_token():
    """Kiểm tra hàm ước tính token bằng công thức xấp xỉ heuristic."""
    # Chuỗi rỗng trả về 0
    assert uoc_tinh_token("") == 0
    assert uoc_tinh_token("   ") == 0

    # Tiếng Việt có dấu: từ ngắn và có dấu thanh
    chuoi_tv = "Tập đoàn Điện lực Việt Nam EVN chăm sóc khách hàng 24/7"
    token_tv = uoc_tinh_token(chuoi_tv)
    assert token_tv > 10
    # Đảm bảo có tính 4 token overhead cấu trúc tin nhắn
    assert token_tv >= len(chuoi_tv.split()) + 4

    # Đoạn văn bản dài hơn cho kết quả lớn hơn tương ứng
    chuoi_dai = chuoi_tv * 5
    assert uoc_tinh_token(chuoi_dai) > token_tv * 3


def test_prompts_he_thong_nam_ngoai_ma_co_so_phien_ban():
    """Kiểm chứng prompts/he_thong.md nằm ngoài mã nguồn và có dòng số phiên bản ở đầu tệp."""
    assert DUONG_DAN_PROMPT_HE_THONG.exists(), "Tệp prompts/he_thong.md phải tồn tại"

    with open(DUONG_DAN_PROMPT_HE_THONG, "r", encoding="utf-8") as f:
        noi_dung = f.read()

    # Kiểm tra có dòng phiên bản ở đầu tệp
    dong_dau = [line.strip() for line in noi_dung.splitlines() if line.strip()][0]
    assert "Phiên bản:" in dong_dau or "Phien_ban:" in dong_dau

    # Kiểm tra đọc qua hàm doc_loi_nhac_he_thong
    prompt_doc = doc_loi_nhac_he_thong()
    assert "Tập đoàn Điện lực Việt Nam" in prompt_doc

    # Kiểm tra tính trung lập: không chứa các thẻ định dạng riêng của từng hãng
    assert "<thinking>" not in prompt_doc
    assert "</thinking>" not in prompt_doc
    assert "<function_calls>" not in prompt_doc


def test_gioi_han_token_mac_dinh_theo_tang_nho_nhat():
    """Kiểm chứng giới hạn token mặc định đặt an toàn theo tầng có cửa sổ ngữ cảnh nhỏ nhất (8k)."""
    # Tầng 2 (OpenRouter Auto) có context 8.192 token, trừ 4.096 token ra -> 4.096 token vào
    assert GIOI_HAN_TOKEN_AN_TOAN_MAC_DINH == 4096


def test_dung_ngu_canh_luon_giu_system_prompt():
    """Kiểm tra lời nhắc hệ thống luôn luôn nằm ở vị trí đầu tiên (index 0)."""
    ht = tao_hoi_thoai()
    luu_tin_nhan(ht.id, "user", "Xin chào")
    luu_tin_nhan(ht.id, "assistant", "Chào bạn, tôi là trợ lý EVN.")

    ket_qua = dung_ngu_canh(hoi_thoai_id=ht.id, tin_nhan_moi="Giá điện hôm nay thế nào?")
    assert len(ket_qua) > 0
    assert ket_qua[0]["role"] == "system"
    assert "Tập đoàn Điện lực Việt Nam" in ket_qua[0]["content"]

    # Tin nhắn cuối cùng là câu hỏi mới của người dùng
    assert ket_qua[-1]["role"] == "user"
    assert ket_qua[-1]["content"] == "Giá điện hôm nay thế nào?"


def test_cat_ngu_canh_theo_cap_khong_cat_le():
    """Kiểm tra cắt tỉa ngữ cảnh theo nguyên CẶP (user, assistant), tuyệt đối không cắt lẻ."""
    ht = tao_hoi_thoai()

    # Tạo 3 cặp tương tác trong quá khứ
    luu_tin_nhan(ht.id, "user", "Câu hỏi 1: Lịch sử tiền điện")
    luu_tin_nhan(ht.id, "assistant", "Trả lời 1: Tiền điện tháng trước là 500k")

    luu_tin_nhan(ht.id, "user", "Câu hỏi 2: Cách đăng ký điện 3 pha")
    luu_tin_nhan(ht.id, "assistant", "Trả lời 2: Cần chuẩn bị căn cước và đơn đề nghị")

    luu_tin_nhan(ht.id, "user", "Câu hỏi 3: Chi phí lắp đặt 3 pha")
    luu_tin_nhan(ht.id, "assistant", "Trả lời 3: Miễn phí nhân công lắp đặt")

    cau_hoi_moi = "Câu hỏi 4: Thời gian hoàn thành trong bao lâu?"

    # Đo lượng token của system và câu hỏi mới
    token_sys = uoc_tinh_token(doc_loi_nhac_he_thong())
    token_moi = uoc_tinh_token(cau_hoi_moi)

    # Đo token của từng cặp
    ds_tn = [
        ("Câu hỏi 1: Lịch sử tiền điện", "Trả lời 1: Tiền điện tháng trước là 500k"),
        ("Câu hỏi 2: Cách đăng ký điện 3 pha", "Trả lời 2: Cần chuẩn bị căn cước và đơn đề nghị"),
        ("Câu hỏi 3: Chi phí lắp đặt 3 pha", "Trả lời 3: Miễn phí nhân công lắp đặt"),
    ]
    token_cap_1 = uoc_tinh_token(ds_tn[0][0]) + uoc_tinh_token(ds_tn[0][1])
    token_cap_2 = uoc_tinh_token(ds_tn[1][0]) + uoc_tinh_token(ds_tn[1][1])
    token_cap_3 = uoc_tinh_token(ds_tn[2][0]) + uoc_tinh_token(ds_tn[2][1])

    # Kịch bản A: Giới hạn token chỉ đủ chỗ cho System + Câu mới + Cặp 3 + Cặp 2 (không đủ Cặp 1)
    gioi_han_a = token_sys + token_moi + token_cap_3 + token_cap_2 + 5
    ket_qua_a = dung_ngu_canh(
        hoi_thoai_id=ht.id,
        gioi_han_token=gioi_han_a,
        tin_nhan_moi=cau_hoi_moi,
    )

    # Phải có: System, User 2, Assistant 2, User 3, Assistant 3, User 4
    assert len(ket_qua_a) == 6
    roles_a = [m["role"] for m in ket_qua_a]
    assert roles_a == ["system", "user", "assistant", "user", "assistant", "user"]
    # Cặp 1 bị loại bỏ hoàn toàn
    assert "Câu hỏi 1" not in str(ket_qua_a)
    # Cặp 2 và Cặp 3 còn nguyên vẹn cả câu hỏi lẫn câu trả lời
    assert "Câu hỏi 2" in ket_qua_a[1]["content"]
    assert "Trả lời 2" in ket_qua_a[2]["content"]
    assert "Câu hỏi 3" in ket_qua_a[3]["content"]
    assert "Trả lời 3" in ket_qua_a[4]["content"]
    assert ket_qua_a[5]["content"] == cau_hoi_moi

    # Kịch bản B (QUAN TRỌNG NHẤT): Giới hạn token chỉ đủ chỗ cho System + Câu mới + Cặp 3 + MỘT NỬA Cặp 2
    # Cửa sổ chỉ cho phép thêm 1 tin nhắn của Cặp 2, nhưng KHÔNG ĐỦ cho cả cặp 2.
    # Quy tắc: Bỏ toàn bộ Cặp 2, KHÔNG ĐƯỢC LẤY LẺ nửa cặp!
    gioi_han_b = token_sys + token_moi + token_cap_3 + (token_cap_2 // 2)
    ket_qua_b = dung_ngu_canh(
        hoi_thoai_id=ht.id,
        gioi_han_token=gioi_han_b,
        tin_nhan_moi=cau_hoi_moi,
    )

    # Phải có: System, User 3, Assistant 3, User 4 (tổng cộng 4 tin nhắn)
    assert len(ket_qua_b) == 4
    roles_b = [m["role"] for m in ket_qua_b]
    assert roles_b == ["system", "user", "assistant", "user"]
    # Tuyệt đối không có một nửa cặp 2 lẻ loi nào
    assert "Trả lời 2" not in str(ket_qua_b)
    assert "Câu hỏi 2" not in str(ket_qua_b)
    assert "Câu hỏi 3" in ket_qua_b[1]["content"]
    assert "Trả lời 3" in ket_qua_b[2]["content"]


def test_tro_chuyen_20_luot_kiem_tra_khong_phinh_vo_han(caplog):
    """Kiểm chứng mô phỏng trò chuyện 20 lượt:

    1. Lời nhắc đầu vào (token_vao) chạm ngưỡng an toàn và ổn định, không phình vô hạn.
    2. Cắt tỉa ngữ cảnh theo nguyên CẶP (user, assistant) ở mọi lượt, không cắt lẻ.
    3. Luôn giữ lời nhắc hệ thống trung lập (prompts/he_thong.md) ở đầu.
    4. Ghi nhận log token_vao ở mỗi lượt và 5 dòng cuối cùng ổn định, tương đương:
       docker compose logs app | grep token_vao | tail -5
    """
    caplog.set_level("INFO")
    ht = tao_hoi_thoai(nguoi_dung_id="khach_vip")

    # Đặt giới hạn token kiểm thử phù hợp (system prompt ~1000 token, chừa ~400-500 token cho các cặp gần nhất)
    gioi_han_kiem_thu = 1500

    danh_sach_cau_hoi = [
        "Lượt 1: Tôi cần tư vấn thủ tục cấp điện mới cho hộ gia đình tại quận 1.",
        "Lượt 2: Hồ sơ đăng ký cấp điện gồm những giấy tờ pháp lý gì?",
        "Lượt 3: Thời gian khảo sát và lắp đặt công tơ điện mất bao lâu?",
        "Lượt 4: Chi phí lắp đặt ban đầu có được miễn phí nhân công không?",
        "Lượt 5: Tôi muốn tìm hiểu về cơ cấu biểu giá điện sinh hoạt 6 bậc hiện nay.",
        "Lượt 6: Bậc 1 và Bậc 2 hiện nay áp dụng cho bao nhiêu kWh đầu tiên?",
        "Lượt 7: Nếu dùng vượt 400 kWh một tháng thì tính theo giá bậc nào?",
        "Lượt 8: Có những kênh nào để thanh toán tiền điện trực tuyến không dùng tiền mặt?",
        "Lượt 9: Tôi có thể trích nợ tự động qua tài khoản ngân hàng được không?",
        "Lượt 10: Làm thế nào để tra cứu hóa đơn tiền điện qua ứng dụng Zalo?",
        "Lượt 11: Mã khách hàng EVN thường có định dạng như thế nào?",
        "Lượt 12: Tôi bị mất điện đột ngột thì báo qua số tổng đài nào?",
        "Lượt 13: Số tổng đài chăm sóc khách hàng EVN miền Nam là số mấy?",
        "Lượt 14: Tôi muốn thay đổi thông tin chủ thể hợp đồng mua bán điện sang tên tôi.",
        "Lượt 15: Thủ tục sang tên hợp đồng điện cần chuẩn bị giấy tờ mua bán nhà không?",
        "Lượt 16: Hướng dẫn cách sử dụng điều hòa tiết kiệm điện trong mùa nắng nóng.",
        "Lượt 17: Có nên cài đặt nhiệt độ điều hòa ở mức 26 đến 28 độ C không?",
        "Lượt 18: Khoảng cách an toàn hành lang lưới điện cao áp 220kV là bao nhiêu mét?",
        "Lượt 19: Làm sao để cài đặt ứng dụng CSKH EVN trên điện thoại thông minh?",
        "Lượt 20: Cảm ơn bạn, thông tin tư vấn rất rõ ràng và hữu ích!",
    ]

    danh_sach_token_vao_20_luot = []
    danh_sach_so_cap_giu_20_luot = []

    for luot, cau_hoi in enumerate(danh_sach_cau_hoi, start=1):
        tin_nhan_ngu_canh = dung_ngu_canh(
            hoi_thoai_id=ht.id,
            gioi_han_token=gioi_han_kiem_thu,
            tin_nhan_moi=cau_hoi,
        )

        # 1. Kiểm tra cấu trúc ngữ cảnh ở từng lượt:
        # Luôn có system prompt ở vị trí đầu tiên
        assert tin_nhan_ngu_canh[0]["role"] == "system"
        assert "Tập đoàn Điện lực Việt Nam" in tin_nhan_ngu_canh[0]["content"]

        # Tin nhắn cuối cùng luôn là câu hỏi của người dùng hiện tại
        assert tin_nhan_ngu_canh[-1]["role"] == "user"
        assert tin_nhan_ngu_canh[-1]["content"] == cau_hoi

        # CẮT NGỮ CẢNH THEO CẶP, KHÔNG CẮT LẺ:
        # Toàn bộ tin nhắn lịch sử ở giữa phải là các cặp (user, assistant) hoàn chỉnh, số lượng luôn chẵn
        tin_lich_su = tin_nhan_ngu_canh[1:-1]
        assert len(tin_lich_su) % 2 == 0, f"Lượt {luot}: Số tin lịch sử phải là số chẵn (theo cặp), không cắt lẻ"
        so_cap = len(tin_lich_su) // 2
        danh_sach_so_cap_giu_20_luot.append(so_cap)

        for k in range(0, len(tin_lich_su), 2):
            assert tin_lich_su[k]["role"] == "user", f"Lượt {luot}: Tin đầu cặp phải là user"
            assert tin_lich_su[k + 1]["role"] == "assistant", f"Lượt {luot}: Tin sau cặp phải là assistant"

        # Tính tổng token của toàn bộ lời nhắc chuẩn bị gửi cho mô hình (token_vao)
        tong_token_vao = sum(uoc_tinh_token(m["content"]) for m in tin_nhan_ngu_canh)
        danh_sach_token_vao_20_luot.append(tong_token_vao)

        # Mọi lượt đều không được vượt quá giới hạn token an toàn
        assert tong_token_vao <= gioi_han_kiem_thu, (
            f"Lượt {luot} bị vượt ngưỡng token: {tong_token_vao} > {gioi_han_kiem_thu}"
        )

        # Lưu lại câu hỏi và câu trả lời vào DB để mô phỏng tương tác thực tế
        luu_tin_nhan(ht.id, "user", cau_hoi)
        cau_tra_loi = (
            f"Phản hồi cho {cau_hoi[:25]}...: Quý khách chuẩn bị hồ sơ và liên hệ 19006769 để được hỗ trợ."
        )
        luu_tin_nhan(ht.id, "assistant", cau_tra_loi, tang_phuc_vu=1)

    # 2. Kiểm tra danh sách 20 lượt:
    assert len(danh_sach_token_vao_20_luot) == 20
    assert len(danh_sach_so_cap_giu_20_luot) == 20

    # 3. Kiểm tra 5 lượt cuối cùng (tương đương tail -5 log hệ thống):
    # Lời nhắc không phình vô hạn mà đã đạt trạng thái cân bằng ổn định
    nam_luot_cuoi = danh_sach_token_vao_20_luot[-5:]
    do_lech = max(nam_luot_cuoi) - min(nam_luot_cuoi)
    assert do_lech < 100, f"Các lượt cuối bị phình hoặc dao động bất thường: {nam_luot_cuoi}"

    # Số cặp giữ lại ở các lượt cuối phải ổn định
    so_cap_cuoi = danh_sach_so_cap_giu_20_luot[-5:]
    assert all(c == so_cap_cuoi[0] for c in so_cap_cuoi), f"Số cặp giữ lại không ổn định: {so_cap_cuoi}"

    # 4. Đảm bảo ở lượt 20, các cặp cũ xa xưa (ví dụ Lượt 1, Lượt 2) đã được cắt bỏ trọn vẹn
    ngu_canh_cuoi = dung_ngu_canh(hoi_thoai_id=ht.id, gioi_han_token=gioi_han_kiem_thu)
    noi_dung_cuoi_str = str(ngu_canh_cuoi)
    assert "Lượt 1:" not in noi_dung_cuoi_str, "Cặp ở lượt 1 quá khứ phải được cắt tỉa để tránh phình vô hạn"
    assert "Lượt 20:" in noi_dung_cuoi_str, "Cặp ở lượt 20 gần nhất phải được giữ lại"

    # 5. Kiểm tra các dòng log ghi nhận token_vao trong caplog (mô phỏng docker compose logs app | grep token_vao | tail -5)
    log_token_vao = [r.message for r in caplog.records if "token_vao" in r.message]
    assert len(log_token_vao) >= 20, "Hệ thống phải ghi nhận log token_vao ở mọi lượt dựng ngữ cảnh"
    nam_dong_log_cuoi = log_token_vao[-5:]
    assert len(nam_dong_log_cuoi) == 5
    for dong in nam_dong_log_cuoi:
        assert "token_vao=" in dong

    # In 5 dòng log cuối cùng khi chạy pytest với cờ -s
    print("\n" + "=" * 70)
    print("5 DÒNG LOG CUỐI CÙNG (TƯƠNG ĐƯƠNG docker compose logs app | grep token_vao | tail -5):")
    for dong in nam_dong_log_cuoi:
        print(f"[INFO] {dong}")
    print("=" * 70)

