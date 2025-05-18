from typing import TypedDict, List, Dict, Optional, Any
from starlette.websockets import WebSocket
from langchain_core.tools import Tool

# 상태 정의
class AgentState(TypedDict):
    messages: Optional[str]  # 대화 이력
    user_id: int  # 사용자 ID
    server_action: Optional[str] # 서버에서 도구 사용없이 바로 수행할 기능
    data: Any # 클라이언트에서 넘겨준 데이터
    jwt_token: Optional[str]
    current_message: str  # 현재 처리 중인 메시지
    available_tools: List[Tool]
    tool_calls: List[Dict]  # 호출할 도구 목록
    tool_results: List[Dict]  # 도구 실행 결과
    initial_response: Optional[str]
    final_response: Optional[str]  # 최종 응답
    client_action: Optional[str]  # 사진 촬영 요청 타입 (있는 경우)
    error: Optional[str]  # 오류 정보 (있는 경우)
    websocket: Optional[WebSocket]  # 웹소켓 객체 추가
    response_data: Any