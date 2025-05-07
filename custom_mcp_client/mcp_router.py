from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from custom_mcp_client.client import process_user_message

# 요청 모델 정의
class ChatRequest(BaseModel):
    message: str
    jwt_token: str
    session_id: Optional[str] = None

# 응답 모델 정의
class ChatResponse(BaseModel):
    response: str
    session_id: str

# 라우터 생성
router = APIRouter(prefix="/chat", tags=["chat"])

# 세션 저장소 (실제 구현에서는 Redis 등 외부 저장소 사용 권장)
sessions = {}


@router.post("/custom-client/message", response_model=ChatResponse)
async def process_message(request: ChatRequest):

    # 세션 ID 처리
    session_id = request.session_id or f"session_{len(sessions) + 1}"
    if session_id not in sessions:
        sessions[session_id] = {"history": []}

    # 사용자 메시지 로깅
    sessions[session_id]["history"].append({"role": "user", "content": request.message})

    # MCP 에이전트를 통한 메시지 처리
    # 토큰 정보를 포함한 메시지 구성
    enhanced_message = f"""
        {request.message}

        # API 호출 정보
        mcp_tools를 사용할 때에는 사용자별 jwt토큰 매개변수로 사용하세요.: {request.jwt_token}
        """
    response = await process_user_message(jwt_token=request.jwt_token, user_message=enhanced_message)

    # 응답 로깅
    sessions[session_id]["history"].append({"role": "assistant", "content": response})

    return ChatResponse(response=response, session_id=session_id)
