from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi import APIRouter
import base64
import logging

from backend.auth.jwt_token_helper import get_user_id_from_token
from mcp_client.agent.agent_types import AgentState, init_state
from mcp_client.agent.medeasy_agent import process_user_message
from mcp_client.service.hello_service import hello_web_socket_connection
# from mcp_client.tts import convert_text_to_speech
from mcp_client.tts.clova_tts import convert_text_to_speech
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

    # 연결 성공시 인사말.
    response = await hello_web_socket_connection(jwt_token)
    mp3_bytes = await convert_text_to_speech(user_id=int(user_id), text=response)
    mp3_base64 = base64.b64encode(mp3_bytes).decode("utf-8")

    await websocket.send_json(make_standard_response(
        result_code=200,
        result_message="요청을 성공적으로 처리하였습니다.",
        text_message=response,
        audio_base64=mp3_base64,
        audio_format="mp3",
        client_action=None,
        data=None
    ))

    # 초기 상태 구성
    state: AgentState = {
        "current_message": None,  # 현재 들어온 client 메시지
        "messages": None,
        "client_action": None,
        "server_action": None,
        "data": None,
        "available_tools": [],
        "tool_calls": [],
        "tool_results": [],
        "initial_response": None,
        "error": None,
        "user_id": int(user_id),
        "jwt_token": jwt_token,
        "websocket": websocket,  # 웹소켓 객체 추가
        "final_response": None,
        "response_data": None,
        "temp_data": None,
        "direction" : None
    }

    try:
        while True:
            # 1. 메시지 수신 (JSON 형식)
            client_message = await websocket.receive_json()

            message = client_message.get("message")
            server_action = client_message.get("server_action")
            data = client_message.get("data")

            logger.info(f"WebSocket message from user {user_id}, message: {message}")

            try:
                state["server_action"] = server_action
                state["data"] = data
                state["current_message"] = message

                logger.info(f"사용자 메시지 요청 현재 상태 client_action: {state.get('client_action', '')}")

                response, action, response_data, temp_data = await process_user_message(state=state)
                mp3_bytes = await convert_text_to_speech(user_id=state["user_id"], text=response)
                mp3_base64 = base64.b64encode(mp3_bytes).decode("utf-8")

                # 응답 전송
                await websocket.send_json(make_standard_response(
                    result_code=200,
                    result_message="요청을 성공적으로 처리하였습니다.",
                    text_message=response,
                    audio_base64=mp3_base64,
                    audio_format="mp3",
                    client_action=action,
                    data=response_data
                ))

                state["client_action"] = action
                state["response_data"] = response_data
                state["temp_data"] = temp_data

            except Exception as e:
                text_message = "요청 처리 중 오류가 발생하였습니다.."
                audio_file = await convert_text_to_speech(user_id=state["user_id"], text=text_message)
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
