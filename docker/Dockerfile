# docker/Dockerfile
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl apt-transport-https ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 복사 후 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Google Cloud CLI 설치 (선택사항)
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | tee /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - && \
    apt-get update && apt-get install -y google-cloud-sdk

# 프로젝트 전체 소스 복사
COPY . .

# 개발용: --reload 사용 (프로덕션용이면 제거)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
