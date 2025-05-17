import os

from mcp_client.service.routine_service import get_medication_notifications


async def hello_web_socket_connection(
        jwt_token: str
) -> str:
    """웹 소켓 연결 성공시 인사말"""
    notification = await get_medication_notifications(jwt_token)

    return f"안녕하세요. 복약 비서 메디씨입니다. {notification} 도움이 필요하시면 말씀해주세요."
