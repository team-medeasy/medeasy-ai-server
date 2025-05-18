import logging
from typing import List, Dict, Any

from mcp_client.agent.agent_types import AgentState
from mcp_client.chat_session_repo import chat_session_repo
from mcp_client.client import format_chat_history

logger = logging.getLogger(__name__)

async def retrieve_context(state: AgentState) -> AgentState:
    """채팅 이력을 가져와 컨텍스트에 추가"""
    user_id = state["user_id"]
    logger.info("채팅 이력 조회")
    recent_messages: List[Dict[str, Any]] = chat_session_repo.get_recent_messages(user_id, 7)
    state["messages"] = format_chat_history(recent_messages)
    logger.info("채팅 이력 조회 완료")
    return state

def has_server_action(state: AgentState) -> str:
    """서버에서 직접 처리할 요청이 있는지 확인"""
    return "server_action" if ("server_action" in state and state["server_action"]) else "detect_conversation_shift"