# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from backend.api.routes import medicine
from backend.db.elastic import setup_elasticsearch

app = FastAPI(
    title="MedEasy Vision Pill API",
    description="의약품 이미지 분석 및 검색 API",
    version="1.1.0"
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
app.include_router(medicine.router, prefix="/api/v1")

logger = logging.getLogger("MedEasyAPI")

@app.get("/")
async def root():
    return {"message": "MedEasy Vision Pill API에 오신 것을 환영합니다!"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Application startup: Connecting to databases...")
    mongo_ok = await connect_mongo()
    if not mongo_ok:
        logger.error("⚠️ MongoDB 연결 실패")
    es_ok = await setup_elasticsearch()
    if not es_ok:
        logger.error("⚠️ Elasticsearch 설정 실패")
    logger.info("✅ System initialization complete.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Application shutdown")
