import logging
from mcp_client.agent.agent_types import AgentState
from mcp_client.chat_session_repo import chat_session_repo

logger = logging.getLogger(__name__)

async def save_conversation(state: AgentState) -> AgentState:
    """대화 내용 저장"""
    user_id = state["user_id"]
    user_message = state["current_message"]
    final_response = state["final_response"]

    logger.info("대화 내용 저장")
    chat_session_repo.add_message(user_id=user_id, role="user", message=user_message)
    chat_session_repo.add_message(user_id=user_id, role="agent", message=final_response)
    logger.info("대화 내용 저장완료")

    return state