import aiohttp
import json
from typing import Dict, List, Optional, Any, Union
from openai import OpenAI
import os

from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url="https://api.openai.com/v1")

'''
mcp-use library 와 다르게 바로 spring 으로 요청 
'''

functions = [
    {
        "type": "function",
        "function": {
            "name": "search_medicine",
            "description": "의약품 이름 기반으로 검색, 관련 의약품 정보들을 조회합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "약 이름 키워드",
                        "nullable": True,
                    },
                },
            }
        }
    }
]

async def process_user_message(jwt_token: str, user_message: str) -> str:

    # 함수 호출을 위한 챗봇 요청
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # 또는 다른 적절한 모델
        messages=[{"role": "user", "content": user_message}],
        tools=functions,
        tool_choice="auto"
    )

    logger.info(f"debug first response: {response}")

    # 응답에서 함수 호출 정보 추출
    message = response.choices[0].message

    # 함수 호출이 있는 경우 처리
    if message.tool_calls:
        function_responses = []

        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            # 함수 실행
            function_result = await _execute_function(jwt_token, function_name, function_args)
            function_responses.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(function_result)
            })

        # 함수 결과를 포함하여 다시 요청
        second_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": user_message},
                message,
                *function_responses
            ]
        )

        # 최종 응답 반환
        return second_response.choices[0].message.content

    # 함수 호출이 없으면 기본 응답 반환
    return message.content


async def _execute_function(jwt_token:str, function_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """함수 실행

    Args:
        function_name: 실행할 함수 이름
        args: 함수 인자들

    Returns:
        함수 실행 결과
    """
    if function_name == "search_medicine":
        return await search_medicine(
            jwt_token=jwt_token,
            name=args.get("name"),
        )
    else:
        raise ValueError(f"알 수 없는 함수: {function_name}")

async def search_medicine(
    jwt_token: str = None,
    name: Optional[str] = None
) -> Dict[str, Any]:
    url = "https://api.medeasy.dev/medicine/search"
    headers = {
        "Authorization": f"Bearer {jwt_token}"
    }
    params = {}
    if name:
        params["name"] = name

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                raise Exception(f"API 요청 실패: {response.status}, {error_text}")

