# Quy Chuẩn An Toàn Kiểu Dữ Liệu và Thu Hẹp Kiểu (Type Safety & Type Narrowing)

Quy tắc bắt buộc khi viết mã nguồn và kiểm thử trong toàn bộ dự án nhằm ngăn chặn
triệt để lỗi phân tích kiểu tĩnh `Object of class NoneType has no attribute`:

## 1. Nguyên Tắc Cốt Lõi Về Xử Lý `Optional[T]`

Mọi hàm hoặc phương thức có kiểu trả về là `Optional[T]` (hoặc `Union[T, None]`,
`T | None` như các hàm truy vấn cơ sở dữ liệu `lay_hoi_thoai`, `phien.get()`,
`re.search()`, từ điển `.get()`, v.v.) thì đối tượng trả về có thể mang giá trị
`None`.

Tuyệt đối **CẤM** truy cập trực tiếp thuộc tính hoặc phương thức của đối tượng
(`obj.thuoc_tinh`, `obj.phuong_thuc()`) khi chưa thực hiện thu hẹp kiểu
(type narrowing).

## 2. Quy Định Cụ Thể Theo Từng Ngữ Cảnh

### Trong Mã Kiểm Thử (tests/)

Ngay sau khi nhận kết quả từ hàm trả về `Optional[T]`, bắt buộc phải có câu lệnh
kiểm tra khẳng định `is not None` trước khi truy cập bất kỳ thuộc tính nào:

```python
# ĐÚNG:
ht = lay_hoi_thoai(ht_id)
assert ht is not None
assert ht.tieu_de == "Tiêu đề mong đợi"

# SAI (CẤM):
ht = lay_hoi_thoai(ht_id)
assert ht.tieu_de == "Tiêu đề mong đợi"  # Bị lỗi Pyright: NoneType has no attribute tieu_de
```

### Trong Mã Nghiệp Vụ Ứng Dụng (app/)

Phải luôn kiểm tra điều kiện an toàn và xử lý sớm (early return, raise
HTTPException, hoặc fallback) trước khi sử dụng:

```python
# ĐÚNG:
hoi_thoai = lay_hoi_thoai(hoi_thoai_id)
if not hoi_thoai:
    raise HTTPException(status_code=404, detail="Hội thoại không tồn tại")
tieu_de = hoi_thoai.tieu_de

# SAI (CẤM):
hoi_thoai = lay_hoi_thoai(hoi_thoai_id)
tieu_de = hoi_thoai.tieu_de  # Gây crash ứng dụng nếu ID không hợp lệ
```

## 3. Tránh Ép Kiểu Thừa Thãi (No Redundant Type Casting)

- Không bọc `str(...)` đối với các biến đã có type hint là `str` (như kết quả
  chuỗi của LLM, tham số hàm dạng `str`).
- Kiểm tra chính xác kiểu dữ liệu trước khi xử lý chuỗi (`.strip()`, `.split()`).
