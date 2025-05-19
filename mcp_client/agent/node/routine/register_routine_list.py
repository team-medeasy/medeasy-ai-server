import copy
import json
from typing import List, Dict, Any
import os
import logging

import aiohttp

from mcp_client.agent.agent_types import AgentState

logger = logging.getLogger(__name__)
medeasy_api_url = os.getenv('MEDEASY_API_URL')

async def register_routine_list(
        state : AgentState,
)-> AgentState:
    """
    복약 일정 목록을 서버에 등록하는 함수

    Args:
        jwt_token: 사용자 JWT 토큰
        routines_data: 복약 일정 데이터 목록. 각 항목은 다음 형식을 따름:
            {
                "medicine_id": str,
                "nickname": str,
                "dose": int,
                "total_quantity": int,
                "user_schedule_ids": List[int],
                "routine_start_date": str,
                "start_user_schedule_id": int,
                "interval_days": int
            }

    Returns:
        Dict[str, Any]: 서버 응답 데이터
    """
    jwt_token = state["jwt_token"]
    routines_data = state["data"]

    url = f"{medeasy_api_url}/routine/list"
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    # 요청 데이터 로깅 (민감 정보 제외)
    sanitized_data = copy.deepcopy(routines_data)
    logger.info(f"복약 일정 등록 요청 데이터: {json.dumps(sanitized_data, ensure_ascii=False)}")

    # 요청 데이터 검증
    if not isinstance(routines_data, list):
        logger.error("routines_data는 리스트 형식이어야 합니다.")
        state["final_response"] = "복약 일정 등록에 실패하였습니다. 데이터 형식이 올바르지 않습니다."

    if len(routines_data) == 0:
        logger.error("등록할 복약 일정이 없습니다.")
        state["final_response"] = "등록할 복약 일정이 없습니다."

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=routines_data) as response:
                response_text = await response.text()

                logger.info(f"복약 일정 등록 API 응답 상태 코드: {response.status}")
                logger.info(f"복약 일정 등록 API 응답 내용: {response_text}")

                if response.status != 200:
                    state["final_response"] = "복약 일정 등록에 실패하였습니다. 나중에 다시 시도해주세요."

                try:
                    state["final_response"] = "복약 일정을 등록하였습니다!"

                except json.JSONDecodeError as e:
                    logger.error(f"복약 일정 등록 중 오류 발생: {str(e)}", exc_info=True)
                    state["final_response"] = "복약 일정 등록에 실패하였습니다. 나중에 다시 시도해주세요."

    except aiohttp.ClientError as e:
        logger.error(f"복약 일정 등록 중 오류 발생: {str(e)}", exc_info=True)
        state["final_response"] = "네트워크가 불안정합니다. 나중에 다시 시도해주세요."

    except Exception as e:
        logger.error(f"복약 일정 등록 중 오류 발생: {str(e)}", exc_info=True)
        state["final_response"] = "예상할 수 없는 문제가 발생하였습니다.. 나중에 다시 시도해주세요."

    return state