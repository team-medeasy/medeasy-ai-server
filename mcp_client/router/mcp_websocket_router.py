from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi import APIRouter
import base64
import logging

from backend.auth.jwt_token_helper import get_user_id_from_token
from mcp_client.client import process_user_message
from mcp_client.tts import convert_text_to_speech

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/message/voice")
async def websocket_message_voice(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # 1. 메시지 수신 (JSON 형식)
            client_message = await websocket.receive_json()
            message = client_message.get("message")
            authorization = client_message.get("authorization")
            action = client_message.get("action")
            data = client_message.get("data")

            # 2. 토큰 확인 및 사용자 인증
            if not authorization or not authorization.startswith("Bearer "):
                await websocket.send_json({
                    "error": "Invalid or missing Authorization token"
                })
                continue

            token = authorization.replace("Bearer ", "")
            try:
                user_id = get_user_id_from_token(token)
            except Exception as e:
                await websocket.send_json({
                    "error": f"사용자 인증 중 오류가 발생하였습니다."
                })
                continue

            logger.info(f"WebSocket message from user {user_id}")

            user_message = f"""
                message_content: {message}
                jwt_token: {token} 
            """

            try:
                # 3. 메시지 처리 및 응답 생성
                response, action = await process_user_message(user_message=user_message, user_id=int(user_id))
                mp3_bytes = await convert_text_to_speech(response)
                mp3_base64 = base64.b64encode(mp3_bytes).decode("utf-8")

                # 4. 응답 전송
                await websocket.send_json({
                    "text_message": response,
                    "audio_base64": mp3_base64,
                    "audio_format": "mp3",
                    "action": action,
                    "data" : None
                })
            except Exception as e:
                await websocket.send_json({
                    "error": f"Error processing message: {str(e)}"
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
