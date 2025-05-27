from fastapi import HTTPException
import aiohttp
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
load_dotenv()

# Clova Voice API 설정
CLOVA_VOICE_URL = "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"
CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")


async def convert_text_to_speech(text: str, speaker: str = "nara_call", speed: int = 0, pitch: int = 0):
    """
    Clova Voice를 사용하여 텍스트를 음성으로 변환

    Args:
        text: 변환할 텍스트
        speaker: 음성 화자 (nara, clara, matt, shinji, meimei, liangliang, jose, carmen)
        speed: 말하기 속도 (-5 ~ 5, 기본값 0)
        pitch: 음성 피치 (-5 ~ 5, 기본값 0)
    """
    try:
        logger.info(f"Converting text to speech: {text[:50]}...")

        # 요청 헤더
        headers = {
            "X-NCP-APIGW-API-KEY-ID": CLIENT_ID,
            "X-NCP-APIGW-API-KEY": CLIENT_SECRET,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        # 요청 데이터
        data = {
            "speaker": speaker,
            "volume": "0",  # 볼륨 (-5 ~ 5, 기본값 0)
            "speed": str(speed),
            "pitch": str(pitch),
            "format": "mp3",  # mp3 또는 wav
            "text": text
        }

        # 비동기 HTTP 요청
        async with aiohttp.ClientSession() as session:
            async with session.post(CLOVA_VOICE_URL, headers=headers, data=data) as response:
                if response.status == 200:
                    audio_content = await response.read()
                    logger.info("Successfully converted text to speech")
                    return audio_content
                else:
                    error_text = await response.text()
                    logger.error(f"Clova Voice API Error: {response.status} - {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Clova Voice API Error: {error_text}"
                    )

    except aiohttp.ClientError as e:
        logger.error(f"HTTP Client Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"HTTP request failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Clova Voice TTS Error: {str(e)}")


# 사용 가능한 화자 목록
AVAILABLE_SPEAKERS = {
    "nara": "한국어 여성 음성 (밝은 톤)",
    "clara": "한국어 여성 음성 (차분한 톤)",
    "matt": "영어 남성 음성",
    "shinji": "일본어 남성 음성",
    "meimei": "중국어 여성 음성",
    "liangliang": "중국어 남성 음성",
    "jose": "스페인어 남성 음성",
    "carmen": "스페인어 여성 음성"
}


def get_available_speakers():
    """사용 가능한 화자 목록 반환"""
    return AVAILABLE_SPEAKERS