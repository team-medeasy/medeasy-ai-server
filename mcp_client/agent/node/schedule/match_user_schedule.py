import json
import logging
import re
from typing import List, Dict, Any, Optional

from mcp_client.agent.agent_send_message import agent_send_message
from mcp_client.agent.agent_types import AgentState
from mcp_client.client import final_response_llm

logger = logging.getLogger(__name__)

async def match_user_schedule(state: AgentState)->AgentState:
    logger.info("execute match user schedule node")
    user_message=state.get("current_message", "사용자 메시지가 없습니다.")
    schedules = state.get("response_data", [])

    if not schedules:
        state["final_response"] = "등록된 일정이 없습니다. 먼저 일정을 등록해 주세요."
        return state

    if not user_message.strip():
        state["final_response"] = "복용할 시간을 말씀해 주세요."
        return state

    system_prompt = "당신은 사용자가 언급한 일정 이름과 실제 존재하는 스케줄 이름을 매칭해주는 어시스턴스 입니다. 매칭되는 일정들의 ID를 반환해야합니다."
    match_user_schedule_prompt = f"""
            다음 일정 리스트에서 사용자가 선택한 일정들의 ID를 찾아주세요

            존재하는 사용자의 일정 리스트 : {schedules}

            사용자 메시지: "{user_message}"

            분석 기준:
            1. 시간대 이름 매칭: "아침", "점심", "저녁", "밤", "새벽" 등.
            2. 구체적인 시간 매칭: "8시", "12시", "오후 6시" 등
            3. 순서 표현: "첫 번째", "두 번째", "마지막" 등
            4. 단축된 순서 표현: '1', '2, '3' 등 ex) 사용자의 일정 리스트의 순서가 아침, 점심, 저녁, 자기 전이고 사용자가 2,4 라고 요청을 한 경우, 점심, 자기 전 추출
            
            주의사항:
            - 명확하게 매칭되지 않으면 selected_user_schedule_ids를 빈 배열로 설정하세요
            - 여러 일정이 매칭될 수 있습니다
            - 시간이 가장 유사한 것을 우선 선택하세요

            응답형식:
            {{
                "selected_user_schedule_ids": [1, 2, 3],
                "confidence": "high/medium/low/none",
                "reason": "선택 이유"
            }}

            꼭 JSON 형식으로만 응답해주세요.
        """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": match_user_schedule_prompt},
    ]

    try:
        # LLM 호출
        llm_response = await final_response_llm.ainvoke(messages)

        # 응답 파싱
        parsed_result = parse_schedule_matching_response(llm_response.content)

        if parsed_result and parsed_result.get("selected_user_schedule_ids"):
            schedule_ids = parsed_result["selected_user_schedule_ids"]
            confidence = parsed_result.get("confidence", "medium")
            reason = parsed_result.get("reason", "")

            # 유효한 스케줄 ID인지 확인
            valid_schedule_ids = validate_schedule_ids(schedule_ids, schedules)

            if valid_schedule_ids:
                # temp_data에 스케줄 ID 저장
                temp_data = state.get("temp_data", {})
                temp_data["user_schedule_ids"] = valid_schedule_ids
                state["temp_data"] = temp_data
                logger.info(f"save temp_data's user_schedule_ids: {state['temp_data']}")

                # 매칭된 스케줄 정보 생성
                matched_schedules_info = get_matched_schedules_info(valid_schedule_ids, schedules)
                logger.info(f"matched_schedules_info: {matched_schedules_info}")

                agent_message = f"다음 일정으로 설정되었습니다: {matched_schedules_info}."
                await agent_send_message(state, agent_message)
                state["client_action"] = "register_routine"
                state["direction"] = "register_routine"

                logger.info(f"스케줄 매칭 완료: {valid_schedule_ids} (신뢰도: {confidence})")
                logger.info(f"매칭 이유: {reason}")

            else:
                state["final_response"] = "언급하신 일정을 찾을 수 없습니다. 다음 중에서 선택해 주세요:\n" + format_schedules_for_user(schedules)

        else:
            # 매칭 실패 시 사용자에게 선택지 제공
            schedule_list = format_schedules_for_user(schedules)
            state[
                "final_response"] = f"언급하신 시간을 정확히 파악할 수 없습니다. 다음 일정 중에서 선택해 주세요:\n\n{schedule_list}\n\n예: '아침하고 저녁에 먹을게요' 또는 '1번하고 3번 일정으로 해주세요'"

    except Exception as e:
        logger.exception(f"스케줄 매칭 중 오류: {str(e)}")
        state["final_response"] = "일정 매칭 중 오류가 발생했습니다. 다시 시도해 주세요."

    return state


def format_schedules_for_analysis(schedules: List[Dict[str, Any]]) -> str:
    """
    LLM 분석용 스케줄 리스트 포맷팅

    Args:
        schedules: 스케줄 리스트

    Returns:
        포맷팅된 스케줄 텍스트
    """
    formatted_lines = []

    for schedule in schedules:
        schedule_id = schedule.get("schedule_id") or schedule.get("id")
        name = schedule.get("name", "알 수 없음")
        time = schedule.get("time", "")
        description = schedule.get("description", "")

        # 시간 정보 포맷팅
        time_info = f" ({time})" if time else ""
        desc_info = f" - {description}" if description else ""

        formatted_lines.append(f"ID: {schedule_id}, 이름: {name}{time_info}{desc_info}")

    return "\n".join(formatted_lines)

