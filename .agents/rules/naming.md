# Quy Chuẩn Đặt Tên Trong Dự Án (Naming Rules)

Tài liệu này quy định chuẩn đặt tên thống nhất cho toàn bộ tệp, thư mục, biến,
hàm, lớp, cấu hình và tài liệu trong hệ thống Chatbot EVN.

## 1. Nguyên Tắc Cốt Lõi

1. **Rõ nghĩa và Thể hiện Mục đích (Intention-Revealing):** Tên phải trả lời được:
   *đối tượng này là gì, nó đại diện cho cái gì, và nó làm nhiệm vụ gì*.
2. **Tuyệt đối KHÔNG dùng tiếng Việt có dấu:** Cấm hoàn toàn việc đặt tên tệp,
   thư mục, biến, hàm, lớp, gói hoặc biến môi trường có dấu tiếng Việt. Tất cả
   định danh phải dùng 100% ký tự ASCII chuẩn `[a-z0-9-_.]`.
3. **Nhất quán:** Một khái niệm nghiệp vụ chỉ dùng đúng một danh từ/động từ
   xuyên suốt dự án (ví dụ: dùng `hoi_thoai` thì không dùng xen kẽ `cuoc_tro_chuyen`,
   `chat_session`, `conversation`).

## 2. Quy Chuẩn Đặt Tên Tệp và Thư Mục

| Đối tượng | Quy chuẩn | Ví dụ ĐÚNG | Ví dụ SAI (CẤM) |
| :--- | :--- | :--- | :--- |
| **Tài liệu Markdown** | `kebab-case` không dấu | `debug.md`, `kien-truc.md` | `gỡ-lỗi.md`, `báo_cáo.md` |
| **Mã nguồn Python** | `snake_case` không dấu | `nhat_ky.py`, `ngu_canh.py` | `nhật_ký.py`, `NhatKy.py` |
| **Tệp kiểm thử** | Tiền tố `test_` + `snake_case` | `test_nhat_ky.py` | `test-nhat-ky.py`, `testNhatKy.py` |
| **Thư mục dự án** | `kebab-case` hoặc `snake_case` | `app/chat/`, `web/assets/` | `tài-liệu/`, `Thư Mục/` |
| **Tệp cấu hình** | `kebab-case` hoặc `snake_case` | `models.yaml`, `docker-compose.yml` | `CấuHình.yaml` |

## 3. Quy Chuẩn Đặt Tên Trong Mã Nguồn

### 3.1. Tên Biến và Thuộc Tính (`snake_case`)

- Dùng tiếng Việt không dấu hoặc tiếng Anh nhất quán.
- Biến logic (boolean) phải có tiền tố xác định trạng thái: `la_`, `co_`, `da_`,
  `is_`, `has_`, `can_`.
  - ĐÚNG: `da_luu_tin_nhan`, `la_quan_tri`, `co_quyen_truy_cap`.
  - SAI: `luu`, `admin_flag`, `status1`.
- Tránh đặt tên chung chung vô nghĩa: `data`, `temp`, `info`, `res`, `obj`.
  - ĐÚNG: `thong_tin_nguoi_dung`, `ket_qua_goi_mo_hinh`, `ban_ghi_nhat_ky`.

### 3.2. Tên Hàm và Phương Thức (`snake_case`)

- Bắt đầu bằng một động từ thể hiện hành động: `lay_`, `tao_`, `cap_nhat_`,
  `xoa_`, `tinh_`, `kiem_tra_`, `sinh_`.
  - ĐÚNG: `sinh_ma_yeu_cau()`, `kiem_tra_han_muc()`, `dung_ngu_canh()`.
  - SAI: `ma_yeu_cau()`, `process()`, `handle()`, `do_stuff()`.

### 3.3. Tên Lớp (Class), TypeVar và Enum (`PascalCase`)

- Dùng danh từ hoặc cụm danh từ mô tả bản chất của thực thể.
  - ĐÚNG: `DinhDangNhatKyJson`, `KetQuaGoi`, `NguoiDungDB`, `YeuCauChatStream`.
  - SAI: `dinh_dang_json`, `ketquagoi`, `nguoidung`.

### 3.4. Tên Hằng Số và Biến Môi Trường (`UPPER_SNAKE_CASE`)

- Viết hoa toàn bộ, phân cách bằng dấu gạch dưới `_`.
  - ĐÚNG: `GHI_NOI_DUNG`, `NGAN_SACH_NGAY_USD`, `HAN_MUC_IP_PHUT`.
  - SAI: `ghi_noi_dung`, `NganSachNgayUsd`.

## 4. Bảng Tra Cứu Các Sai Lầm Cần Tránh

```text
[CẤM] docs/gỡ-lỗi.md         --> [ĐÚNG] docs/debug.md hoặc docs/go-loi.md
[CẤM] app/core/nhật_ký.py    --> [ĐÚNG] app/core/nhat_ky.py
[CẤM] def gửi_tin_nhắn()     --> [ĐÚNG] def gui_tin_nhan()
[CẤM] class bộ_định_tuyến    --> [ĐÚNG] class BoDinhTuyen
[CẤM] let a, b, c = ...      --> [ĐÚNG] let tong_tien, so_luong, ma_don = ...
```
