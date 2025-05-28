import asyncio
import json
from typing import Any, Dict, Optional, List, Tuple

from langchain_core.messages import BaseMessage
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
import os

from dotenv import load_dotenv
import logging

from mcp_client.prompt import final_response_system_prompt, tool_selector_system_prompt, system_prompt

from mcp_client.fallback_handler import generate_fallback_response
from mcp_client.manager.mcp_client_manager import client_manager
from mcp_client.util.retry_utils import with_retry
from mcp_client.chat_session_repo import chat_session_repo
from mcp_client.manager.tool_manager import tool_manager

import random
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


load_dotenv()
logger = logging.getLogger(__name__)

config_path = os.getenv("MCP_CONFIG_PATH", "/app/mcp_client_config/medeasy_mcp_client.json")

# Create LLM
gpt_nano= ChatOpenAI(model_name="gpt-4.1-nano")
gpt_mini= ChatOpenAI(model_name="gpt-4.1-mini")
final_response_llm= ChatOpenAI(model_name="gpt-4.1-mini", max_tokens=1500)
tool_llm = ChatOpenAI(model_name="gpt-4.1-mini")

# SSE 연결 오류를 위한 재시도 데코레이터
@retry(
    retry=retry_if_exception_type(Exception),  # SSE 오류 클래스로 변경 가능
    stop=stop_after_attempt(5),  # 최대 5회 재시도
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 지수 백오프
    before_sleep=lambda retry_state: print(f"연결 재시도 중... ({retry_state.attempt_number}/5)")
)
async def get_tools_with_retry():
    # 랜덤 지연을 추가해 동시 연결 문제 완화
    await asyncio.sleep(random.uniform(0.5, 2.0))
    return await client_manager.get_tools()

# 서비스 초기화
async def initialize_service():
    """서비스 시작 시 호출되는 초기화 함수"""
    await client_manager.initialize()

async def process_user_message(user_message: str, user_id: int) -> Tuple[str, Optional[str]]:
    """
    사용자의 메시지에 대해 도구를 사용하여 요청 처리

    Args:
        system_prompt (str): 시스템 프롬프트
        user_message (str): 사용자가 입력한 메시지 내용.
        user_id (int): 사용자 식별자

    Returns:
        message: str: LLM 응답 메시지
    """
    # 채팅 이력을 가져와 컨텍스트에 포함
    logger.info("채팅 이력 조회")
    recent_messages = chat_session_repo.get_recent_messages(user_id, 10)
    chat_history: str = format_chat_history(recent_messages)
    logger.info(f"채팅 이력 조회 완료")

    # 도구 초기화
    logger.info("도구 로딩")
    tools = await tool_manager.get_tools()
    logger.info("도구 로딩 완료")

    if not tools:
        # 도구 초기화 실패 시 대체 응답
        logger.warning("mcp server 도구 로딩 에러")
        fallback_response = await generate_fallback_response(system_prompt, user_message, chat_history)

        chat_session_repo.add_message(user_id=user_id, role="user", message=user_message)
        chat_session_repo.add_message(user_id=user_id, role="system", message=fallback_response)
        return fallback_response, None

    try:
        # 초기 응답 생성 (재시도 로직 포함)
        async def _get_initial():
            return await _get_initial_response(user_message, tools, chat_history)

        logger.info("메시지와 어울리는 도구 호출")
        initial_response = await with_retry(_get_initial)
        tool_calls = _extract_tool_calls(initial_response)
        logger.info("메시지와 어울리는 도구 호출 완료")


        # 도구 호출 결과에 따른 분기 처리
        if not tool_calls:
            response = initial_response.content
            chat_session_repo.add_message(user_id, "user", user_message)
            chat_session_repo.add_message(user_id, "system", response)
            return response, None

        for tool_call in tool_calls:
            if tool_call.get('function', {}).get('name') == 'register_routine_by_prescription':
                return '처방전 촬영해주세요.', "CAPTURE_PRESCRIPTION"

            if tool_call.get('function', {}).get('name') == 'register_routine_by_pills_photo':
                return '알약 사진을 촬영해주세요.', "CAPTURE_PILLS_PHOTO"


        # 도구 실행 (재시도 로직 포함)
        async def _execute_tools():
            return await _execute_tool_calls(tool_calls, tools)
        logger.info("도구 실행")
        tool_results = await with_retry(_execute_tools)
        logger.info("도구 실행 완료")

        # 최종 응답 생성 (재시도 로직 포함)
        async def _generate_final():
            return await _generate_final_response(final_response_system_prompt, user_message, tool_calls, tool_results)

        logger.info("최종 응답 생성")
        final_response = await with_retry(_generate_final)
        logger.info("최종 응답 생성 완료")

        logger.info("대화 내용 저장")
        # 사용자 및 시스템 응답 저장
        chat_session_repo.add_message(user_id=user_id, role="user", message=user_message)
        chat_session_repo.add_message(user_id, "system", final_response)
        logger.info("대화 내용 저장완료")
        return final_response, None

    except Exception as e:
        logger.exception(f"메시지 처리 중 오류 발생: {e}")
        # 장애 발생 시 대체 응답
        fallback_response = await generate_fallback_response(system_prompt, user_message, str(e))

        chat_session_repo.add_message(user_id, "system", fallback_response)
        return fallback_response, None

