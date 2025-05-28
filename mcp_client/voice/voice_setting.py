import json
from dataclasses import dataclass, asdict
from typing import Optional

import redis
import logging

logger = logging.getLogger(__name__)

@dataclass
class VoiceSettings:
    """음성 설정 데이터 클래스"""
    speaker: str = "vara"
    speed: int = 0
    pitch: int = 0
    volume: int = 0
    format: str = "mp3"

class VoiceSettingRepository:
    def __init__(self, host, port, password):
        """
        Redis 채팅 세션 레포지토리 초기화

        Args:
            host: Redis 서버 호스트
            port: Redis 서버 포트
            password: Redis 서버 비밀번호
            db: Redis DB 번호
            max_messages: 세션당 저장할 최대 메시지 수
        """
        self.redis = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=True
        )
        self.key_prefix = "voice_settings"
        logger.info("✅ voice setting repository redis initialized")

    def _get_key(self, user_id: str) -> str:
        """사용자 ID로 Redis 키 생성"""
        return f"{self.key_prefix}:{user_id}"

    def save(self, user_id: str, settings: VoiceSettings) -> bool:
        """음성 설정 저장"""
        try:
            key = self._get_key(user_id)
            settings_json = json.dumps(asdict(settings))

            # 30일 만료 설정
            self.redis.setex(key, 2592000, settings_json)
            logger.info(f"음성 설정 저장 완료: {user_id}")
            return True

        except Exception as e:
            logger.error(f"음성 설정 저장 실패: {user_id}, {e}")
            return False

    def get(self, user_id: str) -> Optional[VoiceSettings]:
        """음성 설정 조회"""
        try:
            key = self._get_key(user_id)
            settings_json = self.redis.get(key)

            if not settings_json:
                return None

            settings_dict = json.loads(settings_json)
            return VoiceSettings(**settings_dict)

        except Exception as e:
            logger.error(f"음성 설정 조회 실패: {user_id}, {e}")
            return None

    def get_or_default(self, user_id: str) -> VoiceSettings:
        """음성 설정 조회 (없으면 기본값)"""
        settings = self.get(user_id)
        if settings:
            return settings

        else:
            self.save(user_id, VoiceSettings())
            return VoiceSettings()

    def update(self, user_id: str, **kwargs) -> bool:
        """음성 설정 부분 업데이트"""
        try:
            # 기존 설정 조회
            current = self.get_or_default(user_id)

            # 업데이트할 필드만 변경
            for key, value in kwargs.items():
                if hasattr(current, key):
                    setattr(current, key, value)

            # 저장
            return self.save(user_id, current)

        except Exception as e:
            logger.error(f"음성 설정 업데이트 실패: {user_id}, {e}")
            return False

    def delete(self, user_id: str) -> bool:
        """음성 설정 삭제"""
        try:
            key = self._get_key(user_id)
            result = self.redis.delete(key)

            if result > 0:
                logger.info(f"음성 설정 삭제 완료: {user_id}")
                return True
            else:
                logger.info(f"삭제할 음성 설정 없음: {user_id}")
                return False

        except Exception as e:
            logger.error(f"음성 설정 삭제 실패: {user_id}, {e}")
            return False

    def exists(self, user_id: str) -> bool:
        """음성 설정 존재 여부 확인"""
        try:
            key = self._get_key(user_id)
            return self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"음성 설정 존재 확인 실패: {user_id}, {e}")
            return False