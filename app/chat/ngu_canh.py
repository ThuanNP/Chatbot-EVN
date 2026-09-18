"""Quản lý cửa sổ ngữ cảnh và cắt tỉa lịch sử hội thoại cho Chatbot EVN.

Đảm bảo tuân thủ nghiêm ngặt các quy tắc:
1. Luôn giữ lời nhắc hệ thống đọc từ prompts/he_thong.md ở đầu danh sách.
2. Cắt tỉa theo CẶP tin nhắn (một lượt hỏi kèm một lượt đáp), tuyệt đối không cắt lẻ.
3. Giới hạn token mặc định đặt an toàn theo tầng có cửa sổ nhỏ nhất trong 4 tầng (OpenRouter Auto: 8k context, trừ 4k output -> an toàn 4096 token).
4. Ước tính token bằng công thức xấp xỉ (heuristic) có ghi chú rõ ràng.
"""

from pathlib import Path
import logging
from typing import Dict, List, Optional, Tuple

from app.config import DUONG_DAN_GOC
from app.core.database import TinNhan
from app.chat.hoi_thoai import lay_tin_nhan_hoi_thoai

logger = logging.getLogger(__name__)

# Đường dẫn tới tệp lời nhắc hệ thống trung lập
DUONG_DAN_PROMPT_HE_THONG = DUONG_DAN_GOC / "prompts" / "he_thong.md"

# Giới hạn token an toàn mặc định dựa trên tầng có cửa sổ nhỏ nhất trong 4 tầng:
# - Tầng 1 (Gemini 3.6 Flash): > 1.000.000 token
# - Tầng 2 (OpenRouter Auto): Dự phòng tới các model có context nhỏ nhất 8.192 token
# - Tầng 3 (Claude 3.5 Haiku): 200.000 token
# - Tầng 4 (GPT-4o Mini): 128.000 token
# Cửa sổ nhỏ nhất = 8.192 token.
# Trừ đi token dự trữ cho phản hồi đầu ra (gioi_han_token_ra = 4.096 token trong config/models.yaml):
# 8.192 - 4.096 = 4.096 token an toàn tối đa cho toàn bộ prompt đầu vào (system + lịch sử).
GIOI_HAN_TOKEN_AN_TOAN_MAC_DINH: int = 4096


def uoc_tinh_token(van_ban: str) -> int:
    """Ước tính số lượng token của một đoạn văn bản bằng công thức xấp xỉ (heuristic).

    LƯU Ý QUAN TRỌNG:
    Đây là CÔNG THỨC XẤP XỈ, không phải tokenizer chính xác 100% của từng nhà cung cấp
    (Google Gemini, OpenRouter, Anthropic Claude, OpenAI).
    Đối với tiếng Việt có dấu, trung bình 1 từ xấp xỉ 1.2 - 1.5 token, hoặc 1 token trên
    mỗi 2.5 - 3.5 ký tự UTF-8. Công thức này kết hợp số từ và chiều dài ký tự kèm hệ số
    an toàn và 4 token overhead cấu trúc tin nhắn chuẩn OpenAI chat format.
    """
    if not van_ban:
        return 0

    van_ban_str = van_ban.strip()
    if not van_ban_str:
        return 0

    so_tu = len(van_ban_str.split())
    so_ky_tu = len(van_ban_str)

    # Ước tính: 1.3 token mỗi từ + 0.15 token mỗi ký tự bù cho dấu thanh tiếng Việt
    token_noi_dung = int(so_tu * 1.3 + so_ky_tu * 0.15)
    # Cộng 4 token overhead cấu trúc metadata cho mỗi tin nhắn (role, format, delims)
    return max(1, token_noi_dung) + 4


def doc_loi_nhac_he_thong() -> str:
    """Đọc nội dung lời nhắc hệ thống từ tệp prompts/he_thong.md.

    Nếu tệp không tồn tại hoặc lỗi đọc, trả về lời nhắc hệ thống dự phòng tiêu chuẩn.

    Returns:
        str: Nội dung lời nhắc hệ thống
    """
    if DUONG_DAN_PROMPT_HE_THONG.exists():
        try:
            with open(DUONG_DAN_PROMPT_HE_THONG, "r", encoding="utf-8") as f:
                noi_dung = f.read().strip()
                if noi_dung:
                    return noi_dung
        except Exception as e:
            logger.warning(f"Không thể đọc {DUONG_DAN_PROMPT_HE_THONG}: {e}. Dùng prompt dự phòng.")

    return (
        "Bạn là trợ lý AI thông minh chính thức của Tập đoàn Điện lực Việt Nam (EVN). "
        "Hãy hỗ trợ người dùng giải đáp các thắc mắc về nghiệp vụ và dịch vụ ngành điện "
        "một cách lịch sự, chuẩn xác, trung thực và rõ ràng."
    )


