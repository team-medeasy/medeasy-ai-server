from langchain_core.tools import Tool
from langgraph.graph import StateGraph
from typing import TypedDict, List, Dict, Optional, Tuple, Any
import logging

from mcp_client.chat_session_repo import chat_session_repo
from mcp_client.client import _execute_tool_calls, _generate_final_response, _get_initial_response, _extract_tool_calls, \
    format_chat_history
from mcp_client.fallback_handler import generate_fallback_response
from mcp_client.prompt import system_prompt, final_response_system_prompt
from mcp_client.retry_utils import with_retry
from mcp_client.tool_manager import tool_manager

logger = logging.getLogger(__name__)

# 상태 정의
class AgentState(TypedDict):
    messages: str  # 대화 이력
    user_id: int  # 사용자 ID
    current_message: str  # 현재 처리 중인 메시지
    available_tools: List[Tool]
    tool_calls: List[Dict]  # 호출할 도구 목록
    tool_results: List[Dict]  # 도구 실행 결과
    initial_response: Optional[str]
    final_response: Optional[str]  # 최종 응답
    capture_request: Optional[str]  # 사진 촬영 요청 타입 (있는 경우)
    error: Optional[str]  # 오류 정보 (있는 경우)


# 노드 함수들
async def retrieve_context(state: AgentState) -> AgentState:
    """채팅 이력을 가져와 컨텍스트에 추가"""
    user_id = state["user_id"]
    logger.info("채팅 이력 조회")
    recent_messages: List[Dict[str, Any]] = chat_session_repo.get_recent_messages(user_id, 7)
    state["messages"] = format_chat_history(recent_messages)
    logger.info("채팅 이력 조회 완료")
    return state


async def load_tools(state: AgentState) -> AgentState:
    """도구 관리자에서 도구 로드"""
    try:
        logger.info("도구 로딩")
        tools = await tool_manager.get_tools()
        state["available_tools"] = tools
        logger.info("도구 로딩 완료")
    except Exception as e:
        logger.warning(f"도구 로딩 에러: {e}")
        state["error"] = f"도구 로딩 실패: {str(e)}"
    return state


async def generate_initial_response(state: AgentState) -> AgentState:
    """초기 응답 생성 및 도구 호출 추출"""
    if "error" in state and state["error"]:
        return state

    try:
        logger.info("메시지와 어울리는 도구 호출")
        initial_response = await with_retry(
            lambda: _get_initial_response(
                state["current_message"],
                state["available_tools"],
                state["messages"]
            )
        )
        tool_calls = _extract_tool_calls(initial_response)
        state["tool_calls"] = tool_calls
        state["initial_response"] = initial_response.content
        logger.info(f"initial response: {initial_response.content}")
        logger.info("메시지와 어울리는 도구 호출 완료")
    except Exception as e:
        logger.exception(f"초기 응답 생성 중 오류: {e}")
        state["error"] = f"초기 응답 생성 실패: {str(e)}"
    return state


async def check_capture_requests(state: AgentState) -> AgentState:
    """특수 도구 호출(사진 촬영 등) 확인"""
    if not state.get("tool_calls"):
        return state

    for tool_call in state["tool_calls"]:
        name = tool_call.get('function', {}).get('name')
        if name == 'register_routine_by_prescription':
            state["capture_request"] = "CAPTURE_PRESCRIPTION"
            state["final_response"] = "처방전 촬영해주세요."
            break
        elif name == 'register_routine_by_pills_photo':
            state["capture_request"] = "CAPTURE_PILLS_PHOTO"
            state["final_response"] = "알약 사진을 촬영해주세요."
            break

    return state


async def execute_tools(state: AgentState) -> AgentState:
    """도구 실행"""
    if "capture_request" in state and state["capture_request"]:
        # 특수 도구 호출이 있으면 일반 도구 실행 건너뜀
        return state

    if not state.get("tool_calls"):
        # 도구 호출이 없는 경우 초기 응답을 최종 응답으로 사용
        state["final_response"] = state.get("initial_response", "")
        return state

    try:
        logger.info("도구 실행")
        tool_results = await with_retry(
            lambda: _execute_tool_calls(
                state["tool_calls"],
                state["available_tools"]
            )
        )
        state["tool_results"] = tool_results
        logger.info("도구 실행 완료")
    except Exception as e:
        logger.exception(f"도구 실행 중 오류: {e}")
        state["error"] = f"도구 실행 실패: {str(e)}"

    return state


