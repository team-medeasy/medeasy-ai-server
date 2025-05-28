import json
import logging
from typing import List, Dict, Any

from mcp_client.agent.agent_types import AgentState
from mcp_client.client import gpt_nano

logger = logging.getLogger(__name__)

"""
1. Node 파일 정리

state["client_action"] == "REVIEW_PRESCRIPTION_REGISTER_RESPONSE" 인 경우:
사용자의 메시지의 의도 파악
1. 처방전 분석 데이터로 복용 일정을 등록할 것인지.
2. 복용 일정을 수정할 것인지
3. 등록하지 않을 것인지 -> "필요하신 거 있으시면 말씀해주세요" 끝
4. 다른 요청을 처리할 것인지 -> 다른 요청을 처리하는 것

구현 방식 
current_message가 복용 일정 등록하겠다는 의사 state["response_data"] 를 추출 -> save_conversation
current_message가 일정을 수정할 때에도 일단 동일  -> 다시 client_action에 대해서 REVIEW_PRESCRIPTION_REGISTER_RESPONSE 지정 -> save_conversation

current_message가 등록하지 않겠다는 의사를 나타내면 -> state 초기화 후  final_response에 "알겠습니다! 추가로 필요하신 일 있으시면 언제든 불러주세요!" 저장 
다른 요청을 처리한다면 client_action 초기화, state return, load_tools 

 
"""


