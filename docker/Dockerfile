FROM python:3.11-slim

WORKDIR /app

# 1. 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl apt-transport-https ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# 2. pip 최신 버전 + requirements
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 3. Google Cloud SDK 설치
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update && apt-get install -y google-cloud-sdk

# 4. 앱 소스 복사
COPY . .

# 5. 실행 
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
