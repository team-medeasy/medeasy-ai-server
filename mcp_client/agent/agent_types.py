from typing import TypedDict, List, Dict, Optional, Any
from starlette.websockets import WebSocket
from langchain_core.tools import Tool
import logging

logger = logging.getLogger(__name__)

# 상태 정의
class AgentState(TypedDict):
    user_id: int  # 사용자 ID
    jwt_token: Optional[str]
    websocket: Optional[WebSocket]  # 웹소켓 객체 추가

    # 메시지마다 덮여쓰일 데이터
    messages: Optional[str]  # 대화 이력
    data: Any # 클라이언트에서 넘겨준 데이터
    current_message: str  # 현재 처리 중인 메시지

    # 메시지마다 초기화해도 괜찮은 상태
    available_tools: List[Tool]
    tool_calls: List[Dict]  # 호출할 도구 목록
    tool_results: List[Dict]  # 도구 실행 결과
    server_action: Optional[str] # 서버에서 도구 사용없이 바로 수행할 기능
    initial_response: Optional[str]
    final_response: Optional[str]  # 최종 응답
    error: Optional[str]  # 오류 정보 (있는 경우)
    direction: Optional[str]


    response_data: Any
    client_action: Optional[str]  # 사진 촬영 요청 타입 (있는 경우)
    temp_data: Any

def init_state(state: AgentState):
    client_action = state.get("client_action")
    response_data = state.get("response_data")

    state["current_message"]=""
    state["data"] = None
    state["messages"] = None
    state["available_tools"] = []
    state["tool_calls"] = []
    state["tool_results"] = []
    state["server_action"] = None
    state["initial_response"] = None
    state["final_response"] = None
    state["error"] = None
    state["direction"] = None

    # 보존해야 할 값 복원
    state["client_action"] = client_action
    state["response_data"] = response_data

    logger.info(f"새로운 대화 상태 초기화, client_action: {client_action}, response_data: {'존재함' if response_data else 'None'}")

    return state