async def _get_initial_response(
    jwt_token: str,
    user_message: str,
    tools: List[Tool],
    chat_history: Optional[str] = None,
) -> BaseMessage:
    """
    주어진 사용자의 메시지와 이전 채팅 이력을 바탕으로 도구 리스트 추출

    Args:
        user_message (str): 사용자가 입력한 메시지 내용.
        tools (List[Tool]): LLM 에이전트에 바인딩할 도구들의 리스트.
        chat_history (Optional[str]): 이전 대화 내역 (포맷팅된 문자열)

    Returns:
        BaseMessage: 도구 호출 정보를 포함할 수 있는 초기 LLM 응답 객체
    """
    llm_with_tools = tool_llm.bind_tools(tools)
    # 채팅 이력이 있는 경우 프롬프트에 포함

    messages = [
        {"role": "developer", "content": tool_selector_system_prompt+final_response_system_prompt},
        {"role": "user", "content": f"jwt_token: {jwt_token}"},
    ]

    # 채팅 이력이 있는 경우만 포함 (토큰 절약)
    if chat_history and len(chat_history) > 0:
        # 채팅 이력 요약/축소하여 토큰 수 제한
        condensed_history = _condense_chat_history(chat_history)
        messages.append({"role": "system", "content": f"이전 대화 내용: {chat_history}"})

    # 사용자 메시지 추가
    messages.append({"role": "user", "content": user_message})

    response: BaseMessage = await llm_with_tools.ainvoke(messages)
    return response

def _condense_chat_history(chat_history: str) -> str:
    """채팅 이력을 요약하거나 축소하여 토큰 수를 줄임"""
    # 실제 구현에서는 최근 N개 메시지만 유지하거나,
    # 키워드 추출 등의 방법으로 이력을 요약할 수 있음
    lines = chat_history.split('\n')
    if len(lines) > 10:  # 예: 최대 10줄만 유지
        return '\n'.join(lines[-10:])
    return chat_history

def _extract_tool_calls(response: BaseMessage) -> List[Dict[str, Any]]:
    """
    LLM 모델의 응답으로부터 도구 추출

    Args:
        response: BaseMessage: LLM 모델 응답 메시지 객체

    Returns:
        tool_calls: List[Dict[str, Any]]: 추출한 도구 정보
    """
    kwargs = getattr(response, "additional_kwargs", {})
    tool_calls = kwargs.get("tool_calls", [])
    logger.info("Extracted tool_calls: %s", tool_calls)
    return tool_calls


async def _execute_tool_calls(
    tool_calls: List[Dict[str, Any]],
    tools: List[Tool]
) -> List[Dict[str, Any]]:
    """
    추출한 도구들을 실행

    Args:
        tool_calls: List[Dict[str, Any]]: 추출한 도구 정보
        tools: List[Tool]: 전체 도구들

    Returns:
        results: List[Dict[str, Any]: json 배열 예시: [{"tool_call_id": tool_call_id, "name": name, "content": content}]
    """

    results: List[Dict[str, Any]] = []

    for call in tool_calls:
        tool_id = call.get("id")
        func = call.get("function", {})
        name = func.get("name")
        args = _parse_arguments(func.get("arguments", "{}"))

        # 추출한 도구와 이름이 같은 첫번째 도구 선택
        tool = next((t for t in tools if t.name == name), None)

        if tool is None:
            error = f"Tool '{name}' not found"
            logger.error(error)
            results.append(_make_result(tool_id, name, error))
            continue

        try:
            raw = await tool.ainvoke(args) # 도구 호출
            content = raw if isinstance(raw, str) else json.dumps(raw) # raw가 str이면 -> raw 아니면 json.dumps(raw)
            # logger.info("Tool %s result: %s", name, content) # 도구 호출 결과
            results.append(_make_result(tool_id, name, content))
        except Exception as e:
            error = f"Error executing {name}: {e}"
            logger.exception(error)
            results.append(_make_result(tool_id, name, error))

    return results

def _parse_arguments(arg_str: str) -> Dict[str, Any]:
    try:
        return json.loads(arg_str)
    except json.JSONDecodeError:
        logger.warning("Failed to parse arguments JSON: %s", arg_str)
        return {}

def _make_result(
    tool_call_id: Optional[str],
    name: str,
    content: str
) -> Dict[str, Any]:
    return {"tool_call_id": tool_call_id, "name": name, "content": content}

async def _generate_final_response(
    system_prompt: str,
    user_message: str,
    tool_calls: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
) -> str:
    """
    사용자에게 내려줄 최종 응답 생성

    Args:
        user_message:str 사용자 메시지
        tool_calls: List[Dict[str, Any]] 추출된 도구 정보
        tool_results: List[Dict[str, Any]] 도구 수행 결과

    Returns:
        llm_response.content: str 응답 메시지
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }
                for tc in tool_calls
            ],
        },
    ]

    for result in tool_results:
        messages.append(
            {
                "role": "tool",
                "tool_call_id": result["tool_call_id"],
                "name": result["name"],
                "content": result["content"],
            }
        )

    try:
        llm_response = await final_response_llm.ainvoke(messages)
        return llm_response.content
    except Exception as e:
        logger.exception("Failed to generate final response: %s", e)
        return "죄송합니다. 요청을 처리하던 중 오류가 발생하였습니다. 나중에 다시 시도해주세요."


# 채팅 이력을 포맷팅하는 함수
def format_chat_history(messages: List[Dict]) -> str:
    """채팅 이력을 프롬프트에 포함하기 위한 포맷팅"""
    formatted = "이전 대화 내역:\n"

    for msg in messages:
        # 시간 포맷팅
        from datetime import datetime
        role = msg.get("role", "")
        timestamp = datetime.fromtimestamp(msg['timestamp'])
        time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        formatted += f"[{time_str}] {role}: {msg['message']}\n"

    return formatted
