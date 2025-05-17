import asyncio
from datetime import datetime
from typing import List

from langchain_core.tools import Tool

from mcp_client.manager.mcp_client_manager import client_manager
import logging

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self):
        self._tools_cache = None
        self._last_update = None
        self._cache_ttl = 3600  # 캐시 유효 시간(초) - 필요에 따라 조정
        self._lock = asyncio.Lock()  # 동시 업데이트 방지를 위한 락

    async def initialize(self):
        """서비스 시작 시 도구 목록 초기화"""
        await self._update_tools_cache()

    async def get_tools(self) -> List[Tool]:
        """캐시된 도구 목록 반환, 필요시 갱신"""
        # 캐시가 없거나 TTL이 만료된 경우에만 갱신
        if (self._tools_cache is None or
            self._last_update is None or
            (datetime.now() - self._last_update).total_seconds() > self._cache_ttl):

            async with self._lock:  # 여러 요청이 동시에 업데이트하는 것 방지
                # 락 획득 후 다시 체크 (다른 스레드가 이미 업데이트했을 수 있음)
                if (self._tools_cache is None or
                        self._last_update is None or
                        (datetime.now() - self._last_update).total_seconds() > self._cache_ttl):
                    await self._update_tools_cache()

        return self._tools_cache

    async def _update_tools_cache(self):
        """도구 목록 캐시 갱신"""
        try:
            # 랜덤 지연을 추가해 동시 연결 문제 완화
            await asyncio.sleep(0.5)
            self._tools_cache = await client_manager.get_tools()
            self._last_update = datetime.now()
            logger.info("도구 목록 캐시 갱신 완료")
        except Exception as e:
            logger.error(f"도구 목록 캐시 갱신 실패: {e}")
            # 캐시 갱신에 실패했으나 기존 캐시가 있으면 계속 사용
            if self._tools_cache is None:
                self._tools_cache = []

    async def force_refresh(self):
        """도구 목록 강제 갱신 (도구 변경 이벤트 발생 시 호출)"""
        async with self._lock:
            await self._update_tools_cache()


# 싱글톤 인스턴스 생성
tool_manager = ToolManager()
