import asyncio
import logging
import os
from typing import Optional, List

from mcp_use import MCPClient
from mcp_use.adapters import LangChainAdapter
from langchain_core.tools import Tool

from mcp_client.util.retry_utils import with_retry, exponential_backoff

logger = logging.getLogger(__name__)

# MCP 클라이언트 설정
config_path = os.getenv("MCP_CONFIG_PATH", "/app/mcp_client_config/medeasy_mcp_client.json")


class MCPClientManager:
    """MCP 클라이언트 관리 클래스"""

    def __init__(self, config_path: str = config_path):
        self.config_path = config_path
        self.client: Optional[MCPClient] = None
        self.adapter: Optional[LangChainAdapter] = None
        self._reconnect_task = None
        self._max_background_retries = 3

    async def initialize(self) -> bool:
        """
        MCP 클라이언트 초기화

        Returns:
            bool: 초기화 성공 여부
        """
        try:
            logger.info("MCP 클라이언트 초기화 중...")
            self.client = MCPClient.from_config_file(self.config_path)
            self.adapter = LangChainAdapter()
            logger.info("MCP 클라이언트 초기화 완료!")
            return True
        except Exception as e:
            logger.error(f"MCP 클라이언트 초기화 실패: {e}")
            self._start_background_reconnect()
            return False

    async def get_tools(self) -> List[Tool]:
        """
        사용 가능한 도구 목록 가져오기 (재시도 로직 포함)

        Returns:
            List[Tool]: 사용 가능한 도구 목록
        """
        if not self.client or not self.adapter: # 초기화가 되지 않은 경우에
            success = await self.initialize()
            if not success:
                return []

        try:
            async def _get_tools()->List[Tool]:
                return await self.adapter.create_tools(self.client)

            return await with_retry(_get_tools)

        except Exception as e:
            logger.error(f"도구 가져오기 실패: {e}")
            await self.reconnect()
            return []

    async def reconnect(self) -> bool:
        """
        MCP 클라이언트 재연결

        Returns:
            bool: 재연결 성공 여부
        """
        try:
            logger.info("MCP 클라이언트 재연결 시도...")
            success = await self.initialize()
            if success:
                logger.info("MCP 클라이언트 재연결 성공!")
            return success
        except Exception as e:
            logger.error(f"MCP 클라이언트 재연결 실패: {e}")
            self._start_background_reconnect()
            return False

    def _start_background_reconnect(self) -> None:
        """백그라운드에서 주기적으로 재연결을 시도하는 작업 시작"""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._background_reconnect())

    async def _background_reconnect(self) -> None:
        """백그라운드 재연결 작업"""
        retry_count = 0

        while retry_count < self._max_background_retries:
            try:
                await asyncio.sleep(await exponential_backoff(retry_count))
                logger.info(f"백그라운드 재연결 시도 {retry_count + 1}/{self._max_background_retries}...")

                success = await self.initialize()
                if success:
                    logger.info("MCP 클라이언트 백그라운드 재연결 성공!")
                    return

            except Exception as e:
                logger.error(f"백그라운드 재연결 실패: {e}")

            retry_count += 1

        logger.critical(
            f"최대 백그라운드 재시도 횟수({self._max_background_retries})를 초과했습니다. "
            "수동으로 서비스를 재시작해주세요."
        )


# 싱글톤 인스턴스
client_manager = MCPClientManager()