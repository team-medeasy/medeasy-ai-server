import logging
from mcp_client.agent.agent_types import AgentState
from mcp_client.service.routine_service import get_medicines_current

logger = logging.getLogger(__name__)

async def delete_routine(state: AgentState)->AgentState:
    """
    1. 현재 등록된 복약 일정들입니다.
    5/20~5/28 어떤약
    5/20~5/28 어떤약
    5/20~5/28 어떤약

    어떤 일정을 삭제하고 싶으신가요?
    """
    # 1. 사용자 현재 복용 중인 루틴 그룹 조회
    current_routine_groups = await get_medicines_current(state["jwt_token"])

    if not current_routine_groups:
        state["final_response"] = "현재 등록된 복용 일정이 없습니다."
        state["direction"] = "save_conversation"
        return state

    # 2. 일정 목록 메시지 생성
    routine_list_message = "현재 등록된 복약 일정들입니다.\n\n"

    for idx, routine in enumerate(current_routine_groups, 1):
        start_date = routine.get("routine_start_date", "")
        end_date = routine.get("routine_end_date", "")
        medicine_name = routine.get("nickname", routine.get("medicine_name", "알 수 없는 약품"))

        # 날짜 포맷팅 (YYYY-MM-DD -> M/D)
        formatted_start = format_date_short(start_date)
        formatted_end = format_date_short(end_date)

        routine_list_message += f"{idx}. {formatted_start}~{formatted_end} {medicine_name}\n"

    routine_list_message += "\n어떤 일정을 삭제하고 싶으신가요?"

    # 3. 응답 설정
    state["final_response"] = routine_list_message
    state["response_data"] = current_routine_groups
    state["client_action"] = "DELETE_ROUTINE_SELECT"
    state["direction"] = "save_conversation"

    return state


def format_date_short(date_string: str) -> str:
    """
    날짜 문자열을 M/D 형태로 변환
    YYYY-MM-DD -> M/D
    """
    try:
        from datetime import datetime

        if not date_string:
            return ""

        # YYYY-MM-DD 형태를 파싱
        date_obj = datetime.strptime(date_string, "%Y-%m-%d")

        # M/D 형태로 포맷팅 (앞의 0 제거)
        return f"{date_obj.month}/{date_obj.day}"

    except Exception as e:
        logger.warning(f"날짜 포맷팅 오류: {date_string}, {e}")
        return date_string



def delete_routine_direction_router(state: AgentState)->str:

    return "save_conversation"
