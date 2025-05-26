import base64
from datetime import date
import logging
from typing import List, Dict, Any

from fastapi import HTTPException

from mcp_client.agent.agent_send_message import agent_send_message
from mcp_client.agent.medeasy_agent import AgentState
from mcp_client.service.medicine_service import process_pill_image, format_medicine_search_results
from mcp_client.service.routine_service import get_routine_list, register_routine_by_prescription, \
    format_prescription_for_voice

logger = logging.getLogger(__name__)

async def check_server_actions(state: AgentState) -> AgentState:
    """
    서버에서 바로 다이렉트로 기능 수행할 점이 있는지 ai 도구 선택이 필요 없는 경우
    """
    logger.info("execute check server actions node")
    server_action: str=state.get("server_action")
    jwt_token: str = state.get("jwt_token")
    data = state.get("data")  # 이미지 바이트 또는 기타 데이터

    try:
        if server_action == "REGISTER_ROUTINE_REQUEST":
            state['direction'] = 'register_routine'

        # 오늘 복용 일정 확인
        elif server_action == "GET_ROUTINE_LIST_TODAY":
            state['direction'] = 'get_routine_list_today'

        # 처방전 촬영 버튼
        elif server_action == "PRESCRIPTION_ROUTINE_REGISTER_REQUEST":
            state['final_response'] = "처방전 사진을 업로드하거나 카메라로 촬영해 주세요!"
            state['client_action'] = "CAPTURE_PRESCRIPTION"

        # 사진 업로드
        elif server_action == "UPLOAD_PRESCRIPTION_PHOTO":
            if not data:
                raise ValueError("업로드된 이미지 데이터가 없습니다.")

            message = "업로드된 처방전을 분석 중입니다. 잠시만 기다려 주세요."
            await agent_send_message(state=state, message=message)

            # 이미지 데이터 처리 (바이트 배열 또는 base64 인코딩 문자열 지원)
            image_data = data
            if isinstance(data, str):
                # base64 인코딩된 문자열인 경우 디코딩
                try:
                    image_data = base64.b64decode(data)
                except Exception as e:
                    logger.warning(f"Base64 디코딩 실패, 원본 데이터 사용: {str(e)}")

            prescription_response: List[Dict[str, Any]] = await register_routine_by_prescription(jwt_token, image_data)

            # 응답 포맷팅 및 상태 저장
            final_response = format_prescription_for_voice(prescription_response)
            state["final_response"] = final_response
            state['response_data'] = prescription_response
            state['client_action'] = "REVIEW_PRESCRIPTION_REGISTER_RESPONSE"

        # 루틴 리스트 등록
        elif server_action == "REGISTER_ROUTINE_LIST":
            message = "복약 일정 등록을 진행하고 있습니다. 잠시만 기다려주세요."
            await agent_send_message(state=state, message=message)

            state['client_action'] = None
            state['direction'] = "register_routine_list"

        elif server_action == "CAPTURE_PILLS_PHOTO_REQUEST":
            state['final_response'] = "의약품 사진을 등록하거나 카메라로 촬영해 주세요!"
            state['client_action'] = "CAPTURE_PILLS_PHOTO"

        # 사진 업로드
        elif server_action == "UPLOAD_PILLS_PHOTO":
            if not data:
                raise ValueError("업로드된 이미지 데이터가 없습니다.")

            message = "업로드된 의약품 사진을 분석 중입니다. 잠시만 기다려 주세요."
            await agent_send_message(state=state, message=message)

            # 이미지 데이터 처리 (바이트 배열 또는 base64 인코딩 문자열 지원)
            image_data = data
            if isinstance(data, str):
                # base64 인코딩된 문자열인 경우 디코딩
                try:
                    image_data = base64.b64decode(data)
                    logger.info(f"Base64 디코딩 완료, 데이터 크기: {len(image_data)} 바이트")
                except Exception as e:
                    logger.warning(f"Base64 디코딩 실패, 원본 데이터 사용: {str(e)}")

            pills_data, error_message = await process_pill_image(image_data)

            # 응답 포맷팅 및 상태 저장
            final_response = format_medicine_search_results(pills_data)
            state["final_response"] = final_response
            state['response_data'] = pills_data
            state['client_action'] = "REVIEW_PILLS_PHOTO_SEARCH_RESPONSE"


    except HTTPException as e:
        logger.error(f"서버 액션 처리 중 HTTP 오류: {e.detail}")
        state["error"] = f"서버 요청 실패: {e.detail}"
    except Exception as e:
        logger.exception(f"서버 액션 처리 중 예외 발생: {str(e)}")
        state["error"] = f"서버 액션 처리 오류: {str(e)}"

    return state


def check_server_actions_direction_router(state: AgentState) -> str:
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
    elif direction == "register_routine_list":
        return "register_routine_list"
    elif direction == "register_routine":
        return "register_routine"
    elif direction == "get_routine_list_today":
        return "get_routine_list_today"
    else:
        # 기본 방향 (direction이 없거나 알 수 없는 값인 경우)
        return "save_conversation"