import logging

from mcp_client.agent.agent_types import AgentState
from mcp_client.manager.tool_manager import tool_manager

logger = logging.getLogger(__name__)

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

def has_error(state: AgentState) -> str:
    """오류가 있는지 확인"""
    return "error" if ("error" in state and state["error"]) else "continue"