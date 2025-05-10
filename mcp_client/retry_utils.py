import asyncio
import logging
import random
import os
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

# 재시도 설정
MAX_RETRIES = int(os.getenv("MCP_MAX_RETRIES", 3))
INITIAL_BACKOFF = float(os.getenv("MCP_INITIAL_BACKOFF", 1.0))  # 초 단위
MAX_BACKOFF = float(os.getenv("MCP_MAX_BACKOFF", 20.0))  # 최대 백오프 시간 (초)
BACKOFF_FACTOR = float(os.getenv("MCP_BACKOFF_FACTOR", 2.0))  # 백오프 증가 계수
JITTER = float(os.getenv("MCP_JITTER", 0.1))  # 백오프에 추가할 랜덤 요소 (최대 ±10%)

T = TypeVar('T')  # 제네릭 타입 변수


async def exponential_backoff(retry_count: int) -> float:
    """
    지수 백오프 시간 계산 함수

    Args:
        retry_count (int): 현재 재시도 횟수

    Returns:
        float: 다음 재시도까지 대기할 시간(초)
    """
    backoff = min(MAX_BACKOFF, INITIAL_BACKOFF * (BACKOFF_FACTOR ** retry_count))
    jitter_amount = backoff * JITTER
    random_jitter = random.uniform(-jitter_amount, jitter_amount)
    return backoff + random_jitter


async def with_retry(func: Callable[..., T], *args, **kwargs) -> T:
    """
    지정된 함수를 재시도 로직과 함께 실행

    Args:
        func (Callable): 실행할 함수
        *args: 함수에 전달할 위치 인자
        **kwargs: 함수에 전달할 키워드 인자

    Returns:
        T: 함수의 반환값

    Raises:
        Exception: 모든 재시도 후에도 함수가 실패하면 마지막 예외를 발생
    """
    retry_count = 0
    last_exception = None

    while retry_count <= MAX_RETRIES:
        try:
            if retry_count > 0:
                logger.info(f"시도 {retry_count}/{MAX_RETRIES}...")

            return await func(*args, **kwargs)

        except Exception as e:
            last_exception = e
            retry_count += 1

            if retry_count <= MAX_RETRIES:
                backoff_time = await exponential_backoff(retry_count)
                logger.warning(f"오류 발생: {e}. {backoff_time:.2f}초 후 재시도 ({retry_count}/{MAX_RETRIES})...")
                await asyncio.sleep(backoff_time)
            else:
                logger.error(f"최대 재시도 횟수 초과. 마지막 오류: {e}")
                break

    # 모든 재시도가 실패한 경우 마지막 예외 발생
    if last_exception:
        raise last_exception