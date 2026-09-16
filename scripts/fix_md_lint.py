"""Kịch bản chuẩn hoá định dạng Markdown cho các tệp artifact và tài liệu."""
from pathlib import Path

WALKTHROUGH_CONTENT = """# Kết quả thực hiện: Phát theo dòng (Streaming) với chuỗi dự phòng cho Chatbot EVN

Đã mở rộng thành công [router.py](file:///d:/Source/Repos/Chatbot-EVN/app/llm/router.py), bổ sung endpoint Server-Sent Events trong [main.py](file:///d:/Source/Repos/Chatbot-EVN/app/main.py), và hoàn thành bộ kiểm thử [test_stream.py](file:///d:/Source/Repos/Chatbot-EVN/tests/test_stream.py).

## Các thay đổi đã thực hiện

### 1. Mở rộng bộ định tuyến mô hình ([router.py](file:///d:/Source/Repos/Chatbot-EVN/app/llm/router.py))

- **Định nghĩa dataclass `ManhPhatRa`**:
  - Hỗ trợ 3 dạng mảnh: `manh` (nội dung mới `doan_van_ban`), `xong` (kết thúc kèm đầy đủ siêu dữ liệu `KetQuaGoi`), `loi` (lỗi giữa chừng kèm `thong_diep_loi` và `van_ban_da_nhan`).
  - Cung cấp các thuộc tính siêu dữ liệu trực tiếp: `tang_phuc_vu`, `ten_model`, `token_vao`, `token_ra`, `do_tre_ms`, `chi_phi_usd`, `so_lan_thu`, `danh_sach_tang_da_hong`.
- **Hàm `goi_mo_hinh_theo_dong`**:
  - Duyệt `chuoi_du_phong` từ cấu hình `config/models.yaml`, bỏ qua các tầng thiếu khoá API.
  - **Phát chữ dần dần (Progressive Token Pacing)**: Tự động tách các khối văn bản lớn trả về từ nhà cung cấp mô hình thành các từ/mảnh tự nhiên với nhịp độ 20ms/mảnh, giúp loại bỏ hiện tượng nhận dồn một cục rồi bung ra cùng lúc, tạo trải nghiệm gõ chữ dần dần sống động và liên tục.
  - **Tình huống khó 1 (Lỗi trước mảnh đầu)**: Khi gặp lỗi trước khi phát mảnh nội dung đầu tiên (`da_phat_manh_dau == False`), tự động thử lại (nếu là lỗi tạm thời) hoặc rơi xuống tầng tiếp theo bình thường mà không ảnh hưởng tới người dùng.
  - **Tình huống khó 2 (Lỗi giữa chừng)**: Khi gặp lỗi sau khi đã phát ít nhất 1 mảnh nội dung (`da_phat_manh_dau == True`), **không rơi tầng** để tránh lặp lại câu trả lời; thay vào đó ghi log chi tiết, phát mảnh lỗi kèm văn bản đã nhận và dừng luồng.
  - **Ghi log đầy đủ theo Quy tắc 4 AGENTS.md**: Tầng phục vụ, model, token vào, token ra, chi phí ước tính, độ trễ.

### 2. Thêm endpoint SSE ([main.py](file:///d:/Source/Repos/Chatbot-EVN/app/main.py))

- Thêm model dữ liệu `YeuCauChatStream` linh hoạt (hỗ trợ `tin_nhan`, `messages`, hoặc `prompt`).
- Endpoint `POST /chat/stream`:
  - Trả về `StreamingResponse` với `media_type="text/event-stream"`.
  - Thiết lập header hạ tầng chống gom đệm proxy ngược:
    - `X-Accel-Buffering: no`
    - `Cache-Control: no-cache`
    - `Connection: keep-alive`
  - Đóng gói mỗi sự kiện là một dòng SSE: `data: <JSON>\\n\\n` với 3 loại: `manh`, `xong`, `loi`.

### 3. Bộ kiểm thử ([test_stream.py](file:///d:/Source/Repos/Chatbot-EVN/tests/test_stream.py))

- `test_luong_phat_thanh_cong_it_nhat_hai_manh_va_manh_xong_du_sieu_du_lieu`: Kiểm chứng luồng phát ít nhất 2 mảnh nội dung rồi tới mảnh xong mang đủ 8 trường siêu dữ liệu.
- `test_tinh_huong_1_loi_truoc_manh_dau_roi_xuong_tang_sau`: Xác nhận khi tầng 1 lỗi 429 trước mảnh đầu, luồng tự rơi tầng 2 thành công và không báo lỗi cho người dùng.
- `test_tinh_huong_2_loi_giua_chung_khong_roi_tang_phat_manh_loi`: Xác nhận khi đứt kết nối giữa chừng, luồng dừng ngay, không rơi tầng 2, phát mảnh lỗi kèm văn bản đã nhận.
- `test_ca_bon_tang_loi_truoc_manh_dau_nem_tat_ca_tang_deu_hong`: Xác nhận ném `TatCaTangDeuHongError` khi tất cả các tầng đều hỏng.
- `test_loi_dau_vao_400_truoc_manh_dau_nem_loi_ngay`: Xác nhận lỗi đầu vào (400) ném `LoiDauVaoError` ngay, không rơi tầng.
- `test_endpoint_post_chat_stream_sse_headers_va_du_lieu`: Kiểm tra headers hạ tầng và cấu trúc sự kiện SSE qua client HTTP.
- `test_endpoint_post_chat_stream_loi_giua_chung_tra_ve_sse_loi`: Kiểm tra endpoint phát sự kiện SSE loại `loi` khi có sự cố giữa chừng.

## Kết quả kiểm thử

Toàn bộ 18 test cases đã chạy thành công:

```text
tests/test_config.py::test_khong_co_gia_tri_mac_dinh_cho_khoa_api PASSED [  5%]
tests/test_config.py::test_cai_dat_moi_truong_thieu_khoa_that_bai PASSED [ 11%]
tests/test_config.py::test_doc_cau_hinh_models_yaml PASSED               [ 16%]
tests/test_config.py::test_lay_cau_hinh_he_thong PASSED                  [ 22%]
tests/test_router.py::test_tang_1_thanh_cong_khong_cham_tang_2 PASSED    [ 27%]
tests/test_router.py::test_tang_1_429_lien_tiep_roi_xuong_tang_2 PASSED  [ 33%]
tests/test_router.py::test_tang_1_401_khong_thu_lai_roi_tang_ngay PASSED [ 38%]
tests/test_router.py::test_ca_bon_tang_hong_nem_ngoai_le_du_bon_ly_do PASSED [ 44%]
tests/test_router.py::test_loi_dau_vao_400_nem_ngay_khong_roi_tang PASSED [ 50%]
tests/test_router.py::test_thieu_khoa_api_bo_qua_lang_le PASSED          [ 55%]
tests/test_router.py::test_phat_theo_dong_thanh_cong PASSED              [ 61%]
tests/test_stream.py::test_luong_phat_thanh_cong_it_nhat_hai_manh_va_manh_xong_du_sieu_du_lieu PASSED [ 66%]
tests/test_stream.py::test_tinh_huong_1_loi_truoc_manh_dau_roi_xuong_tang_sau PASSED [ 72%]
tests/test_stream.py::test_tinh_huong_2_loi_giua_chung_khong_roi_tang_phat_manh_loi PASSED [ 77%]
tests/test_stream.py::test_ca_bon_tang_loi_truoc_manh_dau_nem_tat_ca_tang_deu_hong PASSED [ 83%]
tests/test_stream.py::test_loi_dau_vao_400_truoc_manh_dau_nem_loi_ngay PASSED [ 88%]
tests/test_stream.py::test_endpoint_post_chat_stream_sse_headers_va_du_lieu PASSED [ 94%]
tests/test_stream.py::test_endpoint_post_chat_stream_loi_giua_chung_tra_ve_sse_loi PASSED [100%]

============================= 18 passed in 4.83s ==============================
```
"""

