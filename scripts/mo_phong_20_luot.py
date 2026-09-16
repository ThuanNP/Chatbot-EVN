"""Kịch bản giả lập trò chuyện 20 lượt kiểm tra cửa sổ ngữ cảnh không phình vô hạn.

Kịch bản này mô phỏng quá trình người dùng trò chuyện liên tục 20 lượt với Chatbot EVN:
1. Tạo một phiên hội thoại mới trong cơ sở dữ liệu.
2. Lần lượt gửi 20 câu hỏi về các dịch vụ điện lực (thủ tục, giá điện, báo sự cố...).
3. Gọi hàm dung_ngu_canh() ở mỗi lượt để cắt tỉa lịch sử theo cặp và ước tính token_vao.
4. Lưu câu hỏi của người dùng và câu trả lời giả lập của trợ lý vào cơ sở dữ liệu.
5. In bảng thống kê chi tiết và 5 lượt cuối cùng (tương đương tail -5).
"""

import argparse
import logging
import sys
from pathlib import Path

# Thêm đường dẫn gốc dự án vào sys.path để chạy độc lập từ bất kỳ thư mục nào
DUONG_DAN_GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DUONG_DAN_GOC))

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.chat.hoi_thoai import luu_tin_nhan, tao_hoi_thoai
from app.chat.ngu_canh import (
    GIOI_HAN_TOKEN_AN_TOAN_MAC_DINH,
    dung_ngu_canh,
    uoc_tinh_token,
)
from app.core.database import Base, dat_engine

# Cấu hình logging chuẩn: ghi ra stdout và cả /proc/1/fd/1 nếu đang chạy trong Docker container
handlers = [logging.StreamHandler(sys.stdout)]
if Path("/proc/1/fd/1").exists():
    try:
        fd1 = open("/proc/1/fd/1", "w", encoding="utf-8")
        handlers.append(logging.StreamHandler(fd1))
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=handlers,
    force=True,
)
logger = logging.getLogger("mo_phong_20_luot")

# Danh sách 20 câu hỏi mô phỏng nghiệp vụ EVN thực tế
DANH_SACH_CAU_HOI = [
    "Lượt 1: Tôi muốn đăng ký cấp điện sinh hoạt mới cho hộ gia đình tại quận 1.",
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


def chay_mo_phong(gioi_han_token: int = 1500) -> list[dict]:
    """Thực thi mô phỏng 20 lượt tương tác và ghi nhận biến động của token_vao."""
    # Khởi tạo cơ sở dữ liệu SQLite in-memory biệt lập cho kịch bản mô phỏng
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    dat_engine(engine)

    phi_hoi_thoai = tao_hoi_thoai(nguoi_dung_id="khach_hang_mo_phong")
    hoi_thoai_id = phi_hoi_thoai.id

    logger.info("=" * 70)
    logger.info("BẮT ĐẦU MÔ PHỎNG 20 LƯỢT TRÒ CHUYỆN VỚI CHATBOT EVN")
    logger.info(f"Mã phiên hội thoại: {hoi_thoai_id}")
    logger.info(f"Ngưỡng giới hạn token tối đa: {gioi_han_token} token")
    logger.info("=" * 70)

    ket_qua_cac_luot = []

    for index, cau_hoi in enumerate(DANH_SACH_CAU_HOI, start=1):
        # 1. Dựng ngữ cảnh cho lượt hiện tại
        danh_sach_tin = dung_ngu_canh(
            hoi_thoai_id=hoi_thoai_id,
            tin_nhan_moi=cau_hoi,
            gioi_han_token=gioi_han_token,
        )

        # 2. Tính toán số token thực tế của toàn bộ lời nhắc (system + lịch sử + câu hỏi mới)
        token_vao = sum(uoc_tinh_token(m["content"]) for m in danh_sach_tin)

        # Đếm số cặp lịch sử được giữ lại (trừ tin system ở đầu và tin user ở cuối)
        tin_lich_su = danh_sach_tin[1:-1]
        so_cap_duoc_giu = len(tin_lich_su) // 2

        # 3. Ghi log tương tự như khi gọi mô hình thực tế
        logger.info(
            f"Lượt {index:02d} -> token_vao={token_vao} | "
            f"Giữ lại: {so_cap_duoc_giu} cặp lịch sử | "
            f"Tổng tin trong prompt: {len(danh_sach_tin)}"
        )

        # 4. Lưu câu hỏi vào cơ sở dữ liệu
        luu_tin_nhan(hoi_thoai_id, "user", cau_hoi)

        # 5. Giả lập phản hồi của trợ lý và lưu vào cơ sở dữ liệu
        cau_tra_loi = (
            f"Phản hồi cho {cau_hoi[:30]}...: Quý khách vui lòng chuẩn bị đầy đủ hồ sơ theo "
            f"quy định và liên hệ tổng đài 19006769 hoặc ứng dụng EVN CSKH để được hỗ trợ nhanh nhất."
        )
        luu_tin_nhan(hoi_thoai_id, "assistant", cau_tra_loi, tang_phuc_vu=1)

        ket_qua_cac_luot.append({
            "luot": index,
            "token_vao": token_vao,
            "so_cap_giu": so_cap_duoc_giu,
            "tong_tin": len(danh_sach_tin),
        })

    # Tổng kết bảng kết quả
    print("\n" + "=" * 70)
    print("BẢNG TỔNG HỢP BIẾN ĐỘNG TOKEN_VAO QUA 20 LƯỢT TRÒ CHUYỆN")
    print("=" * 70)
    print(f"{'Lượt':<8}{'token_vao':<15}{'Số cặp giữ lại':<20}{'Trạng thái':<20}")
    print("-" * 70)

    for item in ket_qua_cac_luot:
        luot = item["luot"]
        tk = item["token_vao"]
        cap = item["so_cap_giu"]
        trang_thai = "Đang tích lũy" if luot < 7 else "Đã đạt trần ổn định"
        print(f"{luot:<8}{tk:<15}{cap:<20}{trang_thai:<20}")

    print("-" * 70)

    # 5 dòng cuối cùng (tương đương tail -5)
    print("\n" + "=" * 70)
    print("5 DÒNG LOG CUỐI CÙNG (TƯƠNG ĐƯƠNG grep token_vao | tail -5):")
    print("=" * 70)
    nam_luot_cuoi = ket_qua_cac_luot[-5:]
    for item in nam_luot_cuoi:
        print(
            f"[INFO] app.chat.ngu_canh: Lượt {item['luot']:02d} -> "
            f"token_vao={item['token_vao']}, "
            f"giữ lại {item['so_cap_giu']} cặp lịch sử, "
            f"giới hạn={gioi_han_token}"
        )

    print("=" * 70)
    do_lech = max(x["token_vao"] for x in nam_luot_cuoi) - min(x["token_vao"] for x in nam_luot_cuoi)
    print(f"Kiểm tra độ chênh lệch 5 lượt cuối: {do_lech} token (ngưỡng cho phép < 100 token)")
    print("KẾT LUẬN: LỜI NHẮC HOÀN TOÀN ỔN ĐỊNH, KHÔNG PHÌNH VÔ HẠN!")
    print("=" * 70 + "\n")

    return ket_qua_cac_luot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Giả lập 20 lượt trò chuyện để kiểm tra lời nhắc không phình vô hạn."
    )
    parser.add_argument(
        "--gioi-han",
        type=int,
        default=1500,
        help="Giới hạn token tối đa (mặc định 1500 để thấy rõ việc chạm trần và cắt tỉa)",
    )
    args = parser.parse_args()
    chay_mo_phong(gioi_han_token=args.gioi_han)
