#!/usr/bin/env python3
"""Script dòng lệnh tạo người dùng và sinh mã thông báo (Bearer token) cho Chatbot EVN.

Mã thông báo được sinh ngẫu nhiên an toàn, sau đó được băm mật khẩu chuẩn
bằng HMAC-SHA256 kết hợp APP_SECRET và lưu vào cơ sở dữ liệu.
Mã thông báo thô CHỈ ĐƯỢC HIỂN THỊ ĐÚNG MỘT LẦN duy nhất khi chạy script này.

Sử dụng:
    python scripts/tao_nguoi_dung.py --email thu@vidu.com --bac free
    python scripts/tao_nguoi_dung.py --email quan_tri@vidu.com --bac pro
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

# Đảm bảo thư mục gốc dự án có trong sys.path để import gói app
THU_MUC_GOC = Path(__file__).resolve().parent.parent
if str(THU_MUC_GOC) not in sys.path:
    sys.path.insert(0, str(THU_MUC_GOC))

from sqlalchemy import select

from app.core.database import NguoiDung, khoi_tao_db, lay_phien_db
from app.core.han_muc import bam_ma_thong_bao, sinh_ma_thong_bao_ngau_nhien


def tao_hoac_cap_nhat_nguoi_dung(email: str, bac: str = "free") -> str:
    """Tạo mới hoặc cập nhật token cho người dùng trong cơ sở dữ liệu.

    Args:
        email: Địa chỉ email của người dùng
        bac: Bậc tài khoản ('free' hoặc 'pro')

    Returns:
        str: Mã token thô (hiển thị đúng 1 lần duy nhất)
    """
    khoi_tao_db()
    token_tho = sinh_ma_thong_bao_ngau_nhien()
    token_hash = bam_ma_thong_bao(token_tho)
    prefix = token_tho[:12] + "..."

    email_chuan = email.strip().lower()
    bac_chuan = bac.strip().lower()

    if bac_chuan not in ("free", "pro"):
        raise ValueError(f"Bậc không hợp lệ: '{bac}'. Chỉ chấp nhận 'free' hoặc 'pro'.")

    with lay_phien_db() as phien:
        stmt = select(NguoiDung).where(NguoiDung.email == email_chuan)
        nguoi_dung = phien.execute(stmt).scalar_one_or_none()

        if nguoi_dung:
            nguoi_dung.bac = bac_chuan
            nguoi_dung.token_hash = token_hash
            nguoi_dung.token_prefix = prefix
            nguoi_dung.kich_hoat = True
            nguoi_dung.cap_nhat_luc = datetime.now(timezone.utc)
            nguoi_dung_id = nguoi_dung.id
            hanh_dong = "CẬP NHẬT MÃ TOKEN CHO NGƯỜI DÙNG HIỆN CÓ"
        else:
            nguoi_dung_id = str(uuid.uuid4())
            nguoi_dung_moi = NguoiDung(
                id=nguoi_dung_id,
                email=email_chuan,
                bac=bac_chuan,
                token_hash=token_hash,
                token_prefix=prefix,
                kich_hoat=True,
                tao_luc=datetime.now(timezone.utc),
                cap_nhat_luc=datetime.now(timezone.utc),
            )
            phien.add(nguoi_dung_moi)
            hanh_dong = "TẠO NGƯỜI DÙNG MỚI THÀNH CÔNG"

    print("=" * 72)
    print(f" {hanh_dong}")
    print("=" * 72)
    print(f" ID        : {nguoi_dung_id}")
    print(f" Email     : {email_chuan}")
    print(f" Bậc       : {bac_chuan}")
    print(f" Mã Token  : {token_tho}")
    print("-" * 72)
    print(" LƯU Ý BẢO MẬT QUAN TRỌNG:")
    print(" 1. Mã token thô trên CHỈ ĐƯỢC HIỂN THỊ ĐÚNG MỘT LẦN DUY NHẤT.")
    print(" 2. Hệ thống lưu dạng băm HMAC-SHA256, tuyệt đối không lưu mã thô.")
    print(" 3. Vui lòng sao chép và lưu trữ mã token cẩn thận.")
    print("-" * 72)
    print(" Ví dụ kiểm thử với curl:")
    print(f' curl.exe -s -H "Authorization: Bearer {token_tho}" http://localhost:8000/toi')
    print("=" * 72)

    return token_tho


def main():
    """Hàm chạy chính từ dòng lệnh CLI."""
    parser = argparse.ArgumentParser(
        description="Tạo người dùng và sinh mã thông báo Bearer token cho Chatbot EVN."
    )
    parser.add_argument(
        "--email",
        type=str,
        required=True,
        help="Địa chỉ email người dùng (ví dụ: thu@vidu.com)",
    )
    parser.add_argument(
        "--bac",
        type=str,
        choices=["free", "pro"],
        default="free",
        help="Bậc tài khoản: 'free' (mặc định) hoặc 'pro'",
    )

    args = parser.parse_args()

    try:
        tao_hoac_cap_nhat_nguoi_dung(email=args.email, bac=args.bac)
    except Exception as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
