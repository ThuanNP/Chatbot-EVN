# Hướng dẫn dành cho AI Agent (AGENTS.md)

## Dự án

Một ứng dụng AI chatbot web, gọi mô hình qua bốn nhà cung cấp theo chuỗi dự phòng Gemini → OpenRouter/auto → Claude → OpenAI.

## Quy tắc bất biến

1. Mọi lời gọi mô hình đi qua ĐÚNG MỘT hàm trong app/llm/router.py. Cấm gọi SDK nhà cung cấp ở bất kỳ nơi nào khác trong mã.
2. Tên model và thứ tự chuỗi dự phòng chỉ được khai báo trong config/models.yaml. Cấm ghi tên model cứng trong mã Python.
3. Không ghi khoá API, mật khẩu hay chuỗi kết nối vào mã nguồn. Tất cả đọc từ biến môi trường, có .env.example làm mẫu.
4. Mọi lượt gọi mô hình phải ghi lại: tầng nào phục vụ, model nào, token vào, token ra, chi phí ước tính, độ trễ.
5. Mọi phản hồi tới người dùng phải phát theo dòng. Không có endpoint nào trả về nguyên khối rồi mới hiện.
6. Tên biến và tên hàm nghiệp vụ dùng tiếng Việt không dấu hoặc tiếng Anh nhất quán; chú thích viết tiếng Việt có dấu.
7. Tuân thủ nghiêm ngặt chuẩn định dạng Markdown (markdownlint): luôn có dòng trống bao quanh tiêu đề (MD022), danh sách (MD032), khối mã (MD031); và luôn chỉ định ngôn ngữ cho khối mã (MD040).

## Phạm vi làm việc

Agent chỉ được sửa app/, config/, prompts/, web/, tests/, scripts/, .agents/ và các tệp gốc docker-compose.yml, Dockerfile, .env.example, .gitignore, requirements.txt, README.md, AGENTS.md.

## Phải hỏi trước khi làm

- Thêm thư viện mới
- Đổi lược đồ cơ sở dữ liệu
- Thêm dịch vụ mới vào docker-compose
- Xoá tệp

## Không làm trong phiên bản này

- RAG và cơ sở dữ liệu vector
- Mô hình chạy local
- Đăng nhập một lần doanh nghiệp
- Kubernetes
- Tinh chỉnh mô hình

*Đây là quyết định phạm vi có chủ đích, không phải thiếu sót.*