PLAN_CONTENT = """# Kế Hoạch Triển Khai: Chi Phí, Trần Ngân Sách & Giám Sát Tỷ Lệ Rơi Tầng

## Tổng quan

Kế hoạch triển khai module tính toán chi phí `app/llm/chi_phi.py`, tích hợp vào bộ định tuyến `app/llm/router.py`, tạo bảng `luot_goi` trong cơ sở dữ liệu, kiểm soát trần ngân sách ngày `NGAN_SACH_NGAY_USD` (HTTP 503 khi vượt, cảnh báo ở mức 80%), và giám sát tỷ lệ rơi tầng 1 trong 1 giờ gần nhất (cảnh báo khi vượt 20%).

---

## Yêu Cầu Người Dùng Phê Duyệt (User Review Required)

> [!IMPORTANT]
> **Quy tắc bất biến theo AGENTS.md: Cần sự đồng ý của người dùng khi Đổi lược đồ cơ sở dữ liệu.**
>
> - Dự án sẽ bổ sung bảng mới `luot_goi` vào cơ sở dữ liệu (PostgreSQL / SQLite fallback cho kiểm thử) bằng SQLAlchemy với cấu trúc:
>   - Cột: `id`, `thoi_diem`, `nguoi_dung_id`, `tang`, `model`, `token_vao`, `token_ra`, `chi_phi_usd`, `do_tre_ms`, `thanh_cong`, `ghi_chu`.
>   - Chỉ mục: `ix_luot_goi_thoi_diem` trên `(thoi_diem)` và `ix_luot_goi_nguoi_dung_thoi_diem` trên `(nguoi_dung_id, thoi_diem)`.
> - Không cài thêm thư viện ngoài (sử dụng thư viện có sẵn trong `requirements.txt`: `SQLAlchemy 2.0`, `psycopg`, `pydantic-settings`, `pyyaml`, `fastapi`).

---

## Nội Dung Chi Tiết Các Phần

### Phần 1 - Ước tính chi phí & Ghi nhận lượt gọi (`app/llm/chi_phi.py`)

1. **Hàm `uoc_tinh_chi_phi(tang, token_vao, token_ra) -> float`**:
   - Nhận `tang` (số tầng 1-4 hoặc tên tầng), lấy đơn giá `gia_vao_usd_moi_trieu` và `gia_ra_usd_moi_trieu` trực tiếp từ cấu hình nạp từ `config/models.yaml`.
   - Tính toán chi phí ước tính theo công thức:
     $$\\text{chi\\_phi} = \\left(\\frac{\\text{token\\_vao}}{1.000.000} \\times \\text{gia\\_vao}\\right) + \\left(\\frac{\\text{token\\_ra}}{1.000.000} \\times \\text{gia\\_ra}\\right)$$
     (làm tròn 8 chữ số thập phân).
   - Giữ hàm `tinh_chi_phi_usd` hiện tại để bảo toàn tương thích ngược cho các đoạn mã đang gọi.
2. **Xử lý tầng `openrouter_auto`**:
   - Khi OpenRouter tự động phân giải mô hình phía sau, đọc trường `model` trả về từ phản hồi của nhà cung cấp (`phan_hoi.model` hoặc qua chunk stream).
   - Ghi nhật ký thông tin: ghi rõ model thực tế đã phục vụ kèm thông báo chi phí là ước tính thô (do cấu hình chỉ có giá tham chiếu).
   - Đánh dấu trường ghi chú `ghi_chu="uoc_tinh_tho"` khi lưu vào cơ sở dữ liệu.
3. **Ghi nhận vào bảng `luot_goi`**:
   - Hàm `ghi_nhan_luot_goi(...)` lưu một bản ghi vào bảng `luot_goi`:
     - `thoi_diem`: Thời điểm gọi (UTC).
     - `nguoi_dung_id`: Định danh người dùng (mặc định "khach" hoặc lấy từ tham số request).
     - `tang`: Tầng phục vụ (1, 2, 3, 4).
     - `model`: Model thực tế được dùng.
     - `token_vao`, `token_ra`: Số lượng token prompt và completion.
     - `chi_phi_usd`: Chi phí tính bằng USD.
     - `do_tre_ms`: Thời gian phản hồi tính bằng mili-giây.
     - `thanh_cong`: `True` nếu gọi thành công, `False` nếu gặp lỗi/thất bại.
     - `ghi_chu`: Thông tin bổ sung (ví dụ đánh dấu ước tính thô hoặc lý do lỗi nếu hỏng).

### Phần 2 - Trần ngân sách (`NGAN_SACH_NGAY_USD`)

1. **Kiểm tra trước mỗi lời gọi**:
   - Hàm `kiem_tra_ngan_sach()` truy vấn tổng chi phí tích luỹ trong ngày hiện tại (tính từ 00:00:00 UTC/ngày hiện tại).
   - Lấy ngân sách tối đa từ cấu hình `lay_cau_hinh().env.NGAN_SACH_NGAY_USD` (mặc định 10.0 USD).
   - **Vượt ngân sách**: Ném ngoại lệ `VuotNganSachError` (tương ứng HTTP 503) với thông điệp tiếng Việt thân thiện:
     *"Hệ thống đã đạt giới hạn ngân sách hàng ngày ({ngan_sach} USD). Vui lòng thử lại vào ngày mai hoặc liên hệ quản trị viên."*
     **Tuyệt đối KHÔNG gọi mô hình khi đã vượt trần.**
   - **Đạt từ 80% ngân sách**: Ghi log `WARNING` mỗi lần gọi:
     *"Cảnh báo ngân sách: Chi phí hôm nay (${chi_phi_hom_nay}) đã đạt {phan_tram}% ngân sách ngày (${ngan_sach})."*
2. **Endpoint `GET /chi-phi`**:
   - Trả về cấu trúc JSON:

     ```json
     {
       "chi_phi_hom_nay_usd": 0.452,
       "ngan_sach_ngay_usd": 10.0,
       "phan_tram_da_dung": 4.52,
       "phan_ra_theo_tang": {
         "1": 0.352,
         "2": 0.100,
         "3": 0.0,
         "4": 0.0
       },
       "so_luot_theo_tang": {
         "1": 45,
         "2": 2,
         "3": 0,
         "4": 0
       },
       "ty_le_roi_tang_1_gio_qua": 4.25
     }
     ```

### Phần 3 - Giám sát tỷ lệ rơi tầng (Fall-back Rate)

1. **Tính tỷ lệ trong 1 giờ gần nhất**:
   - Lấy toàn bộ lượt gọi trong khoảng thời gian `[bay_gio - 1h, bay_gio]`.
   - Tính tỷ lệ phần trăm số lượt KHÔNG được tầng 1 phục vụ thành công:
     $$\\text{ty\\_le\\_roi\\_tang} = \\frac{\\text{so\\_luot\\_khong\\_phai\\_tang\\_1\\_hoac\\_tang\\_1\\_hong}}{\\text{tong\\_so\\_luot\\_1h}} \\times 100\\%$$
2. **Cảnh báo khi vượt ngưỡng 20%**:
   - Khi tỷ lệ vượt 20%, ghi nhật ký cấp độ `WARNING`:
     *"CẢNH BÁO TỶ LỆ RƠI TẦNG CAO ({ty_le}% > 20% trong 1 giờ qua). Nguy cơ sự cố và chi phí tăng vọt. Lý do hỏng gần nhất của tầng 1: {ly_do_hong_tang_1}."*
3. **Đưa trường `ty_le_roi_tang_1_gio_qua` vào endpoint `GET /chi-phi`**.

---

## Thay Đổi Mã Nguồn Đề Xuất (Proposed Changes)

### 1. Cơ sở dữ liệu

#### [NEW] [app/core/database.py](file:///d:/Source/Repos/Chatbot-EVN/app/core/database.py)

- Định nghĩa SQLAlchemy Engine và Session tương thích với PostgreSQL (`postgresql+psycopg://`) và SQLite (dùng cho test/fallback khi chưa bật container Postgres).
- Định nghĩa model `LuotGoi` tương ứng với bảng `luot_goi` và các chỉ mục:
  - `Index("ix_luot_goi_thoi_diem", LuotGoi.thoi_diem)`
  - `Index("ix_luot_goi_nguoi_dung_thoi_diem", LuotGoi.nguoi_dung_id, LuotGoi.thoi_diem)`
- Cung cấp hàm `khoi_tao_db()` để tự động tạo bảng nếu chưa có.

### 2. Module chi phí & ngân sách

#### [MODIFY] [app/llm/chi_phi.py](file:///d:/Source/Repos/Chatbot-EVN/app/llm/chi_phi.py)

- Thêm ngoại lệ `VuotNganSachError`.
- Thêm hàm `uoc_tinh_chi_phi(tang, token_vao, token_ra) -> float`.
- Thêm hàm `ghi_nhan_luot_goi(...)` lưu lượt gọi vào bảng `luot_goi`.
- Thêm hàm `kiem_tra_ngan_sach()` kiểm tra tổng chi phí trong ngày, raise `VuotNganSachError` khi vượt, ghi warning khi >= 80%.
- Thêm hàm `tinh_ty_le_roi_tang_1h() -> tuple[float, str]` tính tỷ lệ rơi tầng 1 giờ qua và lấy lý do hỏng gần nhất của tầng 1.
- Thêm hàm `lay_thong_ke_chi_phi_ngay()` tổng hợp dữ liệu phục vụ endpoint `GET /chi-phi`.

### 3. Tích hợp bộ định tuyến

#### [MODIFY] [app/llm/router.py](file:///d:/Source/Repos/Chatbot-EVN/app/llm/router.py)

- Nối `kiem_tra_ngan_sach()` vào đầu hai hàm `goi_mo_hinh` và `goi_mo_hinh_theo_dong`. Nếu vượt ngân sách, từ chối ngay, không gọi bất kỳ mô hình nào.
- Kiểm tra tỷ lệ rơi tầng 1h và ghi log cảnh báo nếu > 20%.
- Khi gọi thành công:
  - Đối với tầng `openrouter_auto`, trích xuất model thực tế từ response, ghi log và đánh dấu ước tính thô.
  - Gọi `uoc_tinh_chi_phi(...)` để tính chi phí dựa trên `models.yaml`.
  - Ghi bản ghi vào bảng `luot_goi` với `thanh_cong=True`.
- Khi tầng thất bại:
  - Lưu lý do hỏng của tầng 1 nếu tầng 1 gặp lỗi.
  - Ghi bản ghi vào bảng `luot_goi` khi tất cả các tầng hỏng với `thanh_cong=False`.

### 4. API Endpoints

#### [MODIFY] [app/main.py](file:///d:/Source/Repos/Chatbot-EVN/app/main.py)

- Thêm endpoint `GET /chi-phi` trả về chi phí hôm nay, ngân sách ngày, phần trăm đã dùng, phân rã theo tầng, số lượt từng tầng, và tỷ lệ rơi tầng trong 1 giờ qua.
- Cập nhật endpoint `POST /chat/stream`:
  - Trước khi khởi tạo stream, kiểm tra ngân sách. Nếu vượt, trả về ngay HTTP 503 kèm thông điệp tiếng Việt thân thiện, không mở luồng gọi mô hình.
  - Bắt ngoại lệ `VuotNganSachError` trong generator SSE để phát ra thông báo lỗi nếu có.
- Gọi `khoi_tao_db()` khi khởi động ứng dụng (lifespan/startup).

### 5. Kiểm thử

#### [NEW] [tests/test_chi_phi.py](file:///d:/Source/Repos/Chatbot-EVN/tests/test_chi_phi.py)

- Kiểm thử hàm `uoc_tinh_chi_phi` theo các tầng trong `models.yaml`.
- Kiểm thử trần ngân sách:
  - Dưới ngân sách: cho phép gọi bình thường.
  - Đạt >= 80%: ghi log cảnh báo `WARNING`.
  - Vượt ngân sách: ném `VuotNganSachError` (HTTP 503) và KHÔNG gọi mô hình.
- Kiểm thử endpoint `GET /chi-phi` và các trường trả về.
- Kiểm thử giám sát tỷ lệ rơi tầng trong 1 giờ qua (dưới 20% và vượt 20% phát cảnh báo kèm lý do hỏng tầng 1).
- Kiểm thử model thực tế của `openrouter_auto` và đánh dấu chi phí ước tính thô.
- Đảm bảo toàn bộ 18 bài test hiện có trong `tests/test_router.py`, `tests/test_stream.py`, `tests/test_config.py` tiếp tục pass 100%.

---

## Kế Hoạch Xác Minh (Verification Plan)

### Kiểm thử tự động

1. Chạy toàn bộ pytest suite:

   ```powershell
   & "d:\\Source\\Repos\\Chatbot-EVN\\.venv\\Scripts\\python.exe" -m pytest
   ```

2. Chạy riêng bộ test mới `tests/test_chi_phi.py`:

   ```powershell
   & "d:\\Source\\Repos\\Chatbot-EVN\\.venv\\Scripts\\python.exe" -m pytest tests/test_chi_phi.py -v
   ```

### Kiểm thử thủ công

1. Gọi thử endpoint `GET /chi-phi` qua FastAPI TestClient hoặc curl.
2. Kiểm tra chỉ mục trên bảng `luot_goi` trong metadata của SQLAlchemy.
"""

def main():
    p1 = Path(r"c:\Users\ThuanNP\.gemini\antigravity-ide\brain\73c644ca-112b-475e-ba73-7fe87105d830\walkthrough.md")
    if p1.exists():
        p1.write_text(WALKTHROUGH_CONTENT.strip() + "\n", encoding="utf-8")
        print(f"Đã sửa {p1}")

    p2 = Path(r"c:\Users\ThuanNP\.gemini\antigravity-ide\brain\a82acadd-08fc-4a11-880d-decb7e5f745c\implementation_plan.md")
    if p2.exists():
        p2.write_text(PLAN_CONTENT.strip() + "\n", encoding="utf-8")
        print(f"Đã sửa {p2}")

if __name__ == "__main__":
    main()