async def generate_final_response(state: AgentState) -> AgentState:
    """최종 응답 생성"""
    if "final_response" in state and state["final_response"]:
        # 이미 최종 응답이 있는 경우 (캡처 요청 등) 건너뜀
        return state

    if "error" in state and state["error"]:
        # 오류가 있는 경우 대체 응답 생성
        fallback = await generate_fallback_response(
            system_prompt,
            state["current_message"],
            state["error"]
        )
        state["final_response"] = fallback
        return state

    try:
        logger.info("최종 응답 생성")
        final_response = await with_retry(
            lambda: _generate_final_response(
                final_response_system_prompt,
                state["current_message"],
                state.get("tool_calls", []),
                state.get("tool_results", [])
            )
        )
        state["final_response"] = final_response
        logger.info("최종 응답 생성 완료")
    except Exception as e:
        logger.exception(f"최종 응답 생성 중 오류: {e}")
        fallback = await generate_fallback_response(
            system_prompt,
            state["current_message"],
            str(e)
        )
        state["final_response"] = fallback

    return state


async def save_conversation(state: AgentState) -> AgentState:
    """대화 내용 저장"""
    user_id = state["user_id"]
    user_message = state["current_message"]
    final_response = state["final_response"]

    logger.info("대화 내용 저장")
    chat_session_repo.add_message(user_id=user_id, role="user", message=user_message)
    chat_session_repo.add_message(user_id=user_id, role="system", message=final_response)
    logger.info("대화 내용 저장완료")

    return state


# 조건 함수들
def has_error(state: AgentState) -> str:
    """오류가 있는지 확인"""
    return "error" if ("error" in state and state["error"]) else "continue"


def has_capture_request(state: AgentState) -> str:
    """캡처 요청이 있는지 확인"""
    return "capture" if ("capture_request" in state and state["capture_request"]) else "continue"


def has_tool_calls(state: AgentState) -> str:
    """도구 호출이 있는지 확인"""
    return "tools" if state.get("tool_calls") else "no_tools"


# 그래프 구성
def build_agent_graph():
    """에이전트 처리 그래프 구성"""
    graph = StateGraph(AgentState)

    # 노드 추가
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("load_tools", load_tools)
    graph.add_node("generate_initial_response", generate_initial_response)
    graph.add_node("check_capture_requests", check_capture_requests)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("generate_final_response", generate_final_response)
    graph.add_node("save_conversation", save_conversation)

    # 엣지 연결
    graph.add_edge("retrieve_context", "load_tools")
    graph.add_conditional_edges(
        "load_tools",
        has_error,
        {
            "error": "generate_final_response",
            "continue": "generate_initial_response"
        }
    )
    graph.add_conditional_edges(
        "generate_initial_response",
        has_error,
        {
            "error": "generate_final_response",
            "continue": "check_capture_requests"
        }
    )
    graph.add_conditional_edges(
        "check_capture_requests",
        has_capture_request,
        {
            "capture": "save_conversation",
            "continue": "execute_tools"
        }
    )
    graph.add_conditional_edges(
        "execute_tools",
        has_tool_calls,
        {
            "tools": "generate_final_response",
            "no_tools": "generate_final_response"
        }
    )
    graph.add_edge("generate_final_response", "save_conversation")

    # 시작점과 종료점 설정
    graph.set_entry_point("retrieve_context")
    graph.set_finish_point("save_conversation")

    return graph.compile()


# 메인 함수
async def process_user_message(user_message: str, user_id: int) -> Tuple[str, Optional[str]]:
    """
    사용자의 메시지에 대해 LangGraph를 사용하여 요청 처리

    Args:
        user_message (str): 사용자가 입력한 메시지 내용.
        user_id (int): 사용자 식별자

    Returns:
        message: str: LLM 응답 메시지
        capture_request: Optional[str]: 캡처 요청 타입 (있는 경우)
    """
    # 초기 상태 구성
    initial_state: AgentState = {
        "messages": str,
        "user_id": user_id,
        "current_message": user_message,
        "available_tools": [],
        "tool_calls": [],
        "tool_results": [],
        "initial_response": None,
        "final_response": None,
        "capture_request": None,
        "error": None
    }

    # 그래프 실행
    agent_graph = build_agent_graph()
    final_state = await agent_graph.ainvoke(initial_state)

    return final_state["final_response"], final_state.get("capture_request")