import re
import json
import logging
from typing import Optional, Dict, Any

from mcp_client.agent.agent_types import AgentState
from mcp_client.agent.node.schedule.match_user_schedule import format_schedules_for_user
from mcp_client.client import final_response_llm
from mcp_client.prompt import system_prompt
from mcp_client.service.medicine_service import search_medicines_by_name, find_medicine_by_id
from mcp_client.service.routine_service import register_single_routine
from mcp_client.service.schedule_service import get_user_schedules_info
from mcp_client.service.user_service import get_user_info

logger = logging.getLogger(__name__)

register_routine_prompt = """
사용자의 메시지를 분석하여 아래와 같은 결과를 출력해주세요.
메시지로부터 추출할 값들을 넣되 언급이 없는 값들은 null 값으로 넣어주세요.

응답 템플릿 예시: 
{
    "medicine_name": "씬지록신정",
    "dose": 5,
    "user_schedule_names": ["아침", "점심"],
    "total_quantity": 6,
    "dose_days": 3
}

예시 필드 설명: 
- medicine_name: 사용자가 복용하려는 약의 이름입니다.
- dose: 1회 복용량입니다.
- user_schedule_names: 사용자가 약을 먹을 시간들입니다 (예: ["아침", "저녁"]).
- total_quantity: 복용 일정을 등록할 총 약의 개수입니다.
- dose_days: 약을 복용할 날 수 입니다.

시간 추출 예시:
- "아침에 먹을거야" → {"user_schedule_names": ["아침"]}
- "저녁에 복용하겠습니다" → {"user_schedule_names": ["저녁"]}
- "아침, 저녁으로 해주세요" → {"user_schedule_names": ["아침", "저녁"]}

주의사항: 
- 시간대 이름(아침, 점심, 저녁 등)이 언급되면 user_schedule_names에 넣으세요.
- 응답은 반드시 JSON 형식으로만 출력해주세요.
- JSON 외의 다른 텍스트는 포함하지 마세요.
- dose, total_quantity에 대해서 숫자만 언급하더라도 등록해줘 : '7개', '7', '7정' -> 7
- 이전 채팅 내역을 참고하여 자연스러운 흐름으로 대화를 진행해줘 
"""

