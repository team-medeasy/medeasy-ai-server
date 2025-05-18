import logging

from mcp_client.agent.agent_types import AgentState
from mcp_client.client import _get_initial_response, _extract_tool_calls
from mcp_client.util.retry_utils import with_retry

logger = logging.getLogger(__name__)

async def generate_initial_response(state: AgentState) -> AgentState:
    """초기 응답 생성 및 도구 호출 추출"""
    if "error" in state and state["error"]:
        return state

    try:
        logger.info("메시지와 어울리는 도구 호출")
        initial_response = await with_retry(
            lambda: _get_initial_response(
                jwt_token=state["jwt_token"],
                user_message=state["current_message"],
                tools=state["available_tools"],
                chat_history=state["messages"]
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
