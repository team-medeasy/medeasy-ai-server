from mcp_client.agent.agent_types import AgentState
import re
import logging
import json
from langchain_openai import ChatOpenAI

from mcp_client.service.routine_service import delete_routine_group

logger = logging.getLogger(__name__)
gpt_mini = ChatOpenAI(model_name="gpt-4.1-mini")

# 복용 일정 선택 분석 프롬프트
routine_selection_prompt = """
사용자의 메시지와 이전 대화 내역을 분석하여 삭제할 복용 일정을 식별해주세요.

사용자는 다음과 같은 방식으로 삭제할 일정을 지정할 수 있습니다:
1. 번호로 선택 (예: "1번", "2, 3번", "첫번째")  
2. 약 이름으로 선택 (예: "에소졸정", "클래리트로마이신", "아세클로페낙")
3. 날짜로 선택 (예: "5월 29일부터", "5/27~5/29", "27일 시작하는")
4. 조합으로 선택 (예: "에소졸정 5/29부터", "1번하고 클래리트로마이신")

응답 형식:
{{
    "selected_routine_indices": [0, 2],
    "confidence": "high|medium|low",
    "reasoning": "선택한 이유와 근거를 상세히 설명",
    "matched_criteria": {{
        "method": "number|name|date|combination",
        "details": "구체적인 매칭 기준"
    }},
    "clarification_message": "신뢰도가 낮을 때 사용자에게 보여줄 친화적인 질문 메시지"
}}

confidence 기준:
- high: 명확한 번호나 정확한 약 이름으로 특정됨
- medium: 약 이름의 일부나 날짜로 특정되었지만 여러 후보가 있을 수 있음  
- low: 모호하거나 여러 해석이 가능함

clarification_message 작성 가이드 (confidence가 low일 때):
- 사용자가 무엇을 입력했는지 인정하되, 어떤 정보가 더 필요한지 친절하게 물어보세요
- 구체적인 예시를 포함하여 도움을 주세요
- 기술적인 분석 내용은 포함하지 마세요
- 예: "어떤 약의 일정을 삭제하고 싶으신지 약 이름을 더 구체적으로 말씀해주시겠어요?"

중요사항:
- selected_routine_indices는 0-based index입니다
- 매칭되는 일정이 없으면 빈 배열 []을 반환하세요
- 이전 대화에서 언급된 내용도 고려하세요
- 약 이름은 부분 매칭도 허용하되 명확성을 고려하세요

현재 복용 일정 목록:
{routine_list}

이전 대화 내역:
{chat_history}

사용자 메시지: {user_message}
"""


async def delete_routine_select(state: AgentState) -> AgentState:
    """
    사용자가 선택한 복용 일정을 AI로 분석하고 바로 삭제 처리
    """
    logger.info("execute delete routine select node")
    try:
        user_message = state.get("current_message", "").strip()
        current_routines = state.get("response_data", [])
        chat_history = state.get("messages", "")

        logger.info(f"chat_history: {chat_history}")

        if not current_routines:
            state["final_response"] = "삭제할 복용 일정 목록이 없습니다. 다시 조회해주세요."
            state["direction"] = "save_conversation"
            return state

        # 1. 현재 복용 일정을 텍스트로 변환
        routine_list_text = format_routines_for_ai(current_routines)
        logger.info("routine list text: {}".format(routine_list_text))

        # 3. AI를 사용하여 사용자 의도 분석
        messages = [
            {"role": "system", "content": routine_selection_prompt.format(
                routine_list=routine_list_text,
                chat_history=chat_history,
                user_message=user_message
            )},
            {"role": "user", "content": user_message}
        ]
        ai_response = await gpt_mini.ainvoke(messages)
        analysis_result = parse_ai_response(ai_response.content)
        logger.info(f"AI 분석 결과: {analysis_result}")

        # 4. 신뢰도 확인
        if analysis_result["confidence"] != "high":
            clarification_msg = analysis_result.get("clarification_message",
                                                    "삭제할 일정을 더 명확하게 지정해주세요. 번호(예: 1번), 약 이름(예: 에소졸정), 또는 날짜(예: 5/29)로 말씀해주세요.")

            state["final_response"] = clarification_msg
            state["client_action"] = "DELETE_ROUTINE_SELECT"
            state["direction"] = "save_conversation"
            return state

        # 5. 선택된 일정이 없는 경우
        selected_indices = analysis_result.get("selected_routine_indices", [])
        if not selected_indices:
            state["final_response"] = "선택하신 조건에 해당하는 복용 일정을 찾을 수 없습니다. 다시 확인해주세요."
            state["client_action"] = "DELETE_ROUTINE_SELECT"
            state["direction"] = "save_conversation"
            return state

        # 6. 선택된 일정들 추출
        selected_routines = []
        for idx in selected_indices:
            if 0 <= idx < len(current_routines):
                routine = current_routines[idx]
                selected_routines.append({
                    "routine_group_id": routine["routine_group_id"],
                    "medicine_name": routine.get("nickname", routine.get("medicine_name", "")),
                    "start_date": routine.get("routine_start_date", ""),
                    "end_date": routine.get("routine_end_date", "")
                })

        # 7. 실제 삭제 수행
        deleted_routines = []
        for routine in selected_routines:
            try:
                await delete_routine_group(jwt_token=state["jwt_token"], routine_group_id=routine["routine_group_id"])
                deleted_routines.append(routine)
                logger.info(f"복용 일정 삭제 완료: {routine['routine_group_id']}")
            except Exception as e:
                logger.error(f"복용 일정 삭제 실패: {routine['routine_group_id']}, {e}")

        # 8. 삭제 완료 메시지 생성
        if deleted_routines:
            success_message = "다음 복용 일정을 삭제하였습니다:\n\n"
            for routine in deleted_routines:
                start_date = format_date_short(routine["start_date"])
                end_date = format_date_short(routine["end_date"])
                success_message += f"• {start_date}~{end_date} {routine['medicine_name']}\n"

            state["final_response"] = success_message
        else:
            state["final_response"] = "복용 일정 삭제 중 오류가 발생했습니다. 다시 시도해주세요."

        state["direction"] = "save_conversation"
        state["client_action"] = None
        state["response_data"] = None
        return state

    except Exception as e:
        logger.error(f"복용 일정 선택 삭제 중 오류 발생: {e}")
        state["final_response"] = "복용 일정 삭제 중 오류가 발생했습니다. 다시 시도해주세요."
        state["direction"] = "save_conversation"

        import traceback
        logger.error(f"스택 트레이스: {traceback.format_exc()}")
        return state


