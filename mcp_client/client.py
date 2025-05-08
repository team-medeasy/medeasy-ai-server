from mcp_use import MCPClient, MCPAgent
from langchain_openai import ChatOpenAI
import os

from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

config_path = os.getenv("MCP_CONFIG_PATH", "mcp_client_config/medeasy_mcp_client.json")

# Create LLM
llm = ChatOpenAI(model_name="gpt-4o-mini")

# Create MCPClient with config
mcp_client = MCPClient.from_config_file(config_path)

# Create agent with the client
agent = MCPAgent(llm=llm, client=mcp_client, use_server_manager=True, max_steps=20)

async def process_user_message(user_message):

    # Run the query
    result = await agent.run(
        user_message,
    )
    print(f"\nResult: {result}")

    return result

