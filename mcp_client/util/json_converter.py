def make_standard_response(
    result_code: int,
    result_message: str,
    text_message: str = None,
    audio_base64: str = None,
    audio_format: str = None,
    action: str = None,
    data = None
) -> dict:
    return {
        "result_code": result_code,
        "result_message": result_message,
        "text_message": text_message,
        "audio_base64": audio_base64,
        "audio_format": audio_format,
        "action": action,
        "data": data
    }
