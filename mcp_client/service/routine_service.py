import os
import logging
from datetime import date, datetime, timedelta

import httpx
import pytz
from fastapi import HTTPException

kst = pytz.timezone('Asia/Seoul')
logger = logging.getLogger(__name__)

medeasy_api_url = os.getenv('MEDEASY_API_URL')

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


async def get_medication_notifications(jwt_token: str) -> str:
    """
    사용자의 복약 알림을 조회합니다:
    1. 시간이 지났지만 아직 복용하지 않은 약
    2. 30분 이내에 복용 예정인 약

    Args:
        jwt_token: 사용자 JWT 토큰

    Returns:
        str: 알림 메시지 (복용하지 않은 약과 예정된 약에 대한 알림)
    """
    url = f"{medeasy_api_url}/routine"
    today = datetime.now(kst).date()

    params = {
        "start_date": today.isoformat(),
        "end_date": today.isoformat()
    }
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"알림 조회 실패: {resp.text}")

    now = datetime.now(kst).time()
    now_dt = datetime.combine(today, now)
    soon_delta = timedelta(minutes=30)

    notifications = []

    data = resp.json()["body"]

    for day in data:  # 날짜 단위 루틴
        routine_date = datetime.strptime(day["take_date"], "%Y-%m-%d").date()

        for schedule in day.get("user_schedule_dtos", []):
            take_time_str = schedule.get("take_time")
            if not take_time_str:
                continue

            try:
                time_obj = datetime.strptime(take_time_str, "%H:%M:%S").time()
            except ValueError:
                continue

            routine_date_time = datetime.combine(routine_date, time_obj)
            schedule_name = schedule.get('name', '')

            # 복용하지 않은 약 알림 (시간이 지났는데 안 먹음)
            if now_dt > routine_date_time:
                not_taken = [
                    r for r in schedule.get("routine_dtos", [])
                    if not r.get("is_taken", False)
                ]
                if not_taken:
                    meds = ", ".join(r.get("nickname", "") for r in not_taken)
                    notifications.append(f"아직 {schedule_name}에 {meds}을(를) 복용하지 않으셨습니다.")

            # 곧 복용 예정 알림 (30분 이내)
            schedule_dt = datetime.combine(today, time_obj)
            if now_dt < schedule_dt <= now_dt + soon_delta:
                medicines = ", ".join(
                    f"{routine.get('nickname', '')}"
                    for routine in schedule.get("routine_dtos", [])
                )
                notifications.append(
                    f"잠시 후 {schedule_name} 시간({time_obj.strftime('%H:%M')})에 {medicines}을(를) 복용해야 합니다.")

    if not notifications:
        return "현재 복약을 잘하고 계십니다!"

    return "\n".join(notifications)