def _gom_nhom_thanh_cac_cap(
    danh_sach_tin_nhan: List[TinNhan],
) -> Tuple[List[Tuple[TinNhan, TinNhan]], Optional[TinNhan]]:
    """Gom nhóm danh sách tin nhắn thành các cặp hội thoại (user, assistant).

    Nếu tin nhắn cuối cùng là của 'user' (lượt hỏi hiện tại đang chờ phản hồi),
    nó sẽ được tách riêng ra làm câu hỏi hiện tại.
    Các tin nhắn trước đó được ghép thành các cặp hoàn chỉnh (user, assistant).
    Bất kỳ tin nhắn mồ côi nào không đủ cặp trong quá khứ sẽ bị bỏ qua để bảo đảm
    mô hình không bị phân tâm hoặc trả lời lệch lạc.

    Args:
        danh_sach_tin_nhan: Danh sách tin nhắn sắp xếp theo thời gian tăng dần

    Returns:
        Tuple[List[Tuple[TinNhan, TinNhan]], Optional[TinNhan]]:
            (Danh sách các cặp (user, assistant) từ cũ đến mới, Tin nhắn user hiện tại nếu có)
    """
    if not danh_sach_tin_nhan:
        return [], None

    tin_nhan_cuoi = danh_sach_tin_nhan[-1]
    tin_nhan_user_hien_tai: Optional[TinNhan] = None
    lich_su = list(danh_sach_tin_nhan)

    # Nếu tin nhắn cuối cùng là của user, đó chính là câu hỏi hiện tại
    if tin_nhan_cuoi.vai_tro == "user":
        tin_nhan_user_hien_tai = tin_nhan_cuoi
        lich_su = lich_su[:-1]

    cac_cap: List[Tuple[TinNhan, TinNhan]] = []
    i = len(lich_su) - 1

    # Duyệt ngược từ cuối lịch sử về trước để gom cặp (user, assistant)
    while i >= 1:
        tin_sau = lich_su[i]
        tin_truoc = lich_su[i - 1]

        if tin_truoc.vai_tro == "user" and tin_sau.vai_tro == "assistant":
            cac_cap.append((tin_truoc, tin_sau))
            i -= 2
        else:
            # Bỏ qua tin nhắn không tạo thành cặp hợp lệ để tránh cắt lẻ
            i -= 1

    # Đảo lại theo thứ tự thời gian từ cũ đến mới
    cac_cap.reverse()
    return cac_cap, tin_nhan_user_hien_tai


