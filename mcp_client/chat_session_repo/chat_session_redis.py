import json
import time
import redis
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class ChatSessionRepository:
    def __init__(self, host, port, password, max_messages: int=10):
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
            decode_responses=True  # 문자열 응답을 자동으로 디코딩
        )
        self.max_messages = max_messages
        logger.info("✅ chat session redis initialized")

    def get_session_key(self, user_id: int) -> str:
        """세션 ID에 해당하는 Redis 키 생성"""
        return f"chat:session:{user_id}"

    def add_message(self, user_id: int, role: str, message: str) -> bool:
        """
        채팅 세션에 새 메시지 추가 (최신 메시지가 먼저 오도록)

        Args:
            user_id: 메시지 작성자 ID
            role (str): 메시지 작성자 역할
            message: 메시지 내용

        Returns:
            성공 여부
        """
        try:
            # 메시지 객체 생성
            message_obj = {
                "role": role,
                "message": message,
                "timestamp": int(time.time())
            }

            # Redis 파이프라인으로 여러 명령 한번에 실행
            pipe = self.redis.pipeline()

            # 1. 리스트 왼쪽(앞)에 새 메시지 추가 (최신순 정렬)
            pipe.lpush(
                self.get_session_key(user_id),
                json.dumps(message_obj, ensure_ascii=False)
            )

            # 2. 최대 메시지 수로 제한
            pipe.ltrim(
                self.get_session_key(user_id),
                0,
                self.max_messages - 1
            )

            # 3. 세션 만료 시간 설정 (선택 사항) - 3분
            pipe.expire(self.get_session_key(user_id), 180)

            # 명령 실행
            pipe.execute()
            return True
        except Exception as e:
            print(f"메시지 추가 오류: {e}")
            return False

    def get_messages(self, user_id: int, start: int = 0, end: int = -1) -> List[Dict[str, Any]]:
        """
        채팅 세션의 메시지 가져오기 (최신순)

        Args:
            user_id: 채팅 세션 ID
            start: 시작 인덱스 (0 = 가장 최신 메시지)
            end: 종료 인덱스 (-1 = 가장 오래된 메시지)

        Returns:
            메시지 목록 (최신순)
        """
        try:
            # LRANGE로 지정된 범위의 메시지 가져오기
            messages_raw = self.redis.lrange(
                self.get_session_key(user_id),
                start,
                end if end != -1 else self.max_messages - 1
            )

            # JSON 문자열을 객체로 변환
            messages = [json.loads(msg) for msg in messages_raw]
            return messages
        except Exception as e:
            print(f"메시지 조회 오류: {e}")
            return []

    def get_recent_messages(self, user_id: int, count: int = 10) -> List[Dict[str, Any]]:
        """
        최근 메시지 count개 가져오기

        Args:
            user_id: 사용자 식별 ID
            count: 가져올 최근 메시지 수

        Returns:
            최근 메시지 목록 (최신순)
        """
        return self.get_messages(user_id, 0, count - 1)

    def clear_session(self, user_id: int) -> bool:
        """
        채팅 세션 초기화 (모든 메시지 삭제)

        Args:
            user_id: 사용자 식별 ID

        Returns:
            성공 여부
        """
        try:
            self.redis.delete(self.get_session_key(user_id))
            return True
        except Exception as e:
            print(f"세션 초기화 오류: {e}")
            return False

    def session_exists(self, user_id: int) -> bool:
        """
        채팅 세션 존재 여부 확인

        Args:
            user_id: 사용자 식별 ID

        Returns:
            존재 여부
        """
        return self.redis.exists(self.get_session_key(user_id)) > 0

    def get_message_count(self, user_id: int) -> int:
        """
        채팅 세션의 메시지 수 조회

        Args:
            user_id: 사용자 식별 ID

        Returns:
            메시지 수
        """
        return self.redis.llen(self.get_session_key(user_id))