from mcp_client.chat_session_repo.chat_session_redis import ChatSessionRepository
import os
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_MAX_MESSAGES = int(os.getenv("REDIS_MAX_MESSAGES", 10))

chat_session_repo = ChatSessionRepository(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    max_messages=REDIS_MAX_MESSAGES
)