async def detect_conversation_shift(state: AgentState) -> AgentState:
    """
    대화 흐름의 변화를 감지하고 적절한 처리를 하는 노드

    특히 처방전 등록 응답 검토 후 사용자의 의도를 파악:
    1. 처방전 분석 데이터로 복용 일정을 등록할 것인지
    2. 복용 일정을 수정할 것인지
    3. 등록하지 않을 것인지
    4. 다른 요청을 처리할 것인지

    Args:
        state: 현재 에이전트 상태

    Returns:
        업데이트된 에이전트 상태
    """
    logger.info("execute detect_conversation_shift node")
    # 처방전 등록 응답 검토 단계인 경우 - 사용자의 의도 파악
    if state.get("client_action") == "REVIEW_PRESCRIPTION_REGISTER_RESPONSE":
        user_message = state.get("current_message", "")
        prescription_data = state.get("response_data")

        if not user_message:
            # 메시지가 없는 경우 그대로 반환
            return state

        # GPT-Nano를 사용하여 사용자 의도 분류
        classification_prompt = f"""
        사용자의 메시지를 분석하여 의도를 분류해주세요. 다음 네 가지 중 하나로 분류하세요.
        1. REGISTER: 처방전 분석 데이터로 복용 일정을 등록하겠다는 의도
        2. MODIFY: 복용 일정을 수정하겠다는 의도
        3. CANCEL: 등록하지 않겠다는 의도
        4. OTHER: 다른 요청이나 대화 주제 변경
        
        사용자 메시지: {user_message}
        
        분류 결과만 간단히 답변해주세요. (REGISTER/MODIFY/CANCEL/OTHER)
        """

        try:
            # GPT-Nano API 호출
            intent_response = await gpt_nano.ainvoke(classification_prompt)
            intent = intent_response.content.strip().upper()
            logger.info(f"사용자 의도 감지: '{user_message}' -> {intent}")

            # 의도에 따른 처리
            if "REGISTER" in intent: # -> check_server_action
                # 복용 일정 등록 의도
                if prescription_data:
                    # 처방전 데이터를 루틴 등록 요청 형식으로 변환 -> check_server_action으로 넘기면 자동 등록
                    routines_data = convert_prescription_to_routines(prescription_data)
                    state["server_action"] = "REGISTER_ROUTINE_LIST"
                    state["data"] = routines_data
                    state["client_action"] = None
                    state['response_data'] = None
                    state["direction"] = "check_server_actions"
                else:
                    state["final_response"] = "죄송합니다. 처방전 데이터를 찾을 수 없습니다. 다시 처방전을 업로드해주시겠어요?"
                    state["client_action"] = None
                    state["direction"] = "save_conversation"

            elif "MODIFY" in intent: # 앞으로 수정사항을 말할 예정 -> save_conversation , 수정사항을 이미 말해줬다면 수정하고 맞는지 확인 -> review_prescription_register_response를 그대로 내려주고 response_data를 업데이트 하여 save_conversation
                # 2단계: 수정 의도 세부 분석 (단순 의사 표현 vs 구체적 수정 내용)
                modification_analysis_prompt = f"""
                                사용자의 메시지에서 복용 일정 수정에 관한 구체적인 내용이 포함되어 있는지 분석해주세요.

                                1. INTENT_ONLY: 단순히 수정하고 싶다는 의사만 표현 (예: "수정할래요", "변경하고 싶어요")
                                2. WITH_DETAILS: 구체적인 수정 내용 포함 (예: "약 이름을 OO으로 바꿔주세요", "용량을 2정으로 수정해주세요")

                                사용자 메시지: {user_message}

                                분석 결과만 답변해주세요: (INTENT_ONLY/WITH_DETAILS)
                                """

                modification_type = await gpt_nano.ainvoke(modification_analysis_prompt)
                modification_type = modification_type.content.strip().upper()
                logger.info(f"수정 의도 세부 분석: '{user_message}' -> {modification_type}")

                if "WITH_DETAILS" in modification_type:
                    # 구체적인 수정 내용이 있는 경우
                    # 수정된 처방 데이터 생성 로직 필요 (사용자 메시지 기반 수정)
                    modified_data = await modify_prescription_data(prescription_data, user_message)
                    state["response_data"] = modified_data
                    state["final_response"] = "수정사항을 반영했습니다. 이대로 처방 일정을 등록할까요?"
                    # client_action 유지하여 계속 검토 단계 유지
                    state["direction"] = "save_conversation"

                else:
                    # 단순 수정 의사만 있는 경우
                    state["final_response"] = "복약 일정을 수정하겠습니다. 어떤 부분을 수정하고 싶으신가요?"
                    # client_action 유지
                    state["direction"] = "save_conversation"

            elif "CANCEL" in intent: # -> save_conversation
                # 등록 취소 의도 - 상태 초기화
                state["final_response"] = "알겠습니다! 추가로 필요하신 일 있으시면 언제든 불러주세요!"
                state["client_action"] = None
                state["response_data"] = None
                state["direction"] = "save_conversation"

            else:  # "OTHER" 또는 기타 의도 -> load_tools
                # 다른 요청 처리 - 상태 초기화 후 일반 대화 흐름으로 전환
                state["final_response"] = None  # 응답은 초기화하고 다음 단계에서 생성
                state["client_action"] = None
                state["response_data"] = None
                state["direction"] = "load_tools"

        except Exception as e:
            logger.error(f"사용자 의도 분석 중 오류 발생: {str(e)}", exc_info=True)
            # 오류 발생 시 기본 응답
            state["final_response"] = "죄송합니다. 메시지를 처리하는 중에 오류가 발생했습니다. 다시 말씀해주시겠어요?"
            state["client_action"] = None


    elif state["client_action"] == "REVIEW_PILLS_PHOTO_SEARCH_RESPONSE":
        user_message = state.get("current_message", "")
        medicines_data = state.get("response_data")

        if not user_message:
            # 메시지가 없는 경우 그대로 반환
            return state

        # GPT-Nano를 사용하여 사용자 의도 분류
        classification_prompt = f"""
           사용자의 메시지를 분석하여 의도를 분류해주세요. 다음 네 가지 중 하나로 분류하세요.
           1. NOT_FOUND: 찾는 약이 없다는 의도 (예: "찾는 약이 없어요", "원하는 약이 목록에 없네요", "다른 약을 찾고 있어요")
           2. DETAIL: 약에 대한 자세한 정보를 요청하는 의도 (예: "1번 약에 대해 자세히 알려줘", "첫 번째 약의 효능이 뭐야?", "세 번째 약 정보 더 알려줘")
           3. REGISTER: 복용 일정을 등록하겠다는 의도 (예: "이 약 등록해줘", "2번 약 복용 일정에 추가해줘", "저녁에 먹을 약으로 설정해줘")
           4. OTHER: 다른 요청이나 대화 주제 변경 (예: "고마워", "다른 질문이 있어", "메인으로 돌아가자", "오늘 복약 일정을 알려줘")

           사용자 메시지: {user_message}

           분류 결과만 간단히 답변해주세요. (NOT_FOUND/DETAIL/REGISTER/OTHER)
           """

        try:
            # GPT-Nano API 호출
            intent_response = await gpt_nano.ainvoke(classification_prompt)
            intent = intent_response.content.strip().upper()
            logger.info(f"사용자 의도 감지: '{user_message}' -> {intent}")

            if "NOT_FOUND" in intent:
                state["direction"] = "save_conversation"
                state['final_response'] = "죄송합니다. 찾는 약이 없으시군요. 의약품을 밝은 곳에서 다시 촬영해주시면 한번 더 약을 찾아드릴게요."
                state["client_action"] = "UPLOAD_PILLS_PHOTO"
                state['response_data'] = None
                return state

            elif "DETAIL" in intent: # 의약품 상제 정보를 얻고 싶을 때
                state["direction"] = "find_medicine_details"

            elif "REGISTER" in intent:
                #TODO register 구현 필요 register routine list 노드 활용하면 좋을텐데 routine_list 등록에 필요한 정보를 다 모으는 것이 목적
                state["direction"] = "register_medicine"

            else:  # "OTHER" 또는 기타 의도 -> load_tools
                # 다른 요청 처리 - 상태 초기화 후 일반 대화 흐름으로 전환
                state["final_response"] = None  # 응답은 초기화하고 다음 단계에서 생성
                state["client_action"] = None
                state["response_data"] = None
                state["direction"] = "load_tools"

                # state["tool_calls"] = []
                # state["tool_results"] = []
                # state["initial_response"] = None

        except Exception as e:
            logger.error(f"사용자 의도 분석 중 오류 발생: {str(e)}", exc_info=True)
            # 오류 발생 시 기본 응답
            state["final_response"] = "죄송합니다. 메시지를 처리하는 중에 오류가 발생했습니다. 다시 말씀해주시겠어요?"
            state["client_action"] = None


    elif state["client_action"] == "REGISTER_ROUTINE":
        state["direction"] = "register_routine"

    elif state["client_action"] == "REGISTER_ROUTINE_SEARCH_MEDICINE":
        state["direction"] = "find_routine_register_medicine"

    elif state["client_action"] == "DELETE_ROUTINE":
        state["direction"] = "delete_routine"

    elif state["client_action"] == "DELETE_ROUTINE_SELECT":
        state["direction"] = "delete_routine_select"

    return state


