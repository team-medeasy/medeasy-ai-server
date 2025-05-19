from mcp_client.agent.agent_types import AgentState
from mcp_client.client import gpt_nano
import logging

logger = logging.getLogger(__name__)

async def find_medicine_details(
        state: AgentState,
)->AgentState:
    user_message = state["current_message"]
    medicines_data = state["response_data"]

    prompt = f"""
        당신은 고령분 사용자들의 복용 관리 ai 비서 '메디씨'입니다.
        
        사용자는 약에 대한 자세한 정보를 원합니다 
        사용자의 메시지를 보고 의약품 데이터를 참고하여 사용자가 원하는 정보를 추가 제공하세요.
        
        
        의약품 데이터는 순서대로 정렬되어있기 때문에, 
        예를 들어 사용자가 "첫번째 약의 정보를 자세히 알려줘"라고 하면 
        의약품 데이터 배열의 첫번째 요소를 설명해주면 됩니다.
        
        추가로 사용자가 마지막 약의 정보를 자세히 알려줘라고 한다면 
        배열의 마지막 인덱스의 약의 정보에 대해서 알려주면 됩니다.
        
        
        사용자 메시지: {user_message}
        의약품 데이터: {medicines_data}
        
    """
    try:
        logger.info("execute find_medicine_detail node")
        ai_response = await gpt_nano.ainvoke(prompt)
        state["final_response"]=ai_response.content.strip()
    except Exception as e:
        logger.error(e)
        state["final_response"] = "의약품 상세정보 조회 중 오류가 발생하였습니다."

    return state


