from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from mcp_client.client import process_user_message
from backend.auth.jwt_token_helper import get_user_id_from_token
import logging

logger = logging.getLogger(__name__)

# 요청 모델 정의
class ChatRequest(BaseModel):
    message: str
    jwt_token: str

# 응답 모델 정의
class ChatResponse(BaseModel):
    response: str

# 라우터 생성
router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("/message", response_model=ChatResponse)
async def process_message(request: ChatRequest):
    try:
        user_id=get_user_id_from_token(request.jwt_token)
        logger.info(f"Received message from user {user_id}")
        # MCP 에이전트를 통한 메시지 처리
        # 토큰 정보를 포함한 메시지 구성
        enhanced_message = f"""
            {request.message}

            # API 호출 정보
            mcp_tools를 사용할 때에는 사용자별 jwt토큰 매개변수로 사용하세요.: {request.jwt_token}
            
            응답은 한글로 주세요.
            
            당신은 복약 스케줄 종합 관리 음성 채팅 봇입니다. 
            사용자가 듣기 편할 수 있도록 특수문자를 넣지 말고 간결하게 응답을 주세요.
            """
        response = await process_user_message(enhanced_message)

        return ChatResponse(response=response)

    except Exception as e:
        # 오류 처리
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")