def dung_ngu_canh(
    hoi_thoai_id: Optional[str] = None,
    gioi_han_token: int = GIOI_HAN_TOKEN_AN_TOAN_MAC_DINH,
    tin_nhan_moi: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Xây dựng và cắt tỉa danh sách tin nhắn đưa vào lời nhắc của mô hình.

    Quy trình thực hiện:
    1. Luôn giữ lời nhắc hệ thống đọc từ prompts/he_thong.md ở vị trí đầu tiên.
    2. Xác định câu hỏi người dùng hiện tại (từ tin_nhan_moi hoặc tin nhắn user mới nhất).
    3. Cắt theo CẶP tin nhắn (một lượt hỏi kèm một lượt đáp), đi ngược về quá khứ
       cho tới khi chạm giới hạn token. Tuyệt đối không cắt lẻ một nửa cặp.
    4. Giới hạn token mặc định (4096) đảm bảo an toàn cho cả tầng có context nhỏ nhất.

    Args:
        hoi_thoai_id: Mã định danh phiên hội thoại (nếu có)
        gioi_han_token: Giới hạn token tối đa cho toàn bộ prompt đầu vào
        tin_nhan_moi: Nội dung tin nhắn người dùng mới nếu chưa kịp lưu vào DB

    Returns:
        List[Dict[str, str]]: Danh sách tin nhắn theo định dạng chuẩn [{'role': '...', 'content': '...'}]
    """
    # 1. Luôn giữ lời nhắc hệ thống
    noi_dung_he_thong = doc_loi_nhac_he_thong()
    token_he_thong = uoc_tinh_token(noi_dung_he_thong)

    tin_nhan_system = {"role": "system", "content": noi_dung_he_thong}

    # 2. Xác định câu hỏi hiện tại
    noi_dung_user_hien_tai: Optional[str] = None
    if tin_nhan_moi and tin_nhan_moi.strip():
        noi_dung_user_hien_tai = tin_nhan_moi.strip()

    # Lấy lịch sử tin nhắn trong cơ sở dữ liệu nếu có hoi_thoai_id
    danh_sach_db: List[TinNhan] = []
    if hoi_thoai_id:
        danh_sach_db = lay_tin_nhan_hoi_thoai(hoi_thoai_id)

    cac_cap_lich_su, user_cuoi_db = _gom_nhom_thanh_cac_cap(danh_sach_db)

    # Nếu chưa có tin_nhan_moi truyền vào nhưng DB có tin nhắn user cuối cùng
    if noi_dung_user_hien_tai is None and user_cuoi_db is not None:
        noi_dung_user_hien_tai = user_cuoi_db.noi_dung

    token_user_hien_tai = (
        uoc_tinh_token(noi_dung_user_hien_tai) if noi_dung_user_hien_tai else 0
    )

    # Ngân sách token còn lại dành cho các cặp lịch sử trong quá khứ
    ngan_sach_lich_su = gioi_han_token - token_he_thong - token_user_hien_tai

    cac_cap_duoc_chon: List[Tuple[TinNhan, TinNhan]] = []

    # 3. Lấy các tin nhắn gần nhất đi ngược về quá khứ cho tới khi chạm giới hạn token
    # Cắt theo CẶP tin nhắn (một lượt hỏi kèm một lượt đáp), không cắt lẻ
    if ngan_sach_lich_su > 0 and cac_cap_lich_su:
        token_tich_luy = 0
        # Duyệt ngược từ cặp gần nhất về quá khứ
        for cap in reversed(cac_cap_lich_su):
            tin_user, tin_bot = cap
            token_user = tin_user.token_uoc_tinh or uoc_tinh_token(tin_user.noi_dung)
            token_bot = tin_bot.token_uoc_tinh or uoc_tinh_token(tin_bot.noi_dung)
            token_ca_cap = token_user + token_bot

            if token_tich_luy + token_ca_cap <= ngan_sach_lich_su:
                cac_cap_duoc_chon.append(cap)
                token_tich_luy += token_ca_cap
            else:
                # Chạm giới hạn token: DỪNG LẠI NGAY, không nhận lẻ một nửa cặp
                break

        # Đảo lại theo thứ tự thời gian từ cũ đến mới
        cac_cap_duoc_chon.reverse()

    # 4. Lắp ráp danh sách tin nhắn hoàn chỉnh
    ket_qua: List[Dict[str, str]] = [tin_nhan_system]

    for tin_u, tin_b in cac_cap_duoc_chon:
        ket_qua.append({"role": "user", "content": tin_u.noi_dung})
        ket_qua.append({"role": "assistant", "content": tin_b.noi_dung})

    if noi_dung_user_hien_tai is not None:
        ket_qua.append({"role": "user", "content": noi_dung_user_hien_tai})

    tong_token_uoc_tinh = sum(uoc_tinh_token(m["content"]) for m in ket_qua)
    logger.info(
        f"[Ngữ cảnh] Dựng ngữ cảnh: token_vao={tong_token_uoc_tinh}, "
        f"giữ lại {len(cac_cap_duoc_chon)}/{len(cac_cap_lich_su)} cặp hội thoại, "
        f"giới hạn token={gioi_han_token}",
        extra={
            "chang": "dung_ngu_canh",
            "token_vao": tong_token_uoc_tinh,
            "so_cap_giu_lai": len(cac_cap_duoc_chon),
            "tong_so_cap": len(cac_cap_lich_su),
            "do_dai_tin_nhan": len(noi_dung_user_hien_tai) if noi_dung_user_hien_tai else 0,
        },
    )

    return ket_qua
