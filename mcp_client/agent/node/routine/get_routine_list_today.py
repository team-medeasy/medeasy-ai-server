import logging
import json
from datetime import date
from mcp_client.agent.agent_types import AgentState
from mcp_client.client import gpt_nano
from mcp_client.prompt import system_prompt
from mcp_client.service.routine_service import get_routine_list

logger = logging.getLogger(__name__)

async def get_routine_list_today(state: AgentState) -> AgentState:
    get_routine_list_today_prompt= """
        당신은 오늘 복용 일정을 설명해주는 에이전트입니다.
        
        사용자는 오늘 복용 일정을 요청하였고, 외부 api를 사용해서 금일 복용 정보와, 요약메시지 데이터를 받게 되었습니다.
        
        이 데이터를 활용하여  사용자에게 친절하고 정확한 복약 정보를 제공하세요.
        
        기본적으로 messages의 문자와 비슷한 형태로 제공하되 사용자가 복약 일정을 더 자세히 요청할 때 schedule_details에 있는 json데이터를 활용하여 응답하세요.
    """

    logger.info("execute get routine list today node")
    user_message = state.get("current_message", "")
    today = date.today()
    routine_data = await get_routine_list(today, today, state["jwt_token"])
    routine_data_str = json.dumps(routine_data, ensure_ascii=False, indent=2)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": user_message},
        {"role": "system", "content": routine_data_str},
    ]

    text_response = await gpt_nano.ainvoke(messages)
    # state 업데이트
    state["final_response"] = text_response.content.strip()
    state["direction"] = "save_conversation"
    return state



def get_routine_list_today_direction_router(state: AgentState) -> str:
    return "save_conversation"