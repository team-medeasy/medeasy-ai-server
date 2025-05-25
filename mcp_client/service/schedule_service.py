import os
import logging

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

medeasy_api_url = os.getenv('MEDEASY_API_URL', "https://api.medeasy.dev")

async def get_user_schedules_info(
        jwt_token: str
):
    schedule_url = f"{medeasy_api_url}/user/schedule"
    headers = {"Authorization": f"Bearer {jwt_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(schedule_url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"스케줄 조회 실패: {resp.text}")
        schedules = resp.json().get("body", [])

        return schedules
