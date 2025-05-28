import logging
from mcp_client.agent.agent_types import AgentState

logger = logging.getLogger(__name__)

async def delete_routine(state: AgentState)->AgentState:
