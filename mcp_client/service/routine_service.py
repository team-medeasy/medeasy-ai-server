import copy
import json
import os
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List
import io
from datetime import datetime, timedelta
from typing import Dict, Any, List
import aiohttp
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

            return result

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


async def get_medication_data(jwt_token: str, user_name: str) -> Dict[str, Any]:
    """
    복약 스케줄의 미복용·예정 데이터를 LLM이 보기 좋게 가공해서 반환합니다.

    Returns:
        {
            "user_name": "김성북",
            "missed": ["아침약", "점심약"],
            "upcoming": [
                {"schedule": "저녁", "time": "18:30", "medicines": ["멀티비타민", "칼슘제"]},
                ...
            ]
        }
    """
    url = f"{medeasy_api_url}/routine"
    today = datetime.now(kst).date()
    params = {"start_date": today.isoformat(), "end_date": today.isoformat()}
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"알림 조회 실패: {resp.text}")

    now_dt = datetime.combine(today, datetime.now(kst).time())
    soon_delta = timedelta(minutes=30)

    missed: List[str] = []
    upcoming: List[Dict[str, Any]] = []

    for day in resp.json()["body"]:
        date = datetime.strptime(day["take_date"], "%Y-%m-%d").date()
        for sched in day.get("user_schedule_dtos", []):
            tstr = sched.get("take_time")
            if not tstr:
                continue
            try:
                t = datetime.strptime(tstr, "%H:%M:%S").time()
            except ValueError:
                continue

            dt = datetime.combine(date, t)
            # 1) 미복용
            if now_dt > dt:
                not_taken = [r for r in sched.get("routine_dtos", []) if not r.get("is_taken", False)]
                if not_taken:
                    missed.append(f"{sched.get('name','')}약")

            # 2) 곧 예정
            dt_today = datetime.combine(today, t)
            if now_dt < dt_today <= now_dt + soon_delta:
                meds = [r.get("nickname","") for r in sched.get("routine_dtos", [])]
                upcoming.append({
                    "schedule": sched.get("name",""),
                    "time": t.strftime("%H:%M"),
                    "medicines": meds
                })

    return {
        "user_name": user_name,
        "missed": missed,
        "upcoming": upcoming
    }


