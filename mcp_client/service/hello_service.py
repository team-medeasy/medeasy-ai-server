import json
import os

import httpx
from langchain_core.messages import SystemMessage

from mcp_client.client import gpt_nano
from mcp_client.service.routine_service import get_medication_notifications, medeasy_api_url, get_medication_data

medeasy_api_url = os.getenv('MEDEASY_API_URL')

async def hello_web_socket_connection(
        jwt_token: str
) -> str:
    """웹 소켓 연결 성공시 인사말"""
    user_name = await get_user_name(jwt_token)
    # notification = await get_medication_notifications(jwt_token, name)
    medication_data = await get_medication_data(jwt_token, user_name)

    # 3) 프롬프트 생성
    prompt = (
        "아래 JSON을 보고, 사용자에게 보낼 한글 메시지를\n"
        "– 인사말\n"
        "– 아직 복용하지 않은 약 알림\n"
        "– 곧 복용 예정인 약 알림\n"
        "– 맺음말\n"
        "순서대로 예쁘고 자연스럽게 만들어줘:\n\n"
        f"{json.dumps(medication_data, ensure_ascii=False, indent=2)}"
    )
    response = await gpt_nano.agenerate([[SystemMessage(content=prompt)]])
    message = response.generations[0][0].text.strip()

    return message

async def get_user_name(jwt_token: str) -> str:
    """토큰으로 사용자 이름 가져오기"""

    """
        토큰으로 사용자 이름을 조회합니다.

        Args:
            jwt_token: 사용자 JWT 토큰

        Returns:
            str: 사용자 이름
        """
    url = f"{medeasy_api_url}/user"
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code >= 400:
            # 오류 발생 시 빈 문자열 반환 (인사말에서 이름 생략)
            return ""

        # 응답 JSON 파싱
        response_data = resp.json()

        # body 내의 name 필드 추출
        user_name = response_data.get("body", {}).get("name", "")
        return user_name

    except Exception as e:
        # 오류 발생 시 빈 문자열 반환 (인사말에서 이름 생략)
        return ""