import json
from typing import Any, Dict, Optional, List

from langchain_core.messages import BaseMessage
from langchain_core.tools import Tool
from mcp_use import MCPClient, MCPAgent
from langchain_openai import ChatOpenAI
import os

from dotenv import load_dotenv
import logging

from mcp_use.adapters import LangChainAdapter

load_dotenv()
logger = logging.getLogger(__name__)

config_path = os.getenv("MCP_CONFIG_PATH", "/app/mcp_client_config/medeasy_mcp_client.json")

# Create LLM
llm = ChatOpenAI(model_name="gpt-4o-mini")

# Create MCPClient with config
mcp_client = MCPClient.from_config_file(config_path)
adapter = LangChainAdapter()

async def process_user_message(system_prompt: str, user_message: str) -> Any:
    """
    사용자의 메시지에 대해 도구를 사용하여 요청 처리

    Args:
        system_prompt (str): 시스템 프롬프트
        user_message (str): 사용자가 입력한 메시지 내용.

    Returns:
        message: str: LLM 응답 메시지
    """
    # 도구 초기화
    tools = await adapter.create_tools(mcp_client)

    # 요청에 맞는 도구 선택
    initial_response = await _get_initial_response(user_message, tools)
    tool_calls = _extract_tool_calls(initial_response)

    # TODO 도구가 없으면 2번정도 서칭 or LLM으로 응답
    if not tool_calls:
        return initial_response.content

    tool_results = await _execute_tool_calls(tool_calls, tools) # 도구 호출
    response_message:str = await _generate_final_response(system_prompt, user_message, tool_calls, tool_results) # 최종 응답 생성

    return response_message

async def _get_initial_response(
    user_message: str,
    tools: List[Tool]
) -> BaseMessage:
    """
    주어진 사용자의 메시지와 어울리는 도구 리스트 추출

    Args:
        user_message (str): 사용자가 입력한 메시지 내용.
        tools (List[Tool]): LLM 에이전트에 바인딩할 도구들의 리스트.

    Returns:
        BaseMessage: 도구 호출 정보를 포함할 수 있는 초기 LLM 응답 객체
    """
    llm_with_tools = llm.bind_tools(tools)
    response: BaseMessage = await llm_with_tools.ainvoke(user_message)
    logger.info("Initial response received")
    return response

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
            logger.info("Tool %s result: %s", name, content) # 도구 호출 결과
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
        llm_response = await llm.ainvoke(messages)
        logger.info("Received final LLM response")
        return llm_response.content
    except Exception as e:
        logger.exception("Failed to generate final response: %s", e)
        return json.dumps({"tool_results": tool_results, "error": str(e)})