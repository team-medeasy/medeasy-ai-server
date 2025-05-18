import logging

from mcp_client.agent.agent_types import AgentState
from mcp_client.client import _generate_final_response
from mcp_client.fallback_handler import generate_fallback_response
from mcp_client.prompt import system_prompt, final_response_system_prompt
from mcp_client.util.retry_utils import with_retry

logger = logging.getLogger(__name__)

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