def convert_prescription_to_routines(prescription_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    처방전 분석 데이터를 루틴 등록 요청 형식으로 변환

    Args:
        prescription_data: 처방전 분석 결과 데이터(body 배열)

    Returns:
        List[Dict[str, Any]]: 루틴 등록 요청 데이터
    """
    routines = []

    for item in prescription_data:
        try:
            # 필수 필드 확인
            medicine_id = item.get("medicine_id")
            if not medicine_id:
                logger.warning(f"medicine_id가 없는 처방 항목 무시: {item}")
                continue

            # 추천된 스케줄만 선택 (recommended: true)
            recommended_schedules = []
            for schedule in item.get("user_schedules", []):
                if schedule.get("recommended", False):
                    recommended_schedules.append(schedule.get("user_schedule_id"))

            # 스케줄이 하나도 없으면 경고 로그 남기고 계속 진행
            if not recommended_schedules:
                logger.warning(f"추천된 스케줄이 없는 약: {item.get('medicine_name', '이름 없음')}")
                # 기본 스케줄 사용 (첫 번째 스케줄)
                if item.get("user_schedules"):
                    recommended_schedules = [item["user_schedules"][0].get("user_schedule_id")]

            # 루틴 데이터 구성
            routine = {
                "medicine_id": medicine_id,
                "nickname": item.get("medicine_name", "처방약"),  # medicine_name 사용
                "dose": item.get("dose", 1),  # 복용량
                "total_quantity": item.get("total_quantity", 30),  # 총 개수
                "user_schedule_ids": recommended_schedules,  # 추천된 스케줄 ID 목록
                "interval_days": 1  # 기본값 1
            }

            # 요일 정보 추가 (있는 경우)
            if "day_of_weeks" in item:
                routine["day_of_weeks"] = item["day_of_weeks"]

            # 시작일 관련 정보는 없으므로 현재 날짜 사용
            from datetime import date
            routine["routine_start_date"] = date.today().isoformat()

            routines.append(routine)

        except Exception as e:
            logger.error(f"처방전 항목 변환 중 오류: {str(e)}", exc_info=True)

    logger.info(f"변환된 루틴 데이터 ({len(routines)}개): {json.dumps(routines, ensure_ascii=False)}")
    return routines




async def modify_prescription_data(
        prescription_data: List[Dict[str, Any]],
        user_message: str
) -> List[Dict[str, Any]]:
    """
    사용자 메시지를 기반으로 처방전 데이터 수정

    Args:
        prescription_data: 원본 처방전 데이터
        user_message: 사용자의 수정 요청 메시지

    Returns:
        수정된 처방전 데이터
    """
    # 깊은 복사로 원본 데이터 유지
    import copy
    modified_data = copy.deepcopy(prescription_data)

    # GPT를 이용한 수정 내용 분석
    modification_prompt = f"""
    다음은 처방전 데이터입니다:
    {json.dumps(prescription_data, ensure_ascii=False)}

    사용자가 다음과 같이 수정을 요청했습니다:
    "{user_message}"

    위 데이터에서 사용자 요청에 따라 어떤 부분을 수정해야 하는지 분석해주세요.
    다음 형식으로 답변해주세요:

    {{
      "action": "수정 유형(MEDICINE_NAME/DOSE/SCHEDULE/QUANTITY/DAY)",
      "target_index": 수정할 약 인덱스(0부터 시작),
      "field": "수정할 필드명",
      "new_value": "새 값"
    }}

    복수의 수정사항이 있으면 위 형식의 JSON 객체 배열로 응답해주세요.
    """

    try:
        # GPT 응답 분석
        modification_response = await gpt_nano.ainvoke(modification_prompt)

        # JSON 파싱 시도
        try:
            modifications = json.loads(modification_response.content)

            # 단일 수정 사항인 경우 리스트로 변환
            if not isinstance(modifications, list):
                modifications = [modifications]

            # 각 수정사항 적용
            for mod in modifications:
                action = mod.get("action")
                target_idx = mod.get("target_index", 0)  # 기본값 0
                field = mod.get("field")
                new_value = mod.get("new_value")

                if target_idx < 0 or target_idx >= len(modified_data):
                    logger.warning(f"잘못된 인덱스: {target_idx}, 처방전 항목 수: {len(modified_data)}")
                    continue

                # 필드 수정
                if field and new_value is not None:
                    if field in modified_data[target_idx]:
                        # 직접 필드가 있는 경우
                        modified_data[target_idx][field] = new_value
                        logger.info(f"처방전 데이터 수정: [{target_idx}].{field} = {new_value}")
                    elif field == "medicine_name" and "medicine_name" in modified_data[target_idx]:
                        modified_data[target_idx]["medicine_name"] = new_value
                        logger.info(f"약 이름 수정: {new_value}")
                    elif field == "dose" and "dose" in modified_data[target_idx]:
                        modified_data[target_idx]["dose"] = int(new_value) if str(new_value).isdigit() else new_value
                        logger.info(f"복용량 수정: {new_value}")
                    elif field == "total_quantity" and "total_quantity" in modified_data[target_idx]:
                        modified_data[target_idx]["total_quantity"] = int(new_value) if str(
                            new_value).isdigit() else new_value
                        logger.info(f"총 수량 수정: {new_value}")
                    elif field == "user_schedule_ids" or field == "schedules":
                        # 복용 시간/스케줄 수정은 더 복잡할 수 있음
                        if isinstance(new_value, list):
                            modified_data[target_idx]["user_schedule_ids"] = new_value
                            logger.info(f"복용 스케줄 수정: {new_value}")

                # 특수 액션 처리
                if action == "REMOVE_MEDICINE" and 0 <= target_idx < len(modified_data):
                    logger.info(f"약 제거: {modified_data[target_idx].get('medicine_name')}")
                    modified_data.pop(target_idx)

        except json.JSONDecodeError:
            logger.error(f"수정 내용 파싱 실패: {modification_response}")
            # 파싱 실패 시 원본 데이터 유지

    except Exception as e:
        logger.error(f"처방전 데이터 수정 중 오류: {str(e)}", exc_info=True)

    return modified_data


def direction_router(state: AgentState) -> str:
    """
    AgentState의 direction 값에 따라 다음 실행할 노드를 결정하는 엣지 함수

    Args:
        state: 현재 에이전트 상태

    Returns:
        str: 다음 실행할 노드 이름
    """
    # direction 값 확인 (없으면 기본값으로 'save_conversation' 사용)
    direction = state.get("direction")

    # direction 로깅
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"대화 흐름 방향 결정: direction={direction}")

    # 방향에 따른 노드 결정
    if direction == "check_server_actions":
        return "check_server_actions"
    elif direction == "load_tools":
        return "load_tools"
    elif direction == "save_conversation":
        return "save_conversation"
    elif direction == "find_medicine_details":
        return "find_medicine_details"
    elif direction == "register_routine":
        return "register_routine"
    elif direction == "find_routine_register_medicine":
        return "find_routine_register_medicine"
    elif direction == "delete_routine":
        return "delete_routine"
    elif direction == "delete_routine_select":
        return "delete_routine_select"
    else:
        # 기본 방향 (direction이 없거나 알 수 없는 값인 경우)
        return "load_tools"