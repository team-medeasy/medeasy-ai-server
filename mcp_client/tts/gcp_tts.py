import base64

from fastapi import HTTPException
from google.cloud import texttospeech, texttospeech_v1beta1
from google.oauth2 import service_account
import os
from dotenv import load_dotenv

load_dotenv()

credentials_path = os.getenv("GCP_TTS_CREDENTIALS_PATH")
credentials = service_account.Credentials.from_service_account_file(credentials_path)
client = texttospeech_v1beta1.TextToSpeechAsyncClient(credentials=credentials)


async def convert_text_to_speech(request: str):
    try:

        # dict 형태로 요청 생성
        request_dict = {
            "input": {
                "text": request
            },
            "voice": {
                "language_code": "ko-KR",
                "ssml_gender": texttospeech_v1beta1.SsmlVoiceGender.MALE
            },
            "audio_config": {
                "audio_encoding": texttospeech_v1beta1.AudioEncoding.MP3
            }
        }

        response = await client.synthesize_speech(request=request_dict)
        return response.audio_content  # binary 반환

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GCP TTS REQUEST ERROR: {str(e)}")