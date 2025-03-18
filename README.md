# MedEasy Vision - Pill Identification API

## 📌 프로젝트 개요

MedEasy Vision은 의약품 이미지에서 색상, 모양, 식별 코드 등을 분석하여 정보를 제공하는 AI 기반 의약품 검색 시스템입니다. Google Gemini AI와 Elasticsearch를 활용하여 정확한 검색 기능을 제공합니다.

## 🚀 주요 기능

- **이미지 분석을 통한 의약품 검색**: Gemini AI를 활용하여 이미지에서 의약품 정보를 추출
- **MongoDB & Elasticsearch 기반 검색**: 정확한 색상, 모양, 식별 코드 매칭 및 벡터 검색 지원
- **다중 의약품 탐지 지원**: 한 장의 이미지에서 여러 개의 의약품을 인식하고 개별적으로 분석
- **API 제공**: FastAPI 기반 REST API 구축

## 🏗️ 기술 스택

- **Backend**: FastAPI, Python
- **Database**: MongoDB, Elasticsearch
- **AI 모델**: Google Gemini AI
- **Containerization**: Docker, Docker Compose
- **CI/CD**: GitHub Actions (예정)
- **Deployment**: AWS (추후 배포 예정)

## 📂 프로젝트 구조

```
medeasy-vision-pill_api/
│── backend/              # FastAPI 백엔드 서버 코드
│   ├── api/              # API 엔드포인트 정의
│   │   ├── models/       # 데이터베이스 모델
│   │   │   ├── pill.py
│   │   ├── routes/       # API 엔드포인트 라우트
│   │   │   ├── pill.py
│   │   │   ├── search.py
│   │   │   ├── upload.py
│   ├── core/             # 핵심 설정 및 로직
│   ├── db/               # 데이터베이스 연결 및 CRUD
│   │   ├── crud.py
│   │   ├── elastic.py
│   │   ├── mongodb.py
│   ├── search/           # 검색 관련 로직
│   │   ├── logic.py
│   │   ├── transform.py
│   ├── services/         # AI 서비스
│   │   ├── gemini_service.py
│   ├── utils/            # 유틸리티 및 로깅
│   │   ├── helpers.py
│   │   ├── logging.py
│   ├── main.py           # FastAPI 진입점
│
│── data/                 # 데이터 관련 파일 (의약품 정보 JSON 등)
│   ├── processed_data.json
│── debugging/            # 디버깅 관련 파일
│   ├── env_deb.py
│── docker/               # Docker 관련 설정
│   ├── docker-compose.yml
│   ├── Dockerfile
│── .gitignore            # Git 무시 파일 목록
│── README.md             # 프로젝트 문서
│── requirements.txt      # Python 패키지 목록
```

## 📊 현재 진행 상황

### ✅ 완료된 작업

- 의약품 데이터 수집 및 MongoDB 저장
- Google Gemini AI API 연동 및 이미지 분석 테스트
- Elasticsearch 기반 의약품 검색 기능 구현 (벡터 검색 포함)
- FastAPI 서버 구축 및 기본 API 개발
- Docker 환경 구성 및 컨테이너 실행 테스트

### 🔄 진행 중인 작업

- 다중 의약품 인식 기능 개선
- 식별 코드 유사도 매칭 로직 보완
- 검색 최적화 및 성능 개선
- GitHub Actions를 활용한 CI/CD 환경 구축

## 🔧 설치 및 실행 방법

### 1️⃣ 환경 설정

```sh
# 프로젝트 클론
git clone https://github.com/your-repo/medeasy-vision-pill_api.git
cd medeasy-vision-pill_api

# 가상환경 생성 (선택 사항)
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate  # Windows

# 필수 패키지 설치
pip install -r requirements.txt
```

### 2️⃣ Docker 컨테이너 실행

```sh
docker-compose up -d  # 백그라운드 실행
```

### 3️⃣ FastAPI 서버 실행

```sh
uvicorn backend.main:app --reload
```

## 📬 API 엔드포인트

### 🏥 Pill 관리

- **의약품 정보 조회**

  ```http
  GET /api/v1/pill/{pill_id}
  ```

  - 특정 의약품의 정보를 가져옴

- **의약품 추가**

  ```http
  POST /api/v1/pill/add/
  ```

  - 새로운 의약품 정보를 추가

- **의약품 정보 업데이트**

  ```http
  PUT /api/v1/pill/update/{pill_id}
  ```

  - 기존 의약품 정보 수정

- **의약품 삭제**
  ```http
  DELETE /api/v1/pill/delete/{pill_id}
  ```
  - 특정 의약품 삭제

### 📤 데이터 업로드

- **JSON 데이터 업로드**
  ```http
  POST /api/v1/upload/json
  ```
  - JSON 파일 업로드 및 데이터 처리

### 🔍 검색 API

- **텍스트 기반 검색**

  ```http
  GET /api/v1/search/text
  ```

  - 키워드 검색을 통한 의약품 검색

- **이미지 기반 검색**
  ```http
  POST /api/v1/search/image
  ```
  - 이미지 업로드 후 AI 분석을 통한 검색

### ⚙️ 기본 엔드포인트

- **Root**

  ```http
  GET /
  ```

- **Health Check**
  ```http
  GET /health
  ```
  - 서버 상태 확인

## 🛠️ 개발 예정 기능

- 여러 환경에 대한 대응 확인 및 검색 로직 수정
- 배포 환경 구축 (AWS 기반 예정)

## 🤝 기여 방법

1. 이 프로젝트를 Fork 합니다.
2. 새로운 브랜치를 생성합니다: `git checkout -b feature-branch`
3. 변경 사항을 커밋합니다: `git commit -m "추가한 기능 설명"`
4. 원격 저장소에 푸시합니다: `git push origin feature-branch`
5. Pull Request를 생성합니다.
