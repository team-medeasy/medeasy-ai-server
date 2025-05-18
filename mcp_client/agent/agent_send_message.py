import base64

from starlette.websockets import WebSocket

from mcp_client.agent.medeasy_agent import AgentState
from mcp_client.tts import convert_text_to_speech
from mcp_client.util.json_converter import make_standard_response

async def agent_send_message(
        state: AgentState, message: str
):
    mp3_bytes = await convert_text_to_speech(message)
    mp3_base64 = base64.b64encode(mp3_bytes).decode("utf-8")
    await state['websocket'].send_json(make_standard_response(
        result_code=200,
        result_message="요청을 성공적으로 처리하였습니다.",
        text_message=message,
        audio_base64=mp3_base64,
        audio_format="mp3",
        client_action=None,
        data=None
    ))