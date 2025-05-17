def make_standard_response(
    result_code: int,
    result_message: str,
    text_message: str = None,
    audio_base64: str = None,
    audio_format: str = None,
    client_action: str = None,
    data = None
) -> dict:
    return {
        "result_code": result_code,
        "result_message": result_message,
        "text_message": text_message,
        "audio_base64": audio_base64,
        "audio_format": audio_format,
        "client_action": client_action,
        "data": data
    }
