from fastapi import HTTPException
from google.cloud import texttospeech, texttospeech_v1beta1
from google.oauth2 import service_account
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
load_dotenv()

credentials_path = os.getenv("GCP_TTS_CREDENTIALS_PATH")
credentials = service_account.Credentials.from_service_account_file(credentials_path)
client = texttospeech_v1beta1.TextToSpeechAsyncClient(credentials=credentials)

async def convert_text_to_speech(request: str):
    try:
        logger.info(f"Converting {request}")
        # dict 형태로 요청 생성
        request_dict = {
            "input": {"text": request},
            "voice": {
                "language_code": "ko-KR",
                "name": "ko-KR-Neural2-C"  # 이 부분을 Neural2 음성 이름으로 변경합니다.
            },
            "audio_config": {
                "audio_encoding": texttospeech_v1beta1.AudioEncoding.MP3,
                "speaking_rate": 1.0,
                # 말하기 속도 (0.25 ~ 4.0, 기본값 1.0)        "pitch": 2.0,  # 음성 피치 (-20.0 ~ 20.0, 기본값 0.0)        # "volume_gain_db": 0.0, # 볼륨 게인 (-96.0 ~ 16.0 dB, 기본값 0.0)        "sample_rate_hertz": 24000, # 필요시 샘플링 속도 지정 8000, 16000, 24000, 48000        "effects_profile_id": ["handset-class-device"]
            }
        }

        response = await client.synthesize_speech(request=request_dict)
        logger.info("finished converting text")
        return response.audio_content

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GCP TTS REQUEST ERROR: {str(e)}")