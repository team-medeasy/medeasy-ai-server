from mcp_client.agent.agent_types import AgentState

async def check_client_actions(state: AgentState) -> AgentState:
    """특수 도구 호출(사진 촬영 등) 확인"""
    if not state.get("tool_calls"):
        return state

    for tool_call in state["tool_calls"]:
        name = tool_call.get('function', {}).get('name')
        if name == 'register_routine_by_prescription':
            state["client_action"] = "CAPTURE_PRESCRIPTION"
            state["final_response"] = "가지고 계신 처방전을 촬영해주세요."
            break
        elif name == 'register_routine_by_pills_photo':
            state["client_action"] = "CAPTURE_PILLS_PHOTO"
            state["final_response"] = "알약 사진을 촬영해주세요."
            break

    return state

def has_capture_request(state: AgentState) -> str:
    """캡처 요청이 있는지 확인"""
    return (
        "capture"
        if state.get("client_action") in ["CAPTURE_PRESCRIPTION", "CAPTURE_PILLS_PHOTO"]
        else "continue"
    )