# main.py
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.config.middleware_config import LoggingMiddleware

import logging
logging.basicConfig(level=logging.INFO)
from contextlib import asynccontextmanager

from backend.api.routes import medicine
from mcp_client.mcp_router import router as mcp_router

from backend.db.elastic import check_elasticsearch_connection, es
from backend.config.logging_config import setup_logging
from backend.exceptionhandler.api_exception_handler import register_exception_handler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 초기화 작업
    logger.info("Application startup: Initializing Elasticsearch connection...")
    es_ok = await check_elasticsearch_connection()
    if not es_ok:
        logger.error("Failed to initialize Elasticsearch connection.")
    logger.info("Elasticsearch connection initialized successfully.")
    yield
    # 앱 종료 시 정리 작업
    logger.info("Application shutdown: Closing Elasticsearch connection...")
    await es.close()

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

register_exception_handler(app)
# 라우터 등록
app.include_router(medicine.router, prefix="/v2")
app.include_router(mcp_router, prefix="/v2")

setup_logging()
logger = logging.getLogger(__name__)

app.add_middleware(LoggingMiddleware)
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