def format_schedules_for_user(schedules: List[Dict[str, Any]]) -> str:
    """
    사용자용 스케줄 리스트 포맷팅

    Args:
        schedules: 스케줄 리스트

    Returns:
        사용자용 스케줄 텍스트
    """
    formatted_lines = []

    for idx, schedule in enumerate(schedules, 1):
        name = schedule.get("name", "")
        time = schedule.get("time_time", "")

        time_info = f" ({time})" if time else ""
        formatted_lines.append(f"{idx}. {name}{time_info}")

    return "\n".join(formatted_lines)

def parse_schedule_matching_response(response_content: str) -> Optional[Dict[str, Any]]:
    """
    LLM 응답에서 스케줄 매칭 정보 파싱

    Args:
        response_content: LLM 응답 텍스트

    Returns:
        파싱된 매칭 정보 또는 None
    """
    try:
        # JSON 부분 추출
        json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            parsed_data = json.loads(json_str)

            # 데이터 검증
            if "selected_user_schedule_ids" in parsed_data:
                schedule_ids = parsed_data["selected_user_schedule_ids"]
                if isinstance(schedule_ids, list):
                    # ID들이 정수인지 확인하고 변환
                    valid_ids = []
                    for sid in schedule_ids:
                        try:
                            valid_ids.append(int(sid))
                        except (ValueError, TypeError):
                            continue

                    parsed_data["selected_user_schedule_ids"] = valid_ids
                    return parsed_data

        return None

    except Exception as e:
        logger.error(f"스케줄 매칭 응답 파싱 중 오류: {str(e)}")
        return None


def validate_schedule_ids(schedule_ids: List[int], schedules: List[Dict[str, Any]]) -> List[int]:
    """
    스케줄 ID들이 유효한지 확인

    Args:
        schedule_ids: 확인할 스케줄 ID 리스트
        schedules: 전체 스케줄 리스트

    Returns:
        유효한 스케줄 ID 리스트
    """
    valid_ids = []
    existing_ids = []

    # 기존 스케줄 ID들 추출
    for schedule in schedules:
        sid = schedule.get("user_schedule_id") or schedule.get("id")
        if sid:
            existing_ids.append(int(sid))

    # 요청된 ID들이 존재하는지 확인
    for sid in schedule_ids:
        if sid in existing_ids:
            valid_ids.append(sid)

    return valid_ids


def format_time(time_str: str) -> str:
    """
    HH:MM:SS 형태의 시간을 H시 M분 형태로 변환

    Args:
        time_str: "01:30:00" 형태의 시간 문자열

    Returns:
        "1시 30분" 형태의 포맷된 시간 문자열
    """
    if not time_str:
        return ""

    try:
        # HH:MM:SS에서 시, 분 추출
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])

        # 포맷팅
        result = ""
        if hours > 0:
            result += f"{hours}시"
        if minutes > 0:
            if result:  # 시간이 있으면 공백 추가
                result += " "
            result += f"{minutes}분"

        return result if result else "0분"

    except (ValueError, IndexError):
        return time_str  # 파싱 실패시 원본 반환


def get_matched_schedules_info(schedule_ids: List[int], schedules: List[Dict[str, Any]]) -> str:
    """
    매칭된 스케줄들의 정보를 사용자 친화적 형태로 반환

    Args:
        schedule_ids: 매칭된 스케줄 ID 리스트
        schedules: 전체 스케줄 리스트

    Returns:
        매칭된 스케줄 정보 텍스트
    """
    matched_names = []

    for schedule in schedules:
        sid = schedule.get("user_schedule_id") or schedule.get("id")
        if sid and int(sid) in schedule_ids:
            name = schedule.get("name", "알 수 없음")
            time = schedule.get("take_time", "")

            if time:
                formatted_time = format_time(time)
                matched_names.append(f"{name}({formatted_time})")
            else:
                matched_names.append(name)

    return ", ".join(matched_names) if matched_names else "선택된 일정"


# 사용 예시를 위한 더미 스케줄 데이터
def get_example_schedules():
    """예시 스케줄 데이터"""
    return [
        {"schedule_id": 37, "name": "아침", "time": "08:00", "description": "아침 식사 후"},
        {"schedule_id": 38, "name": "점심", "time": "12:00", "description": "점심 식사 후"},
        {"schedule_id": 39, "name": "저녁", "time": "19:00", "description": "저녁 식사 후"},
        {"schedule_id": 40, "name": "취침전", "time": "22:00", "description": "잠자기 전"}
    ]

def match_user_schedule_direction_router(state:AgentState) -> str:
    if state.get("direction")=="register_routine":
        return "register_routine"
    else:
        return "save_conversation"