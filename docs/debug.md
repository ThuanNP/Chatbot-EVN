# Hướng Dẫn Gỡ Lỗi và Truy Vết Sự Cố

Tài liệu này hướng dẫn cách truy vết yêu cầu, trích xuất mã định danh `ma_yeu_cau`,
lọc nhật ký và chẩn đoán ba lỗi thường gặp nhất trong hệ thống Chatbot EVN.

## 1. Cách Lấy `ma_yeu_cau` Từ Phản Hồi

Khi hệ thống xử lý một lượt trao đổi, mỗi yêu cầu được gắn một mã truy vết duy nhất
gồm đúng 12 ký tự hex (ví dụ: `a3bbde8bd1fb`).

### 1.1. Lấy từ Header phản hồi HTTP

Mọi phản hồi (thành công hoặc thất bại) luôn trả về mã này trong tiêu đề `X-Ma-Yeu-Cau`:

```bash
curl.exe -i -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"tin_nhan":"xin chao"}' | grep.exe -i "X-Ma-Yeu-Cau"
```

Trên môi trường PowerShell (Windows):

```powershell
$resp = Invoke-WebRequest -Uri "http://localhost:8000/chat" `
  -Method POST `
  -Headers @{"Authorization"="Bearer <token>"} `
  -ContentType "application/json" `
  -Body '{"tin_nhan":"xin chao"}'
$resp.Headers["X-Ma-Yeu-Cau"]
```

### 1.2. Lấy từ Thân phản hồi JSON khi có lỗi

Khi xảy ra lỗi hệ thống (HTTP 500) hoặc lỗi HTTP (400, 404, 429, 503), thân phản hồi
chứa mã yêu cầu để người dùng đọc cho bộ phận hỗ trợ kỹ thuật:

```json
{
  "ma": 500,
  "ma_yeu_cau": "a3bbde8bd1fb"
}
```

## 2. Cách Lọc Nhật Ký Theo `ma_yeu_cau`

Nhật ký hệ thống được ghi theo định dạng JSON một dòng. Dùng lệnh lọc để xem toàn bộ
chuỗi hành trình của một yêu cầu.

### 2.1. Lọc với Docker Compose

```bash
docker compose logs app | grep "<ma_yeu_cau>"
```

### 2.2. Lọc trên PowerShell

```powershell
docker compose logs app | Select-String "<ma_yeu_cau>"
```

### 2.3. Sáu chặng chuẩn trong một lượt gọi thành công

Một lượt yêu cầu hoàn chỉnh sẽ lần lượt đi qua đủ 6 chặng chuẩn:

1. `http_vao`: Bắt đầu tiếp nhận request tại cổng HTTP.
2. `kiem_tra_han_muc`: Kiểm tra ba tầng hạn mức (IP, người dùng/giờ, chi phí ngày).
3. `dung_ngu_canh`: Cắt tỉa ngữ cảnh hội thoại (chỉ ghi độ dài và số lượng token).
4. `goi_mo_hinh`: Gọi nhà cung cấp LLM (ghi tầng, model, token, chi phí, độ trễ).
5. `luu_hoi_thoai`: Lưu tin nhắn người dùng và câu trả lời vào cơ sở dữ liệu.
6. `http_ra`: Hoàn tất xử lý và trả lời HTTP ra máy khách.

## 3. Ba Lỗi Thường Gặp Nhất và Cách Nhận Biết

### 3.1. Lỗi Vượt Hạn Mức (HTTP 429)

- **Nguyên nhân:** Người dùng vượt quá hạn mức theo IP (`HAN_MUC_IP_PHUT`) hoặc số
  lượt gọi mỗi giờ (`HAN_MUC_MOI_NGUOI_GIO`).
- **Phản hồi ngoài:** HTTP 429 với thông báo `vượt quá hạn mức` và header `Retry-After`.
- **Dấu vết nhật ký:** Dòng log chặng `kiem_tra_han_muc` có mức `WARNING`, ghi nhận
  `tang_han_muc` và `retry_after`:

```json
{
  "thoi_diem": "2026-09-18T10:00:00.000000+00:00",
  "muc": "WARNING",
  "ma_yeu_cau": "a3bbde8bd1fb",
  "nguoi_dung_id": "nv_evn_01",
  "chang": "kiem_tra_han_muc",
  "thong_diep": "[Hạn mức 429] tang=gio, retry_after=120s: Bạn đã sử dụng hết 60 lượt",
  "do_tre_ms": 1.25
}
```

### 3.2. Lỗi Vượt Ngân Sách Ngày (HTTP 503)

- **Nguyên nhân:** Tổng chi phí gọi mô hình trong ngày của toàn hệ thống chạm trần
  `NGAN_SACH_NGAY_USD` (hoặc hạn mức ngân sách ngày của người dùng).
- **Phản hồi ngoài:** HTTP 503 Service Unavailable.
- **Dấu vết nhật ký:** Dòng log chặng `kiem_tra_han_muc` có mức `ERROR` kèm thông điệp
  ngân sách:

```json
{
  "thoi_diem": "2026-09-18T10:00:00.000000+00:00",
  "muc": "ERROR",
  "ma_yeu_cau": "a3bbde8bd1fb",
  "nguoi_dung_id": "nv_evn_01",
  "chang": "kiem_tra_han_muc",
  "thong_diep": "[Ngân sách 503] Tổng chi phí hôm nay ($10.02) vượt ngân sách ngày ($10.00)",
  "do_tre_ms": 2.10
}
```

### 3.3. Lỗi Toàn Bộ Tầng Mô Hình Thất Bại (HTTP 500 / 503)

- **Nguyên nhân:** Tất cả 4 tầng trong chuỗi dự phòng (Gemini → OpenRouter → Claude
  → OpenAI) đều hỏng do sai khoá API, cạn quota hoặc sự cố mạng upstream.
- **Phản hồi ngoài:** JSON chỉ gồm `{"ma": 500, "ma_yeu_cau": "..."}`.
- **Dấu vết nhật ký:** Chặng `goi_mo_hinh` hoặc `he_thong` chứa danh sách chi tiết các
  tầng đã thử và lý do thất bại (`danh_sach_tang_da_hong`), kèm vết lỗi `vet_loi`:

```json
{
  "thoi_diem": "2026-09-18T10:00:00.000000+00:00",
  "muc": "ERROR",
  "ma_yeu_cau": "a3bbde8bd1fb",
  "nguoi_dung_id": "nv_evn_01",
  "chang": "he_thong",
  "thong_diep": "Lỗi hệ thống chưa phân loại: TatCaTangDeuHongError",
  "do_tre_ms": 0.0,
  "vet_loi": "Traceback (most recent call last): ... TatCaTangDeuHongError"
}
```
