from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging

logger = logging.getLogger("MongoDB")

#  환경 변수에서 값 불러오기 (docker-compose.yml과 일치해야 함)
MONGO_USER = os.getenv("MONGO_INITDB_ROOT_USERNAME", "admin")
MONGO_PASS = os.getenv("MONGO_INITDB_ROOT_PASSWORD", "password")
MONGO_HOST = os.getenv("MONGO_HOST", "mongo")  # 컨테이너 서비스명 사용
MONGO_PORT = os.getenv("MONGO_PORT", "27017")
MONGO_DB = os.getenv("MONGO_INITDB_DATABASE", "medeasy")

#  MongoDB 인증 URL 구성 (authSource=admin 필요)
MONGO_URL = f"mongodb://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}?authSource=admin"

client = AsyncIOMotorClient(MONGO_URL)
db = client[MONGO_DB]

async def connect_mongo():
    """MongoDB 연결 확인"""
    try:
        await db.command("ping")
        logger.info("✅ Successfully connected to MongoDB.")
        return True # 연결 성공
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        return False # 연결 실패