# ==========================================
# Tầng 1: Builder - Biên dịch và cài đặt thư viện
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==========================================
# Tầng 2: Runner - Tầng thực thi ứng dụng
# ==========================================
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH="/install/lib/python3.12/site-packages"

# Cài curl để phục vụ kiểm tra trạng thái sức khoẻ
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Sao chép các gói thư viện từ tầng builder
COPY --from=builder /install /install

# Tạo nhóm và người dùng không phải root tên ungdung với UID 10001
RUN groupadd -g 10001 ungdung && \
    useradd -u 10001 -g ungdung -s /bin/bash -m ungdung

# Sao chép mã nguồn ứng dụng và phân quyền cho người dùng ungdung
COPY --chown=ungdung:ungdung . /app

# Chuyển sang người dùng không phải root
USER ungdung

# Cấu hình kiểm tra sức khoẻ ứng dụng qua endpoint /health
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
