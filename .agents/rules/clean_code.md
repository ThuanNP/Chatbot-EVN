# Quy Chuẩn Clean Code (Mã Sạch)

Tài liệu này quy định các chuẩn mực về mã sạch áp dụng cho toàn bộ mã nguồn
dự án Chatbot EVN nhằm đảm bảo tính dễ đọc, dễ bảo trì, dễ kiểm thử và mở rộng.

## 1. Nguyên Tắc Cốt Lõi

1. **Đơn nhiệm (Single Responsibility Principle):** Mỗi hàm, phương thức hoặc
   lớp chỉ làm đúng một nhiệm vụ duy nhất và hoàn thành xuất sắc nhiệm vụ đó.
2. **Không lặp mã (Don't Repeat Yourself - DRY):** Tái sử dụng logic nghiệp vụ,
   hàm tiện ích và cấu hình; gom logic trùng lặp về một nơi duy nhất.
3. **Giữ đơn giản (Keep It Simple, Stupid - KISS):** Giải pháp đơn giản, rõ ràng
   luôn ưu tiên hơn giải pháp phức tạp, trừu tượng hóa quá mức.
4. **Không làm thừa (You Aren't Gonna Need It - YAGNI):** Chỉ cài đặt những gì
   nghiệp vụ hiện tại yêu cầu. Không thêm cấu trúc phòng xa chưa cần thiết.

## 2. Thiết Kế Hàm và Luồng Xử Lý

### 2.1. Ngắn gọn và Giới hạn Tham số

- Độ dài một hàm nên nằm trong khoảng 20 đến 50 dòng logic. Nếu hàm dài hơn,
  cần cân nhắc tách nhỏ thành các hàm phụ trợ có tên mang tính mô tả.
- Số lượng tham số đầu vào tối đa là 5. Nếu cần nhiều hơn, hãy đóng gói vào
  một mô hình dữ liệu (Pydantic `BaseModel` hoặc `@dataclass`).

### 2.2. Xử lý Sớm và Thoát Nhanh (Fail-Fast & Early Return)

- Kiểm tra điều kiện biên, dữ liệu không hợp lệ hoặc quyền truy cập ngay đầu hàm.
- Trả về kết quả sớm (`return`) hoặc ném ngoại lệ (`raise`) thay vì lồng nhiều
  tầng `if-else` phức tạp:

```python
# ĐÚNG: Thoát sớm, mã phẳng dễ đọc
def xu_ly_yeu_cau(yeu_cau: YeuCau) -> KetQua:
    if not yeu_cau.tin_nhan:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")
    if not yeu_cau.hoi_thoai_id:
        return tao_moi_va_xu_ly(yeu_cau)
    return tiep_tuc_hoi_thoai(yeu_cau)

# SAI: Lồng ghép tầng tầng lớp lớp (Arrow Anti-pattern)
def xu_ly_yeu_cau(yeu_cau: YeuCau) -> KetQua:
    if yeu_cau.tin_nhan:
        if yeu_cau.hoi_thoai_id:
            return tiep_tuc_hoi_thoai(yeu_cau)
        else:
            return tao_moi_va_xu_ly(yeu_cau)
    else:
        raise HTTPException(status_code=400, detail="Tin nhắn trống")
```

## 3. Phân Định Rõ Ràng Các Tầng Trách Nhiệm

Hệ thống tuân thủ kiến trúc phân tầng tách bạch:

1. **Tầng Giao Tiếp HTTP (`app/main.py`):**
   - Nhiệm vụ: Tiếp nhận request, gắn mã truy vết, chứng thực/phân quyền,
     chuyển đổi DTO và trả HTTP response (kể cả SSE stream).
   - Tuyệt đối không viết logic tính toán nghiệp vụ phức tạp tại controller.
2. **Tầng Nghiệp Vụ (`app/chat/`, `app/llm/`, `app/core/`):**
   - Nhiệm vụ: Điều phối logic kinh doanh, cắt tỉa ngữ cảnh, kiểm soát hạn mức,
     tính toán chi phí, điều phối chuỗi fallback mô hình.
   - Mọi tương tác gọi LLM đi qua duy nhất `app/llm/router.py`.
3. **Tầng Dữ Liệu (`app/core/database.py`, `app/chat/hoi_thoai.py`):**
   - Nhiệm vụ: Thao tác đọc/ghi CSDL SQLite qua SQLAlchemy. Không chứa logic HTTP.

## 4. Dọn Dẹp Mã Chết và Chú Thích Đúng Cách

- **Không giữ mã chết (Dead Code):** Tuyệt đối không để lại các đoạn mã bị comment
  không sử dụng, các biến tạo ra nhưng không dùng, hoặc import thừa thãi.
- **Mã tự giải thích (Self-Documenting Code):** Tên hàm, tên biến và cấu trúc mã
  phải tự nói lên mục đích của chúng.
- **Chú thích (Comments):**
  - Chú thích giải thích **TẠI SAO** (lý do ra quyết định, trường hợp ngoại lệ,
    ràng buộc nghiệp vụ EVN), không giải thích **LÀM GÌ** (những gì mã đã thể hiện).
  - Tuân thủ Quy tắc 6 trong `AGENTS.md`: Chú thích viết bằng tiếng Việt có dấu.
