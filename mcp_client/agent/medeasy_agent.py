from datetime import date

from fastapi import HTTPException
from langchain_core.tools import Tool
from langgraph.graph import StateGraph
from typing import TypedDict, List, Dict, Optional, Tuple, Any
import logging

from backend.auth.jwt_token_helper import get_user_id_from_token
from mcp_client.chat_session_repo import chat_session_repo
from mcp_client.client import _execute_tool_calls, _generate_final_response, _get_initial_response, _extract_tool_calls, \
    format_chat_history
from mcp_client.fallback_handler import generate_fallback_response
from mcp_client.prompt import system_prompt, final_response_system_prompt
from mcp_client.service.routine_service import get_routine_list
from mcp_client.util.retry_utils import with_retry
from mcp_client.manager.tool_manager import tool_manager

logger = logging.getLogger(__name__)

# 상태 정의
class AgentState(TypedDict):
    messages: Optional[str]  # 대화 이력
    user_id: int  # 사용자 ID
    server_action: Optional[str] # 서버에서 도구 사용없이 바로 수행할 기능
    data: Dict[str, Any] # 클라이언트에서 넘겨준 데이터
    jwt_token: Optional[str]
    current_message: str  # 현재 처리 중인 메시지
    available_tools: List[Tool]
    tool_calls: List[Dict]  # 호출할 도구 목록
    tool_results: List[Dict]  # 도구 실행 결과
    initial_response: Optional[str]
    final_response: Optional[str]  # 최종 응답
    client_action: Optional[str]  # 사진 촬영 요청 타입 (있는 경우)
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


async def check_client_actions(state: AgentState) -> AgentState:
    """특수 도구 호출(사진 촬영 등) 확인"""
    if not state.get("tool_calls"):
        return state

    for tool_call in state["tool_calls"]:
        name = tool_call.get('function', {}).get('name')
        if name == 'register_routine_by_prescription':
            state["client_action"] = "CAPTURE_PRESCRIPTION"
            state["final_response"] = "가지고 계신 처방전을 촬영해주세요."
            break
        elif name == 'register_routine_by_pills_photo':
            state["client_action"] = "CAPTURE_PILLS_PHOTO"
            state["final_response"] = "알약 사진을 촬영해주세요."
            break

    return state

async def check_server_actions(state: AgentState) -> AgentState:
    """
    서버에서 바로 다이렉트로 기능 수행할 점이 있는지 ai 도구 선택이 필요 없는 경우
    TODO routine 조회
    """
    server_action: str=state.get("server_action")
    jwt_token: str = state.get("jwt_token")

    try:
        if server_action == "GET_ROUTINE_LIST_TODAY":
            today = date.today()
            routine_result:str = await get_routine_list(today, today, jwt_token)
            state["final_response"] = routine_result

    except HTTPException as e:
        logger.error(f"서버 액션 처리 중 HTTP 오류: {e.detail}")
        state["error"] = f"서버 요청 실패: {e.detail}"
    except Exception as e:
        logger.exception(f"서버 액션 처리 중 예외 발생: {str(e)}")
        state["error"] = f"서버 액션 처리 오류: {str(e)}"

    return state



async def execute_tools(state: AgentState) -> AgentState:
    """도구 실행"""
    if "client_action" in state and state["client_action"]:
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
def has_server_action(state: AgentState) -> str:
    """서버에서 직접 처리할 요청이 있는지 확인"""
    return "server_action" if ("server_action" in state and state["server_action"]) else "load_tools"

def has_error(state: AgentState) -> str:
    """오류가 있는지 확인"""
    return "error" if ("error" in state and state["error"]) else "continue"

def has_capture_request(state: AgentState) -> str:
    """캡처 요청이 있는지 확인"""
    return (
        "capture"
        if state.get("client_action") in ["CAPTURE_PRESCRIPTION", "CAPTURE_PILLS_PHOTO"]
        else "continue"
    )


def has_tool_calls(state: AgentState) -> str:
    """도구 호출이 있는지 확인"""
    return "tools" if state.get("tool_calls") else "no_tools"


# 그래프 구성
def build_agent_graph():
    """에이전트 처리 그래프 구성"""
    graph = StateGraph(AgentState)

    # 노드 추가
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("check_server_actions", check_server_actions)
    graph.add_node("load_tools", load_tools)
    graph.add_node("generate_initial_response", generate_initial_response)
    graph.add_node("check_client_actions", check_client_actions)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("generate_final_response", generate_final_response)
    graph.add_node("save_conversation", save_conversation)

    # 엣지 연결
    graph.add_conditional_edges(
        "retrieve_context",
        has_server_action,
        {
            "server_action": "check_server_actions",
            "load_tools": "load_tools"
        }
    )
    graph.add_edge("check_server_actions", "save_conversation")

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
            "continue": "check_client_actions"
        }
    )
    graph.add_conditional_edges(
        "check_client_actions",
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
async def process_user_message(server_action:str, data: Dict[str, Any], user_message: str, jwt_token: str) -> Tuple[str, Optional[str]]:
    """
    사용자의 메시지에 대해 LangGraph를 사용하여 요청 처리

    Args:
        server_action (str): 서버에서 AI 추론을 거치지 않고 수행할 기능
        data(str): 클라이언트에서 제공한 데이터
        user_message (str): 사용자가 입력한 메시지 내용.
        jwt_token (str): authorization token

    Returns:
        message: str: LLM 응답 메시지
        capture_request: Optional[str]: 캡처 요청 타입 (있는 경우)
    """
    user_id = get_user_id_from_token(jwt_token)

    # 초기 상태 구성
    initial_state: AgentState = {
        "messages": None,
        "user_id": int(user_id),
        "server_action": server_action,
        "data": data,
        "jwt_token": jwt_token,
        "current_message": user_message,
        "available_tools": [],
        "tool_calls": [],
        "tool_results": [],
        "initial_response": None,
        "final_response": None,
        "client_action": None,
        "error": None,
    }

    try:
        agent_graph = build_agent_graph()

        try:
            final_state = await agent_graph.ainvoke(initial_state)
        except Exception as e:
            logger.error(f"그래프 실행 중 오류 발생: {str(e)}", exc_info=True)
            # 오류 발생 시 기본 응답 생성
            return f"죄송합니다. 요청을 처리하는 중 오류가 발생했습니다: {str(e)}", None

    except Exception as e:
        logger.error(f"그래프 구성 중 오류 발생: {str(e)}", exc_info=True)
        return "시스템 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", None

    return final_state["final_response"], final_state.get("client_action")