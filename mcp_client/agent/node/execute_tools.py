import logging

from mcp_client.agent.agent_types import AgentState
from mcp_client.client import _execute_tool_calls
from mcp_client.util.retry_utils import with_retry

logger = logging.getLogger(__name__)

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
        logger.info(f"before execute tools node tool results: {state['tool_results']}")
        tool_results = await with_retry(
            lambda: _execute_tool_calls(
                state["tool_calls"],
                state["available_tools"]
            )
        )
        state["tool_results"] = tool_results
        logger.info(f"after execute tools node tool results: {state['tool_results']}")
        logger.info("도구 실행 완료")
    except Exception as e:
        logger.exception(f"도구 실행 중 오류: {e}")
        state["error"] = f"도구 실행 실패: {str(e)}"

    return state

def has_tool_calls(state: AgentState) -> str:
    """도구 호출이 있는지 확인"""
    return "tools" if state.get("tool_calls") else "no_tools"