import os
import logging
from datetime import date

import httpx
import pytz
from fastapi import HTTPException

kst = pytz.timezone('Asia/Seoul')
logger = logging.getLogger(__name__)

async def get_routine_list(
        start_date: date,
        end_date: date,
        jwt_token: str,
) -> str:
    """
        사용자의 루틴 목록을 조회하는 함수

        Args:
            jwt_token: 사용자 인증 토큰
            start_date: 조회 시작 날짜 (기본값: 오늘)
            end_date: 조회 종료 날짜 (기본값: 오늘)

        Returns:
           완전 정리된 문자열
        """

    # 기본값으로 오늘 날짜 사용
    if start_date is None:
        start_date = date.today()
    if end_date is None:
        end_date = date.today()

    api_url = f"{os.getenv('MCP_SERVER_HOST')}/routine"
    params = {
        "jwt_token": jwt_token,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(api_url, params=params, timeout=10.0)
            response.raise_for_status()  # 4XX, 5XX 에러 발생 시 예외 발생

            result = response.json()

            return result["message"]

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            detail = e.response.text

            error_message = {
                400: "잘못된 요청입니다. 입력 값을 확인해주세요.",
                401: "인증이 필요합니다. 로그인 후 다시 시도해주세요.",
                403: "권한이 없습니다. 인증 토큰을 확인해주세요.",
                404: "요청하신 루틴 정보를 찾을 수 없습니다.",
                500: "서버 내부 오류가 발생했습니다."
            }.get(status, f"알 수 없는 오류 발생: {detail}")

            logger.error(f"루틴 조회 실패: {error_message} (상태 코드: {status})")
            raise HTTPException(status_code=status, detail=error_message)

        except httpx.RequestError as e:
            error_message = f"외부 API 서버와의 연결 실패: {str(e)}"
            logger.error(f"루틴 조회 실패: {error_message}")
            raise HTTPException(status_code=502, detail=error_message)

        except Exception as e:
            error_message = f"루틴 조회 중 예상치 못한 오류 발생: {str(e)}"
            logger.error(error_message)
            raise HTTPException(status_code=500, detail=error_message)

