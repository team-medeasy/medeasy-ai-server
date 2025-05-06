# middleware/logging.py
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("api")  # setup_logging() 에 "api" 로거도 미리 설정해 두세요.

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 요청 로그
        logger.info(f"✅ REQUEST → {request.method} {request.url.path}")

        # 엔드포인트 실행
        response: Response = await call_next(request)

        # 응답 로그
        logger.info(f"✅ RESPONSE ← {request.method} {request.url.path}  Status: {response.status_code}")

        return response
