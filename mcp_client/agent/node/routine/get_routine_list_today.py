import json
from datetime import date

from mcp_client.agent.agent_types import AgentState
from mcp_client.client import gpt_nano
from mcp_client.service.routine_service import get_routine_list


async def get_routine_list_today(state: AgentState) -> AgentState:
    today = date.today()
    routine_list_data = await get_routine_list(today, today, state["jwt_token"])

    # GPT nano로 데이터 가공을 위한 프롬프트 준비
    prompt = f"""
다음은 사용자의 오늘 복약 일정 데이터입니다. 이 데이터를 분석하여 사용자에게 친근하고 유용한 메시지를 생성해주세요.

복약 데이터:
{json.dumps(routine_list_data, ensure_ascii=False, indent=2)}

다음 사항들을 고려하여 메시지를 작성해주세요:
1. 오늘의 전체 복약 일정 요약
2. 놓친 약이 있다면 친절한 리마인드
3. 곧 복용해야 할 약이 있다면 미리 안내
4. 복용 완료된 약이 있다면 칭찬과 격려
5. 전체적으로 따뜻하고 격려하는 톤으로 작성

하나의 자연스러운 문자열 메시지로 응답해주세요.
"""

    # GPT nano 호출
    response = await gpt_nano.ainvoke([
        {"role": "system", "content": "당신은 복약 관리를 도와주는 친절한 AI 어시스턴트입니다. 사용자의 건강을 위해 따뜻하고 격려하는 메시지를 제공합니다."},
        {"role": "user", "content": prompt}
    ])

    # GPT 응답을 문자열로 처리
    processed_message = response.content.strip()

    # state 업데이트
    state["final_response"] = processed_message
    state["direction"] = "save_conversation"
    return state



def get_routine_list_today_direction_router(state: AgentState) -> str:
    return "save_conversation"