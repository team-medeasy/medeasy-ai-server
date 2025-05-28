import re
import json
import logging
from typing import Optional, Dict, Any

from mcp_client.agent.agent_types import AgentState
from mcp_client.agent.node.schedule.match_user_schedule import format_schedules_for_user
from mcp_client.chat_session_repo import chat_session_repo
from mcp_client.client import final_response_llm
from mcp_client.prompt import system_prompt
from mcp_client.service.medicine_service import search_medicines_by_name, find_medicine_by_id
from mcp_client.service.routine_service import register_single_routine
from mcp_client.service.schedule_service import get_user_schedules_info
from mcp_client.service.user_service import get_user_info

logger = logging.getLogger(__name__)

register_routine_prompt = """
사용자의 메시지를 분석하여 아래와 같은 결과를 출력해주세요. 메시지로부터 추출할 값들을 넣되 언급이 없는 값들은 null 값으로 넣어주세요.

응답 템플릿 예시:
{
    "extracted_data": {
        "medicine_name": "씬지록신정",
        "dose": 5,
        "user_schedule_names": ["아침", "점심"],
        "total_quantity": 6,
        "dose_days": 3
    },
    "extraction_reasoning": {
        "medicine_name": "사용자가 '씬지록신정을 복용하겠다'고 명시적으로 언급했습니다.",
        "dose": "사용자가 '하루에 5mg씩'이라고 구체적인 복용량을 제시했습니다.",
        "user_schedule_names": "사용자가 '아침과 점심에 먹겠다'고 시간대를 명확히 지정했습니다.",
        "total_quantity": "사용자가 '총 6알 있다'고 보유 수량을 언급했습니다.",
        "dose_days": "사용자가 '3일간 복용 예정'이라고 기간을 명시했습니다."
    },
    "conversation_flow": {
        "current_intent": "register_routine",
        "flow_changed": false,
        "new_intent": null,
        "confidence": 0.95,
        "reasoning": "사용자가 복용 일정 등록과 관련된 내용만 언급하여 대화 흐름이 유지되고 있습니다."
    }
}

필드 설명:
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
- 약 이름에 숫자가 섞여있는 경우가 있는데 이때 그 숫자를 복용량으로 헷갈려서 dose나 total_quantity 에 값을 넣으면 안돼
- 약 복약 정보에 대한 숫자 메시지가 들어오면, dose와 quantity 중 어디에 값을 넣을지 명확하지 않다면 과거 채팅 내역 중 agent 역할 즉 너가 한 가장 최근의 질문을 보면서 유추해줘

extraction_reasoning 필드 작성 가이드:
- 각 필드를 추출한 구체적인 근거를 명시하세요.
- 사용자 메시지의 어떤 부분에서 해당 정보를 추출했는지 설명하세요.
- null 값인 경우 "해당 정보가 메시지에 언급되지 않았습니다"라고 작성하세요.
- 이전 대화 내역을 참고한 경우 그 내용도 명시하세요.

conversation_flow 분석 가이드:
- current_intent: "register_routine" (고정)
- flow_changed: 복용 일정 등록이 아닌 다른 의도가 감지되면 true
- new_intent: 새로 감지된 의도 ("view_routine", "register_prescription_routine", "medication_check" 등)
- confidence: 의도 판단의 확실성 (0.7 이상이면 흐름 변경으로 판단)
- reasoning: 구체적인 판단 근거 설명

흐름 변경을 감지하는 키워드 예시:
사용자가 복약 일정 등록과 무관한 요청을 한경우 지금 수행 중인 복약 일정 등록 사이클을 벗어나야함.
ex) 처방전 등록, 알약 촬영 등록, 복약 체크, 오늘 복약 정보 조회, 복약 삭제, 목소리 변환 등
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
    logger.info(f"temp data debugging: {state['temp_data']}")

    history_prompt = f"""
    이전 대화 내역: {state["messages"]}
    """
    logger.info(f"이전 대화 내역: {history_prompt}")

    # temp_data 초기화 또는 업데이트
    if not state["temp_data"]:
        # 기존 채팅 세션이 있으면 삭제 (이전 대화 내역 초기화)
        user_id = state["temp_data"]
        if user_id and chat_session_repo.session_exists(user_id):
            chat_session_repo.clear_session(user_id)
            logger.info(f"이전 대화 내역 초기화 완료: user_id={user_id}")

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
    parsed_data, extraction_reasoning, conversation_flow = parse_llm_response_with_reasoning(llm_response.content)
    logger.info(f"parsed_data: {parsed_data}")
    logger.info(f"extraction_reasoning: {extraction_reasoning}")
    logger.info(f"conversation_flow: {conversation_flow}")

    if conversation_flow["flow_changed"]:
        state["direction"] = "load_tools"
        state["client_action"] = None
        state["temp_data"] = None
        state["response_data"] = None
        return state

    if not parsed_data and not state["temp_data"]["medicine_id"] and not state["temp_data"]["user_schedule_ids"]:
        state["final_response"] = "복용 일정 등록에 필요한 약 이름, 복용량, 복용 시간 정보를 말씀해 주세요."
        state["direction"] = "save_conversation"
        return state

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

    if parsed_data.get("dose") and not state["temp_data"]["dose"]:
        state['temp_data']['dose'] = parsed_data.get("dose")

    if parsed_data.get("total_quantity") and not state["temp_data"]["total_quantity"]:
        state['temp_data']['total_quantity'] = parsed_data.get("total_quantity")

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


def parse_llm_response_with_reasoning(response_content):
    """LLM 응답에서 JSON을 파싱하고 extracted_data, extraction_reasoning, conversation_flow를 분리"""
    try:
        # 1. JSON 부분만 추출 (중괄호로 둘러싸인 부분)
        json_match = re.search(r'\{.*\}', response_content, re.DOTALL)

        if not json_match:
            logger.warning("응답에서 JSON 형식을 찾을 수 없습니다.")
            return None, None, None

        json_str = json_match.group()
        # logger.info(f"추출된 JSON 문자열: {json_str}")

        # 2. JSON 파싱
        parsed_response = json.loads(json_str)
        # logger.info(f"파싱된 JSON: {parsed_response}")

        # 3. 응답 구조 검증
        if "extracted_data" not in parsed_response:
            logger.warning("extracted_data 필드가 없습니다. 기존 형식으로 처리합니다.")
            # 기존 형식 (직접 데이터가 최상위에 있는 경우) 처리
            extracted_data = {
                "medicine_name": parsed_response.get("medicine_name"),
                "dose": parsed_response.get("dose"),
                "user_schedule_names": parsed_response.get("user_schedule_names"),
                "total_quantity": parsed_response.get("total_quantity"),
                "dose_days": parsed_response.get("dose_days")
            }
            extraction_reasoning = {}
            # 기존 형식에서는 conversation_flow 기본값 설정
            conversation_flow = {
                "current_intent": "register_routine",
                "flow_changed": False,
                "new_intent": None,
                "confidence": 1.0,
                "reasoning": "기존 형식 응답으로 conversation_flow 기본값 설정"
            }
        else:
            # 4. extracted_data, extraction_reasoning, conversation_flow 분리
            extracted_data = parsed_response.get("extracted_data", {})
            extraction_reasoning = parsed_response.get("extraction_reasoning", {})
            conversation_flow = parsed_response.get("conversation_flow", {
                "current_intent": "register_routine",
                "flow_changed": False,
                "new_intent": None,
                "confidence": 1.0,
                "reasoning": "conversation_flow 필드가 없어 기본값 설정"
            })

        # 5. conversation_flow 필드 검증 및 기본값 보정
        if not isinstance(conversation_flow, dict):
            logger.warning("conversation_flow가 dict 타입이 아닙니다. 기본값으로 설정합니다.")
            conversation_flow = {
                "current_intent": "register_routine",
                "flow_changed": False,
                "new_intent": None,
                "confidence": 1.0,
                "reasoning": "conversation_flow 타입 오류로 기본값 설정"
            }

        # conversation_flow 필수 필드 확인 및 기본값 설정
        default_flow = {
            "current_intent": "register_routine",
            "flow_changed": False,
            "new_intent": None,
            "confidence": 1.0,
            "reasoning": "필수 필드 누락으로 기본값 설정"
        }

        for key, default_value in default_flow.items():
            if key not in conversation_flow:
                conversation_flow[key] = default_value
                logger.warning(f"conversation_flow에서 {key} 필드가 누락되어 기본값으로 설정했습니다.")

        # 6. 추출된 데이터 검증 및 로깅
        # logger.info(f"추출된 데이터: {extracted_data}")
        # logger.info(f"추출 이유: {extraction_reasoning}")
        # logger.info(f"대화 흐름: {conversation_flow}")

        # 7. 필수 필드 존재 여부 확인
        required_fields = ["medicine_name", "dose", "user_schedule_names", "total_quantity"]
        missing_fields = [field for field in required_fields if field not in extracted_data]
        if missing_fields:
            logger.warning(f"누락된 필드: {missing_fields}")

        # 8. 데이터 타입 검증
        if extracted_data.get("dose") is not None and not isinstance(extracted_data["dose"], (int, float)):
            logger.warning(f"dose 필드의 타입이 올바르지 않습니다: {type(extracted_data['dose'])}")

        if extracted_data.get("total_quantity") is not None and not isinstance(extracted_data["total_quantity"], (int, float)):
            logger.warning(f"total_quantity 필드의 타입이 올바르지 않습니다: {type(extracted_data['total_quantity'])}")

        if extracted_data.get("user_schedule_names") is not None and not isinstance(extracted_data["user_schedule_names"], list):
            logger.warning(f"user_schedule_names 필드의 타입이 올바르지 않습니다: {type(extracted_data['user_schedule_names'])}")

        # 9. conversation_flow 타입 검증
        if not isinstance(conversation_flow.get("flow_changed"), bool):
            logger.warning("flow_changed 필드가 boolean 타입이 아닙니다.")
            conversation_flow["flow_changed"] = False

        if not isinstance(conversation_flow.get("confidence"), (int, float)):
            logger.warning("confidence 필드가 숫자 타입이 아닙니다.")
            conversation_flow["confidence"] = 1.0

        return extracted_data, extraction_reasoning, conversation_flow

    except json.JSONDecodeError as e:
        logger.error(f"JSON 디코딩 오류: {e}")
        logger.error(f"문제가 된 JSON 문자열: {json_str if 'json_str' in locals() else 'N/A'}")
        return None, None, None

    except Exception as e:
        logger.error(f"예상치 못한 파싱 오류: {e}")
        logger.error(f"응답 내용: {response_content}")
        return None, None, None


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