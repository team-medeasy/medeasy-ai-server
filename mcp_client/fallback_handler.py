import logging
from typing import Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# LLM 초기화
llm = ChatOpenAI(model_name="gpt-4o-mini")


async def generate_fallback_response(
        system_prompt: str,
        user_message: str,
        error: Optional[str] = None
) -> str:
    """
    도구 장애 시 사용되는 대체 응답 생성

    Args:
        system_prompt (str): 시스템 프롬프트
        user_message (str): 사용자 메시지
        error (str, optional): 발생한 오류 메시지

    Returns:
        str: 대체 응답 메시지
    """
    fallback_prompt = f"""
{system_prompt}

중요: 현재 의약품 정보 시스템에 일시적인 연결 문제가 발생했습니다. 
사용자의 질문에 최선을 다해 응답해주세요. 하지만 약물 정보나 복용 관련 데이터는 제공할 수 없습니다.
사용자에게 시스템 장애가 발생했음을 알리고, 잠시 후 다시 시도해달라고 안내해주세요.
"""

    try:
        messages = [
            {"role": "system", "content": fallback_prompt},
            {"role": "user", "content": user_message}
        ]

        response = await llm.ainvoke(messages)
        return response.content
    except Exception as fallback_error:
        # 모든 대체 로직이 실패한 경우 정적 메시지 반환
        logger.error(f"대체 응답 생성 실패: {fallback_error}")
        return (
            "죄송합니다. 현재 서비스에 일시적인 문제가 발생했습니다. "
            "잠시 후 다시 시도해주시기 바랍니다."
        )