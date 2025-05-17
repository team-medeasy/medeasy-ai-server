from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi import APIRouter
import base64
import logging

from backend.auth.jwt_token_helper import get_user_id_from_token
from mcp_client.client import process_user_message
from mcp_client.tts import convert_text_to_speech
from mcp_client.util.json_converter import make_standard_response

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/message/voice")
async def websocket_message_voice(websocket: WebSocket):
    token = websocket.query_params.get("jwt_token")
    jwt_token=token.replace("Bearer ", "")
    logger.info(f"jwt token: {jwt_token}")

    if not token or not token.startswith("Bearer "):
        await websocket.close(code=4403)  # 4403: Custom unauthorized code
        return

    try:
        user_id = get_user_id_from_token(jwt_token)
    except Exception:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    try:
        while True:
            # 1. 메시지 수신 (JSON 형식)
            client_message = await websocket.receive_json()
            message = client_message.get("message")
            action = client_message.get("action")
            data = client_message.get("data")

            logger.info(f"WebSocket message from user {user_id}")
            user_message = f"""
                message_content: {message}
                jwt_token: {jwt_token} 
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
                text_message = "요청 처리 중 오류가 발생하였습니다.."
                audio_file = await convert_text_to_speech(text_message)
                audio_base64 = base64.b64encode(audio_file).decode("utf-8")

                await websocket.send_json(make_standard_response(
                    result_code=500,
                    result_message="메시지 처리 중 오류 발생",
                    text_message=text_message,
                    audio_base64=audio_base64,
                    audio_format="mp3",
                ))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