async def get_medication_notifications(jwt_token: str, user_name: str) -> str:
    """
    사용자의 복약 알림을 조회합니다:
    1. 시간이 지났지만 아직 복용하지 않은 약
    2. 30분 이내에 복용 예정인 약

    Args:
        jwt_token: 사용자 JWT 토큰
        user_name: 사용자 이름 (예: "김성북")

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

    now_dt = datetime.combine(today, datetime.now(kst).time())
    soon_delta = timedelta(minutes=30)

    # 아직 복용하지 않은 약을 모아둘 리스트
    missed = []
    # 곧 복용 예정인 약을 모아둘 리스트
    upcoming = []

    data = resp.json()["body"]
    for day in data:
        routine_date = datetime.strptime(day["take_date"], "%Y-%m-%d").date()

        for schedule in day.get("user_schedule_dtos", []):
            take_time_str = schedule.get("take_time")
            if not take_time_str:
                continue

            try:
                time_obj = datetime.strptime(take_time_str, "%H:%M:%S").time()
            except ValueError:
                continue

            routine_dt = datetime.combine(routine_date, time_obj)

            # 1) 시간이 지났지만 아직 안 먹은 약
            if now_dt > routine_dt:
                not_taken = [
                    r for r in schedule.get("routine_dtos", [])
                    if not r.get("is_taken", False)
                ]
                if not_taken:
                    # schedule.get("name") 예: "아침"
                    missed.append(f"{schedule.get('name', '')}약")

            # 2) 30분 이내 곧 복용 예정
            in_30 = datetime.combine(today, time_obj)
            if now_dt < in_30 <= now_dt + soon_delta:
                meds = ", ".join(r.get("nickname", "") for r in schedule.get("routine_dtos", []))
                upcoming.append(f"{schedule.get('name', '')}시간({time_obj.strftime('%H:%M')})에 {meds}")

    # 인사말과 맺음말
    greeting = f"안녕하세요 {user_name}님! 복약 비서 메디씨입니다."
    closing = "도움이 필요하시면 말씀해주세요."

    # 메시지 조립
    if not missed and not upcoming:
        return f"{greeting}\n현재 복약을 잘하고 계십니다!"

    parts = [greeting]
    if missed:
        # ["아침약", "점심약"] → "아직 아침약과 점심약을 복용하지 않았습니다."
        parts.append(
            "아직 " +
            "과 ".join(missed).replace("약과 ", "약과 ") +
            "을 복용하지 않았습니다."
        )
    if upcoming:
        # ["아침시간(08:00)에 씬지록신정", ...]
        parts.append(
            "곧 " +
            "; ".join(upcoming) +
            "에 복용해야 합니다."
        )
    parts.append(closing)

    return "\n".join(parts)



async def register_routine_by_prescription(jwt_token: str, image_data: bytes) -> List[Dict[str, Any]]:
    """
    처방전 이미지를 서버에 업로드하여 복약 일정 등록

    Args:
        jwt_token: 사용자 JWT 토큰
        image_data: 이미지 바이너리 데이터

    Returns:
        Dict[str, Any]: 서버 응답 데이터
    """
    url = f"{medeasy_api_url}/routine/prescription"
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # multipart/form-data 요청 준비
    form_data = aiohttp.FormData()
    form_data.add_field(
        name='image',
        value=io.BytesIO(image_data),
        filename='prescription.jpg',
        content_type='image/jpeg'
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=form_data) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"처방전 등록 실패 (상태 코드: {response.status}): {error_text}")

            result = await response.json()
            logger.info(f"처방전 분석 결과 {result.get('body', {})}")
            return result.get("body", {})


def format_prescription_for_voice(prescriptions: List[Dict[str, Any]]) -> str:
    """
    처방전 데이터를 간결한 음성 안내용 텍스트로 요약

    Args:
        prescriptions: 처방전 정보 목록

    Returns:
        str: 음성 안내용 텍스트
    """
    if not prescriptions:
        return "처방전 분석 결과, 등록된 약품이 없습니다. 다른 처방전을 시도하거나 수동으로 등록해 주세요."

    # 의약품 이름 목록 추출
    med_names = []
    for med in prescriptions:
        med_name = med.get("medicine_name", "")

        # 괄호가 있으면 괄호 앞부분만 사용
        paren_idx = med_name.find('(')
        if paren_idx > 0:
            med_name = med_name[:paren_idx].strip()

        # 약품 이름이 있는 경우에만 추가
        if med_name:
            med_names.append(med_name)

    # 약품 이름 목록을 문자열로 결합
    med_names_str = ", ".join(med_names)

    # 메시지 구성
    lines = [
        "처방전 분석이 완료되었습니다.",
        f"등록할 의약품이 {med_names_str} 맞으신가요?",
        "분석 정보가 정확한지 확인해주시고, 복용 일정 등록을 요청해주세요!"
    ]

    return " ".join(lines)

async def register_single_routine(
        jwt_token: str,
        medicine_id: str,
        nickname: str,
        user_schedule_ids: List[int],
        dose: int,
        total_quantity: int,
):
    api_url = f"{medeasy_api_url}/routine"

    body = {
        "medicine_id": medicine_id,
        "nickname": nickname,
        "dose": dose,
        "total_quantity": total_quantity,
        "interval_days": 1,
        "user_schedule_ids": user_schedule_ids,
    }

    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"루틴 생성 실패: {resp.text}")
        return resp.json()


async def get_medicines_current(
        jwt_token: str,
):
    api_url = f"{medeasy_api_url}/user/medicines/current"

    headers = {"Authorization": f"Bearer {jwt_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(api_url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"현재 복용 중인 루틴 그룹 조회 실패: {resp.text}")
        result = resp.json()
        return result.get("body", {})

async def delete_routine_group(
        jwt_token: str,
        routine_group_id: int,
):
    api_url = f"{medeasy_api_url}/routine/group/routine_group_id/{routine_group_id}"

    headers = {"Authorization": f"Bearer {jwt_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.delete(api_url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"루틴 그룹 삭제 실패: {resp.text}")
        result = resp.json()
        return result.get("body", {})