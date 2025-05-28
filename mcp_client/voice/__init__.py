from mcp_client.voice.voice_setting import VoiceSettingRepository
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

voice_setting_repo = VoiceSettingRepository(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
)

# 사용 가능한 화자 목록
AVAILABLE_SPEAKERS = {
    "nara": "여성 음성 (밝은 톤)",
    "jinho": "남성 음성"
}


def get_available_speakers():
    """사용 가능한 화자 목록 반환"""
    return AVAILABLE_SPEAKERS