# main.py
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

import logging
from contextlib import asynccontextmanager

from backend.api.routes import medicine
from backend.db.elastic import setup_elasticsearch, es

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 초기화 작업
    logger.info("Application startup: Initializing Elasticsearch connection...")
    es_ok = await setup_elasticsearch()
    if not es_ok:
        logger.error("Failed to initialize Elasticsearch connection.")
    logger.info("Elasticsearch connection initialized successfully.")
    yield
    # 앱 종료 시 정리 작업
    logger.info("Application shutdown: Closing Elasticsearch connection...")

app = FastAPI(
    title="MedEasy Vision Pill API",
    description="의약품 이미지 분석 및 검색 API",
    version="1.1.0",
    lifespan=lifespan
)

# CORS 설정 (필요에 따라 변경)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# 라우터 등록
app.include_router(medicine.router, prefix="/v2")

logger = logging.getLogger("MedEasyAPI")

@app.get("/")
async def root():
    return {"message": "Welcome to MedEasy Vision API!"}

@app.get("/health")
async def health():
    try:
        if await es.ping():
            return {"status" : "healthy", "elasticsearch": "ok"}
        else:
            raise HTTPException(status_code=503, detail="Elasticsearch connection failed.")
    except Exception as e:
        return {"status": "unhealthy", "elasticsearch": "error", "error": str(e)}