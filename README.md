# Chatbot EVN

Hệ thống AI Chatbot phục vụ nghiệp vụ EVN với kiến trúc dự phòng đa mô hình
(Gemini → OpenRouter/auto → Claude → OpenAI), phản hồi streaming theo thời gian
thực và quản lý ngân sách chặt chẽ.

## Mục đích và đối tượng sử dụng

- **Mục đích**: Hệ thống AI Chatbot phục vụ nghiệp vụ EVN, hỗ trợ xử lý công
  việc và tác nghiệp chuyên môn.
- **Đối tượng sử dụng**: Cán bộ, nhân viên EVN.

## Cấu trúc thư mục

```text
Chatbot-EVN/
├── app/                  # Mã nguồn ứng dụng chính
│   ├── chat/             # Nghiệp vụ quản lý hội thoại và ngữ cảnh
│   ├── core/             # Quản lý nhật ký, hạn mức, bảo mật
│   ├── llm/              # Bộ định tuyến và tính toán chi phí LLM
│   ├── config.py         # Nạp cấu hình từ biến môi trường
│   └── main.py           # Điểm khởi chạy FastAPI
├── config/               # Cấu hình danh sách mô hình và chuỗi dự phòng
├── prompts/              # Các mẫu chỉ dẫn hệ thống (prompts)
├── web/                  # Giao diện web người dùng
├── tests/                # Bộ kiểm thử tự động
├── scripts/              # Các kịch bản tiện ích và kiểm tra nhà cung cấp
├── Dockerfile            # Cấu hình đóng gói container hai tầng
├── docker-compose.yml    # Khởi chạy dịch vụ db (PostgreSQL 17) và app
├── requirements.txt      # Danh sách thư viện Python ghim phiên bản
├── .env.example          # Biến môi trường mẫu
└── AGENTS.md             # Hướng dẫn và quy tắc dành cho AI Agent
```

## Khởi chạy nhanh

1. Sao chép tệp biến môi trường mẫu và điền các khoá API:

   ```bash
   cp .env.example .env
   ```

2. Khởi chạy với Docker Compose:

   ```bash
   docker compose up --build
   ```