def format_routines_for_ai(routines: list) -> str:
    """AI 분석을 위해 복용 일정을 텍스트로 포맷팅"""
    formatted_text = ""
    for idx, routine in enumerate(routines):
        start_date = format_date_short(routine.get("routine_start_date", ""))
        end_date = format_date_short(routine.get("routine_end_date", ""))
        medicine_name = routine.get("nickname", routine.get("medicine_name", ""))

        formatted_text += f"{idx}: {start_date}~{end_date} {medicine_name}\n"

    return formatted_text


def format_chat_history(messages: list) -> str:
    """대화 내역을 텍스트로 포맷팅"""
    if not messages:
        return "이전 대화 내역 없음"

    history_text = ""
    for msg in messages[-10:]:  # 최근 10개 메시지만
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role and content:
            history_text += f"{role}: {content}\n"

    return history_text or "이전 대화 내역 없음"


def parse_ai_response(response_content: str) -> dict:
    """AI 응답을 파싱하여 구조화된 데이터로 변환"""
    try:
        # 1. 마크다운 코드 블록 처리
        if "```json" in response_content:
            json_start = response_content.find("```json") + 7
            json_end = response_content.find("```", json_start)
            if json_end != -1:
                json_str = response_content[json_start:json_end].strip()
            else:
                json_str = response_content[json_start:].strip()
        elif "```" in response_content:
            # 일반 코드 블록
            json_start = response_content.find("```") + 3
            json_end = response_content.find("```", json_start)
            if json_end != -1:
                json_str = response_content[json_start:json_end].strip()
            else:
                json_str = response_content[json_start:].strip()
        else:
            # 2. 중괄호로 둘러싸인 JSON 추출
            json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                raise ValueError("JSON 형식을 찾을 수 없습니다")

        # 3. JSON 파싱
        parsed_data = json.loads(json_str)

        # 4. 필수 필드 검증 및 기본값 설정
        result = {
            "selected_routine_indices": parsed_data.get("selected_routine_indices", []),
            "confidence": parsed_data.get("confidence", "low"),
            "reasoning": parsed_data.get("reasoning", "분석 결과를 파싱할 수 없습니다"),
            "matched_criteria": parsed_data.get("matched_criteria", {
                "method": "unknown",
                "details": "분석 기준을 파악할 수 없습니다"
            }),
            "clarification_message": parsed_data.get("clarification_message",
                                                     "삭제할 일정을 더 명확하게 지정해주세요. 번호나 약 이름으로 말씀해주시겠어요?")
        }

        # 5. 데이터 타입 검증
        if not isinstance(result["selected_routine_indices"], list):
            result["selected_routine_indices"] = []

        if result["confidence"] not in ["high", "medium", "low"]:
            result["confidence"] = "low"

        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 오류: {e}")
        logger.error(f"문제가 된 JSON: {json_str if 'json_str' in locals() else 'N/A'}")
    except Exception as e:
        logger.error(f"AI 응답 파싱 오류: {e}")
        logger.error(f"원본 응답: {response_content}")

    # 파싱 실패 시 기본값 반환
    return {
        "selected_routine_indices": [],
        "confidence": "low",
        "reasoning": "AI 응답을 분석할 수 없습니다",
        "matched_criteria": {
            "method": "error",
            "details": "응답 파싱 실패"
        },
        "clarification_message": "죄송합니다. 다시 한 번 삭제하고 싶은 일정을 말씀해주시겠어요?"
    }


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


def delete_routine_select_direction_router(state: AgentState) -> str:
    return "save_conversation"