import copy
import json
import os
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List
import io

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
    처방전 데이터를 음성 안내용 텍스트로 요약

    Args:
        prescriptions: 처방전 정보 목록

    Returns:
        str: 음성 안내용 텍스트
    """
    if not prescriptions:
        return "처방전 분석 결과, 등록된 약품이 없습니다. 다른 처방전을 시도하거나 수동으로 등록해 주세요."

    # 약품 수 계산
    med_count = len(prescriptions)

    # 처방 일수 (모든 약이 같은 기간이라고 가정)
    days = prescriptions[0].get("total_days", 0) if prescriptions else 0

    # 공통 복용 시간 파악
    all_schedules = set()
    recommended_schedules = set()

    for prescription in prescriptions:
        for schedule in prescription.get("user_schedules", []):
            schedule_name = schedule.get("name", "")
            all_schedules.add(schedule_name)

            if schedule.get("recommended", False):
                recommended_schedules.add(schedule_name)

    # 주요 약품 정보 추출 (최대 2개까지만 상세히 언급)
    detailed_meds = []
    for i, med in enumerate(prescriptions[:2]):
        med_name = med.get("medicine_name", "")
        # 약품명이 너무 길면 앞부분만 사용
        if len(med_name) > 30:
            # 첫 번째 괄호 위치 찾기
            paren_idx = med_name.find('(')
            if paren_idx > 0:
                med_name = med_name[:paren_idx].strip()
            else:
                med_name = med_name[:30].strip()

        class_name = med.get("class_name", "")
        dose = med.get("dose", 1)

        # 약품 타입 (일반/전문)
        med_type = "일반의약품" if med.get("etc_otc_name") == "일반의약품" else "전문의약품"

        detailed_meds.append(f"{med_name} {dose}정({class_name}, {med_type})")

    # 나머지 약품이 있으면 개수만 언급
    remaining = med_count - len(detailed_meds)
    if remaining > 0:
        detailed_meds.append(f"그 외 {remaining}개 약품")

    # 음성 메시지 구성
    lines = []
    lines.append(f"처방전 분석이 완료되었습니다. 총 {med_count}개 약품이 {days}일분 처방되었습니다.")

    # 약품 정보
    lines.append("처방된 약품은 " + ", ".join(detailed_meds) + "입니다.")

    # 복용 시간 안내
    if recommended_schedules:
        schedule_text = ", ".join(sorted(recommended_schedules))
        lines.append(f"권장 복용 시간은 {schedule_text}입니다.")

    # 마무리 문구
    lines.append("복약 일정이 등록되었으니, 시간에 맞춰 복용해 주세요.")
    lines.append("상세한 내용은 복약 관리 페이지에서 확인하실 수 있습니다.")

    return " ".join(lines)


async def register_routine_list(
        jwt_token: str,
        routines_data: List[Dict[str, Any]],
)-> str:
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

    url = f"{medeasy_api_url}/routine/list"
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    # 요청 데이터 로깅 (민감 정보 제외)
    sanitized_data = copy.deepcopy(routines_data)
    logger.info(f"복약 일정 등록 요청 데이터: {json.dumps(sanitized_data, ensure_ascii=False)}")

    # 요청 데이터 검증
    if not isinstance(routines_data, list):
        logger.error("routines_data는 리스트 형식이어야 합니다.")
        return "복약 일정 등록에 실패하였습니다. 데이터 형식이 올바르지 않습니다."

    if len(routines_data) == 0:
        logger.error("등록할 복약 일정이 없습니다.")
        return "등록할 복약 일정이 없습니다."


    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=routines_data) as response:
                response_text = await response.text()

                logger.info(f"복약 일정 등록 API 응답 상태 코드: {response.status}")
                logger.info(f"복약 일정 등록 API 응답 내용: {response_text}")

                if response.status != 200:
                    return "복약 일정 등록에 실패하였습니다. 나중에 다시 시도해주세요."

                try:
                    return "복약 일정을 등록하였습니다!"

                except json.JSONDecodeError as e:
                    logger.error(f"복약 일정 등록 중 오류 발생: {str(e)}", exc_info=True)
                    return "복약 일정 등록에 실패하였습니다. 나중에 다시 시도해주세요."

    except aiohttp.ClientError as e:
        logger.error(f"복약 일정 등록 중 오류 발생: {str(e)}", exc_info=True)
        return "네트워크가 불안정합니다. 나중에 다시 시도해주세요."

    except Exception as e:
        logger.error(f"복약 일정 등록 중 오류 발생: {str(e)}", exc_info=True)
        return "예상할 수 없는 문제가 발생하였습니다.. 나중에 다시 시도해주세요."