async def register_routine(state: AgentState)->AgentState:
    """
    state[response_data] = {
        medicine_id: 1234,
        nickname: null,
        dose: 1,
        user_schedule_ids: [37, 38, 39],
        total_quantity: 6
    }
    """
    logger.info("execute register routine node")

    history_prompt = f"""
    이전 대화 내역: {state["messages"]}
    """
    logger.info(f"이전 대화 내역: {history_prompt}")

    # temp_data 초기화 또는 업데이트
    if not state["temp_data"]:
        state["temp_data"] = {
            "medicine_id": None,
            "nickname": None,
            "dose": None,
            "user_schedule_ids": None,
            "total_quantity": None
        }

    temp_data=state.get("temp_data")
    user_message = state.get("current_message", "")
    jwt_token = state.get("jwt_token")

    messages = [
        {"role": "system", "content": history_prompt},
        {"role": "system", "content": system_prompt+register_routine_prompt},
        {"role": "user", "content": user_message},
    ]

    llm_response= await final_response_llm.ainvoke(messages)
    # LLM 응답에서 JSON 파싱
    parsed_data = parse_llm_response(llm_response.content)
    logger.info(f"parsed_data: {parsed_data}")

    if not parsed_data and not state["temp_data"]["medicine_id"] and not state["temp_data"]["user_schedule_ids"]:
        logger.info("복용 일정 첫 질문 시작")
        state["final_response"] = "복용 일정 등록에 필요한 약 이름, 복용량, 복용 시간 정보를 말씀해 주세요."
        state["direction"] = "save_conversation"
        return state

    # 일단 의약품 이름 검사전에 복용량 정보가 있다면 대입, 맨 마지막에 값이 없으면 대입
    if parsed_data.get("dose"):
        state['temp_data']['dose'] = parsed_data.get("dose")
        logger.info(f"temp data debugging: {state['temp_data']}")

    if parsed_data.get("total_quantity"):
        state['temp_data']['total_quantity'] = parsed_data.get("total_quantity")
        logger.info(f"temp data debugging: {state['temp_data']}")

    # medicine_name이 추출되었는지 확인
    medicine_name = parsed_data.get("medicine_name")
    if not state["temp_data"]["medicine_id"] and medicine_name:
        logger.info(f"medicine_name: {medicine_name}")
        # 사용자의 메시지에 약이 언급된 경우
        # medicine search -> 검색된 데이터들을 리스트로 제공, 이 중 복용하실 의약품이 있으신가요?
        medicines = await search_medicines_by_name(jwt_token, medicine_name)
        state["response_data"] = medicines
        state["final_response"] = "의약품 검색 결과입니다. 복용 일정을 등록할 의약품이 있으신가요?"
        state["client_action"] = "REGISTER_ROUTINE_SEARCH_MEDICINE"
        state["direction"] = "save_conversation"
        return state

    if not medicine_name and not temp_data.get("medicine_id"):
        logger.info("not medicine id and name")
        # 의약품 검색
        state["final_response"] = "복용일정 등록을 위해 의약품 이름을 말씀해주세요!"
        state["client_action"] = "REGISTER_ROUTINE"
        state["direction"] = "save_conversation"

        return state

    # 메시지 스케줄 정보 추출
    if not state["temp_data"]["user_schedule_ids"]:
        if parsed_data.get("user_schedule_names"):
            """
                1. 사용자의 스케줄 리스트를 추출 schedule_service 파일에 메소드 하나 추가 
                2. names와 매칭되는 스케줄 ids 추출 
                3. ids 저장
            """
            logger.info("스케줄 매칭")
            schedules = await get_user_schedules_info(jwt_token)
            state["response_data"] = schedules
            state["direction"] = "match_user_schedule"
            return state

        # 상태에 스케줄에 대한 정보가 없는데, 사용자의 메시지에도 스케줄 내용이 없는 경우
        if not parsed_data.get("user_schedule_names"):
            """
                1. 사용자의 스케줄 리스트를 추출
                2. 이 시간 중 약을 언제 드시고 싶으신가요??
            """
            schedules = await get_user_schedules_info(jwt_token)
            user = await get_user_info(state["jwt_token"])
            state["response_data"] = schedules
            state["client_action"] = "REGISTER_ROUTINE"
            state["final_response"] = f"""다음 {user.get("name")}님의 일정 중에서 약을 언제 복용하실건가요?
            {format_schedules_for_user(schedules)}
            """
            state["direction"] = "save_conversation"
            return state

    if not parsed_data.get("dose") and not state["temp_data"]["dose"]:
        state["final_response"] = "의약품의 1회 복용량을 알려주세요!"
        state["client_action"] = "REGISTER_ROUTINE"
        state["direction"] = "save_conversation"
        state["response_data"] = None
        return state

    if not parsed_data.get("total_quantity") and not state["temp_data"]["total_quantity"]:
        state["final_response"] = "의약품의 총 개수를 알려주세요!"
        state["client_action"] = "REGISTER_ROUTINE"
        state["direction"] = "save_conversation"
        state["response_data"] = None
        return state

    if state["temp_data"]["medicine_id"] and state["temp_data"]["user_schedule_ids"]and state["temp_data"]["dose"] and state["temp_data"]["total_quantity"]:
        if not state["temp_data"]["nickname"]:
            medicine=await find_medicine_by_id(jwt_token, state["temp_data"]["medicine_id"])
            state["temp_data"]["nickname"] = medicine.get("item_name")

        await register_single_routine(
            jwt_token,
            state["temp_data"]["medicine_id"],
            state["temp_data"]["nickname"],
            state["temp_data"]["user_schedule_ids"],
            state["temp_data"]["dose"],
            state["temp_data"]["total_quantity"],
        )

        state["final_response"] = "복용 일정 등록이 완료되었습니다! 일정 확인이 필요하시면 말씀해주세요!"
        state["direction"] = "save_conversation"
        logger.info("register routine node finish")
        return state


