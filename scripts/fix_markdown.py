#!/usr/bin/env python3
"""Tự động sửa lỗi định dạng Markdown sau khi agent ghi tệp.

Dùng làm hook PostToolUse của Claude Code: đọc payload JSON từ stdin, lấy đường
dẫn tệp mà agent vừa ghi, và chạy `markdownlint-cli2 --fix` nếu đó là tệp .md.

Hook luôn thoát với mã 0 để không chặn luồng làm việc của agent; nếu còn lỗi
không tự sửa được thì in cảnh báo ra stderr cho agent đọc và sửa tay.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Thư mục bị loại trừ, khớp với "ignores" trong .markdownlint-cli2.jsonc
THU_MUC_BO_QUA = (".venv", "node_modules", ".pytest_cache", ".remember")
DUONG_DAN_BO_QUA = (Path(".agents") / "skills",)


def lay_duong_dan_tu_stdin() -> Path | None:
    """Đọc payload hook và trả về đường dẫn tệp Markdown cần xử lý."""
    du_lieu = sys.stdin.read().strip()
    if not du_lieu:
        return None

    try:
        payload = json.loads(du_lieu)
    except json.JSONDecodeError:
        return None

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    duong_dan_tho = tool_input.get("file_path")
    if not isinstance(duong_dan_tho, str) or not duong_dan_tho:
        return None

    return Path(duong_dan_tho)


def can_bo_qua(duong_dan: Path, goc_du_an: Path) -> bool:
    """Kiểm tra tệp có nằm trong vùng loại trừ hay không."""
    try:
        tuong_doi = duong_dan.resolve().relative_to(goc_du_an)
    except ValueError:
        # Tệp nằm ngoài dự án thì không đụng tới
        return True

    if any(phan in THU_MUC_BO_QUA for phan in tuong_doi.parts):
        return True

    return any(tuong_doi.is_relative_to(mau) for mau in DUONG_DAN_BO_QUA)


def main() -> int:
    duong_dan = lay_duong_dan_tu_stdin()
    if duong_dan is None or duong_dan.suffix.lower() != ".md":
        return 0

    if not duong_dan.is_file():
        return 0

    goc_du_an = Path(
        os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent
    ).resolve()

    if can_bo_qua(duong_dan, goc_du_an):
        return 0

    npx = shutil.which("npx")
    if npx is None:
        print("Bỏ qua sửa Markdown: không tìm thấy npx trên PATH.", file=sys.stderr)
        return 0

    lenh = [npx, "--yes", "markdownlint-cli2", "--fix", str(duong_dan)]

    try:
        ket_qua = subprocess.run(
            lenh,
            cwd=goc_du_an,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("Bỏ qua sửa Markdown: markdownlint-cli2 chạy quá 120 giây.", file=sys.stderr)
        return 0
    except OSError as loi:
        print(f"Bỏ qua sửa Markdown: không chạy được markdownlint-cli2 ({loi}).", file=sys.stderr)
        return 0

    if ket_qua.returncode != 0:
        # --fix đã xử lý hết phần sửa được; phần còn lại agent phải sửa tay.
        thong_bao = (ket_qua.stdout or "") + (ket_qua.stderr or "")
        print(
            "Còn lỗi markdownlint phải sửa tay trong "
            f"{duong_dan}:\n{thong_bao.strip()}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
