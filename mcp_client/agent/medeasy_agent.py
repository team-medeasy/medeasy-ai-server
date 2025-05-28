from langgraph.graph import StateGraph
from typing import List, Dict, Optional, Tuple, Any
import logging

from starlette.websockets import WebSocket

from mcp_client.agent.agent_types import AgentState
from mcp_client.agent.node import *
from mcp_client.agent.node import detect_conversation_shift, direction_router
from mcp_client.agent.node.check_client_actions import check_client_actions_direction_router
from mcp_client.agent.node.check_server_actions import check_server_actions_direction_router
from mcp_client.agent.node.medicine.find_medicine_details import find_medicine_details
from mcp_client.agent.node.medicine.find_routine_register_medicine import find_routine_register_medicine, \
    find_routine_register_medicine_direction_router
from mcp_client.agent.node.routine.delete_routine import delete_routine, delete_routine_direction_router
from mcp_client.agent.node.routine.delete_routine_select import delete_routine_select, \
    delete_routine_select_direction_router
from mcp_client.agent.node.routine.get_routine_list_today import get_routine_list_today, \
    get_routine_list_today_direction_router
from mcp_client.agent.node.routine.register_routine import register_routine, register_routine_direction_router
from mcp_client.agent.node.routine.register_routine_list import register_routine_list
from mcp_client.agent.node.schedule.match_user_schedule import match_user_schedule, match_user_schedule_direction_router

logger = logging.getLogger(__name__)

# 그래프 구성
def build_agent_graph():
    """에이전트 처리 그래프 구성"""
    graph = StateGraph(AgentState)

    # 노드 추가
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("detect_conversation_shift", detect_conversation_shift)

    graph.add_node("find_medicine_details", find_medicine_details)
    graph.add_node("check_server_actions", check_server_actions)

    graph.add_node("register_routine_list", register_routine_list)
    graph.add_node("register_routine", register_routine)
    graph.add_node("find_routine_register_medicine", find_routine_register_medicine)
    graph.add_node("get_routine_list_today", get_routine_list_today)

    graph.add_node("match_user_schedule", match_user_schedule)

    graph.add_node("delete_routine", delete_routine)
    graph.add_node("delete_routine_select", delete_routine_select)

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
            "detect_conversation_shift": "detect_conversation_shift"
        }
    )

    graph.add_conditional_edges(
        "detect_conversation_shift",
        direction_router,
        {
            "check_server_actions": "check_server_actions",
            "load_tools": "load_tools",
            "save_conversation": "save_conversation",
            "find_medicine_details": "find_medicine_details",
            "register_routine": "register_routine",
            "find_routine_register_medicine": "find_routine_register_medicine",
            "delete_routine": "delete_routine",
            "delete_routine_select": "delete_routine_select",
        }
    )

    graph.add_edge("find_medicine_details", "save_conversation")

    graph.add_conditional_edges(
        "check_server_actions",
        check_server_actions_direction_router,
        {
            "register_routine_list": "register_routine_list",
            "save_conversation": "save_conversation",
            "register_routine": "register_routine",
            "get_routine_list_today": "get_routine_list_today",
        }
    )

    graph.add_conditional_edges(
        "get_routine_list_today",
        get_routine_list_today_direction_router,
        {
            "save_conversation": "save_conversation",
        }
    )

    graph.add_conditional_edges(
        "register_routine",
        register_routine_direction_router,
        {
            "find_routine_register_medicine": "find_routine_register_medicine",
            "save_conversation": "save_conversation",
            "load_tools": "load_tools",
            "match_user_schedule": "match_user_schedule",
        }
    )

    graph.add_conditional_edges(
        "find_routine_register_medicine",
        find_routine_register_medicine_direction_router,
        {
            "register_routine" : "register_routine",
            "save_conversation": "save_conversation",
        }
    )

    graph.add_conditional_edges(
        "match_user_schedule",
        match_user_schedule_direction_router,
        {
            "register_routine" : "register_routine",
            "save_conversation": "save_conversation",
        }
    )

    graph.add_conditional_edges(
        "delete_routine",
        delete_routine_direction_router,
        {
            "save_conversation": "save_conversation",
        }
    )

    graph.add_conditional_edges(
        "delete_routine_select",
        delete_routine_select_direction_router,
        {
            "save_conversation": "save_conversation",
        }
    )

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
        check_client_actions_direction_router,
        {
            "capture": "save_conversation",
            "register_routine": "register_routine",
            "execute_tools": "execute_tools",
            "delete_routine": "delete_routine",
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
async def process_user_message(
        state: AgentState,
) -> Tuple[str, Optional[str], Optional[str], Optional[Any]]:
    """
    사용자의 메시지에 대해 LangGraph를 사용하여 요청 처리

    Args:
        server_action (str): 서버에서 AI 추론을 거치지 않고 수행할 기능
        data(str): 클라이언트에서 제공한 데이터
        user_message (str): 사용자가 입력한 메시지 내용.
        jwt_token (str): authorization token
        websocket (WebSocket): 클라이언트에 메시지를 보낼 웹소켓 세션

    Returns:
        message: str: LLM 응답 메시지
        capture_request: Optional[str]: 캡처 요청 타입 (있는 경우)
    """

    try:
        agent_graph = build_agent_graph()

        try:
            final_state = await agent_graph.ainvoke(state)
        except Exception as e:
            logger.error(f"그래프 실행 중 오류 발생: {str(e)}", exc_info=True)
            # 오류 발생 시 기본 응답 생성
            return f"죄송합니다. 요청을 처리하는 중 오류가 발생했습니다: {str(e)}", None, None, None

    except Exception as e:
        logger.error(f"그래프 구성 중 오류 발생: {str(e)}", exc_info=True)
        return "시스템 오류가 발생했습니다. 잠시 후 다시 시도해주세요.", None, None, None

    logger.info(f"medeasy agent final_response: {state['final_response']}")
    return final_state["final_response"], final_state.get("client_action"), final_state.get("response_data"), final_state.get("temp_data")