def parse_llm_response(response_content: str) -> Optional[Dict[str, Any]]:
    """
    LLM 응답에서 JSON 데이터 추출 및 파싱

    Args:
        response_content: LLM 응답 텍스트

    Returns:
        파싱된 딕셔너리 또는 None
    """
    try:
        # 응답에서 JSON 부분만 추출
        json_content = extract_json_from_text(response_content)

        if not json_content:
            logger.error("LLM 응답에서 JSON을 찾을 수 없습니다")
            return None

        # JSON 파싱
        parsed_data = json.loads(json_content)

        # 데이터 검증
        validated_data = validate_medicine_data(parsed_data)

        return validated_data

    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {str(e)}")
        logger.error(f"파싱 시도한 내용: {json_content}")
        return None
    except Exception as e:
        logger.error(f"LLM 응답 파싱 중 오류: {str(e)}")
        return None


def extract_json_from_text(text: str) -> Optional[str]:
    """
    텍스트에서 JSON 부분만 추출

    Args:
        text: 전체 텍스트

    Returns:
        JSON 문자열 또는 None
    """
    # 중괄호로 둘러싸인 JSON 패턴 찾기
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(json_pattern, text, re.DOTALL)

    if matches:
        # 가장 완전해 보이는 JSON 선택 (가장 긴 것)
        return max(matches, key=len)

    # 중괄호 패턴이 없으면 전체 텍스트에서 JSON 형태로 보이는 부분 추출
    # 코드 블록 안의 JSON 찾기
    code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    code_matches = re.findall(code_block_pattern, text, re.DOTALL)

    if code_matches:
        return code_matches[0]

    # 직접적인 JSON 구조 찾기
    if '{' in text and '}' in text:
        start = text.find('{')
        end = text.rfind('}') + 1
        return text[start:end]

    return None


def validate_medicine_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    추출된 약품 데이터 검증 및 정리

    Args:
        data: 파싱된 데이터

    Returns:
        검증된 데이터
    """
    validated = {}

    # medicine_name 검증
    medicine_name = data.get("medicine_name")
    if medicine_name and isinstance(medicine_name, str):
        validated["medicine_name"] = medicine_name.strip()

    # dose 검증
    dose = data.get("dose")
    if dose is not None:
        try:
            validated["dose"] = int(dose) if dose != "null" else None
        except (ValueError, TypeError):
            validated["dose"] = 1  # 기본값

    # user_schedule_names 검증
    schedule_names = data.get("user_schedule_names")
    if schedule_names and isinstance(schedule_names, list):
        validated["user_schedule_names"] = [name for name in schedule_names if name and name != "null"]

    # user_schedule_times 검증
    schedule_times = data.get("user_schedule_times")
    if schedule_times and isinstance(schedule_times, list):
        # 시간 형식 검증 (HH:MM)
        valid_times = []
        for time_str in schedule_times:
            if time_str and time_str != "null" and re.match(r'^\d{1,2}:\d{2}$', time_str):
                valid_times.append(time_str)
        validated["user_schedule_times"] = valid_times

    # total_quantity 검증
    total_quantity = data.get("total_quantity")
    if total_quantity is not None:
        try:
            validated["total_quantity"] = int(total_quantity) if total_quantity != "null" else None
        except (ValueError, TypeError):
            validated["total_quantity"] = None

    # dose_days 검증
    dose_days = data.get("dose_days")
    if dose_days is not None:
        try:
            validated["dose_days"] = int(dose_days) if dose_days != "null" else None
        except (ValueError, TypeError):
            validated["dose_days"] = None

    return validated

def register_routine_direction_router(state: AgentState)->str:
    if state["direction"] == "find_routine_register_medicine":
        return "find_routine_register_medicine"
    elif state["direction"] == "save_conversation":
        return "save_conversation"
    elif state["direction"] == "match_user_schedule":
        return "match_user_schedule"
    else:
        return "load_tools"