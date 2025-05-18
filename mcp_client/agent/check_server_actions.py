import base64
from datetime import date
import logging
from typing import List, Dict, Any

from fastapi import HTTPException

from mcp_client.agent.agent_send_message import agent_send_message
from mcp_client.agent.agent_types import init_state
from mcp_client.agent.medeasy_agent import AgentState
from mcp_client.service.routine_service import get_routine_list, register_routine_by_prescription, \
    format_prescription_for_voice, register_routine_list

logger = logging.getLogger(__name__)

async def check_server_actions(state: AgentState) -> AgentState:
    """
    서버에서 바로 다이렉트로 기능 수행할 점이 있는지 ai 도구 선택이 필요 없는 경우
    """
    server_action: str=state.get("server_action")
    jwt_token: str = state.get("jwt_token")
    data = state.get("data")  # 이미지 바이트 또는 기타 데이터

    try:
        if server_action == "GET_ROUTINE_LIST_TODAY":
            today = date.today()
            routine_result:str = await get_routine_list(today, today, jwt_token)
            state["final_response"] = routine_result

        elif server_action == "PRESCRIPTION_ROUTINE_REGISTER_REQUEST":
            state['final_response'] = "처방전 사진을 업로드하거나 카메라로 촬영해 주세요!"
            state['client_action'] = "CAPTURE_PRESCRIPTION"

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

        elif server_action == "REGISTER_ROUTINE_LIST":
            message = "복약 일정 등록을 진행하고 있습니다. 잠시만 기다려주세요."
            await agent_send_message(state=state, message=message)

            init_state(state=state)
            state['final_response'] = await register_routine_list(jwt_token, data)


    except HTTPException as e:
        logger.error(f"서버 액션 처리 중 HTTP 오류: {e.detail}")
        state["error"] = f"서버 요청 실패: {e.detail}"
    except Exception as e:
        logger.exception(f"서버 액션 처리 중 예외 발생: {str(e)}")
        state["error"] = f"서버 액션 처리 오류: {str(e)}"

    return state