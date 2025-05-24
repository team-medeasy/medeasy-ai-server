import logging
from typing import Optional, Dict, List

from mcp_client.agent.agent_send_message import agent_send_message
from mcp_client.agent.agent_types import AgentState
from mcp_client.client import final_response_llm

logger = logging.getLogger(__name__)

async def find_routine_register_medicine(state: AgentState)->AgentState:
    logger.info("execute find routine register medicine node")
    user_message=state.get("current_message", "사용자 메시지가 없습니다.")
    medicines = state.get("response_data", [])

    if not medicines:
        state["final_response"] = "검색된 의약품이 없습니다."
        return state

    # 간결한 시스템 프롬프트
    system_prompt = "당신은 사용자의 의약품 선택을 도와주는 전문 어시스턴트입니다. 정확한 의약품 ID를 반환해야 합니다."

    find_routine_register_medicine_prompt = f"""
        다음 의약품 검색 결과에서 사용자가 선택한 의약품의 ID를 찾아주세요.
        
        검색된 의약품 데이터 리스트 : {state.get("response_data", [])}
        
        사용자 메시지: "{user_message}"
        
        분석 기준:
        1. 사용자가 번호를 언급한 경우 (예: "1번", "첫 번째", "두 번째")
        2. 사용자가 구체적인 약품명을 언급한 경우
        3. 사용자가 제조사나 특징을 언급한 경우
        4. 사용자가 "네", "맞아요", "그거요" 등의 긍정 표현을 사용한 경우
        5. 사용자가 다른 종류의 의약품을 검색하거나, 아예 다른 요청을 할 경우 confidence 문자열값을 none 주세요.
        
        주의사항:
        - 명확하게 매칭되지 않으면 selected_medicine_id를 null로 설정하세요
        
        응답형식:
        {{
            "selected_medicine_id": "의약품ID" 또는 null,
            "confidence": "high/medium/low/none",
            "reason": "선택 이유"
        }}
        
        꼭 JSON 형식으로만 응답해주세요.
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content":find_routine_register_medicine_prompt},
    ]

    try:
        llm_response= await final_response_llm.ainvoke(messages)

        # 응답 파싱
        selected_medicine = parse_medicine_selection_response(llm_response.content)
        logger.info(f"find_routine_register_medicine llm response after parse selected_medicine: {selected_medicine}")

        if selected_medicine.get("confidence") == "none":
            state["direction"] = "register_routine"
            state["client_action"] = "REGISTER_ROUTINE"
            state["response_data"] = None
            return state

        if selected_medicine and selected_medicine.get("selected_medicine_id"):
            # 선택된 의약품 처리
            medicine_id = selected_medicine["selected_medicine_id"]
            selected_medicine_info = find_medicine_by_id(medicines, medicine_id)

            if selected_medicine_info:
                # medicine_id만 업데이트
                state["temp_data"]["medicine_id"] = medicine_id

                logger.info(f"약을 선택한 이유: {selected_medicine.get('reason')}, 선택 정확도: {selected_medicine.get('confidence')}")

                agent_message = f"'{selected_medicine_info.get('item_name')}'이 선택되었습니다."
                await agent_send_message(state, agent_message)

                state["client_action"] = "REGISTER_ROUTINE"
                state["direction"] = "register_routine"
                return state
            else:
                state["final_response"] = "선택하신 의약품 정보를 찾을 수 없습니다. 나중에 다시 시도해주세요."
                state["client_action"] = None
                state["direction"] = "save_conversation"
                return state
        else:
            # 선택되지 않은 경우
            medicine_list = format_medicine_list_for_user(medicines)
            state["final_response"] = f"선택하신 의약품을 명확히 파악할 수 없습니다. 다음 중에서 선택해 주세요:\n\n{medicine_list}"
            state["direction"] = "save_conversation"

    except Exception as e:
        logger.exception(f"의약품 선택 처리 중 오류: {str(e)}")
        state["final_response"] = "의약품 선택 처리 중 오류가 발생했습니다."
        state["direction"] = "save_conversation"

    return state


def parse_medicine_selection_response(response_content: str) -> Optional[Dict]:
    """LLM 응답에서 의약품 선택 정보 파싱"""
    try:
        import json
        import re

        # JSON 부분 추출
        json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            return json.loads(json_str)

        return None
    except Exception as e:
        logger.error(f"응답 파싱 중 오류: {str(e)}")
        return None

def find_medicine_by_id(medicines: List[Dict], medicine_id: str) -> Optional[Dict]:
    """ID로 의약품 찾기"""
    for medicine in medicines:
        if (str(medicine.get("id", "")) == medicine_id or
            str(medicine.get("item_seq", "")) == medicine_id):
            return medicine
    return None


def format_medicines_for_selection(medicines: List[Dict]) -> str:
    """LLM 분석용 의약품 리스트 포맷팅"""
    formatted_lines = []
    for idx, medicine in enumerate(medicines, 1):
        medicine_id = medicine.get("medicine_id") or medicine.get("item_seq") or str(idx)
        item_name = medicine.get("item_name", "알 수 없음")
        entp_name = medicine.get("entp_name", "알 수 없음")

        formatted_lines.append(f"{idx}. [ID: {medicine_id}] {item_name} - {entp_name}")

    return "\n".join(formatted_lines)


def format_medicine_list_for_user(medicines: List[Dict]) -> str:
    """사용자용 의약품 리스트 포맷팅"""
    formatted_lines = []
    for idx, medicine in enumerate(medicines, 1):
        item_name = medicine.get("item_name", "알 수 없음")
        entp_name = medicine.get("entp_name", "알 수 없음")
        formatted_lines.append(f"{idx}. {item_name} - {entp_name}")

    return "\n".join(formatted_lines)

def find_routine_register_medicine_direction_router(state: AgentState) -> str:
    if state["direction"] == "register_routine" :
        return "register_routine"

    else:
        return "save_conversation"
