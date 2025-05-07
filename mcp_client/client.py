from mcp_use import MCPClient, MCPAgent
from langchain_openai import ChatOpenAI
import os

from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# MCP 클라이언트 초기화
config = {
      "mcpServers": {
        "fastapi-mcp": {
          "command": "npx",
          "args": [
            "mcp-remote",
            "http://127.0.0.1:30003/mcp",
            "8080"
         ]
      }
  }
}
# Create LLM
llm = ChatOpenAI(model_name="gpt-4o-mini")

# Create MCPClient with config
mcp_client = MCPClient.from_dict(config)

# Create agent with the client
agent = MCPAgent(llm=llm, client=mcp_client, max_steps=30)


async def process_user_message(user_message):

    # Run the query
    result = await agent.run(
        user_message,
    )
    print(f"\nResult: {result}")

    return result

