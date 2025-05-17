import os

import httpx

from mcp_client.service.routine_service import get_medication_notifications, medeasy_api_url

medeasy_api_url = os.getenv('MEDEASY_API_URL')

async def hello_web_socket_connection(
        jwt_token: str
) -> str:
    """웹 소켓 연결 성공시 인사말"""
    name = await get_user_name(jwt_token)
    notification = await get_medication_notifications(jwt_token)

    return f"안녕하세요 {name}님! 복약 비서 메디씨입니다. {notification} 도움이 필요하시면 말씀해주세요."

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