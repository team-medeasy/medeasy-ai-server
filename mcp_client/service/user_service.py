import os
import logging

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

medeasy_api_url = os.getenv('MEDEASY_API_URL', "https://api.medeasy.dev")

async def get_user_info(jwt_token: str):
    url = f"{medeasy_api_url}/user"
    headers = {"Authorization": f"Bearer {jwt_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"스케줄 조회 실패: {resp.text}")
        user = resp.json().get("body", [])

        return user