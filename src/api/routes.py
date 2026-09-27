"""
FastAPI 路由 — 提供 /chat 和 /health 接口
类比 Java: 相当于 @RestController
"""
import logging
from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage

from src.api.schemas import ChatRequest, ChatResponse, HealthResponse
from src.agent.graph import graph
from src.agent.state import AgentState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """处理用户消息，返回 Agent 回复"""
    try:
        initial_state: AgentState = {
            "messages": [HumanMessage(content=request.message)],
            "intent": "",
            "order_id": "",
            "tracking_number": "",
            "customer_email": "",
            "tool_results": {},
            "final_response": "",
            "retry_count": 0,
            "error_message": None,
        }

        result = graph.invoke(initial_state)

        return ChatResponse(
            response=result.get("final_response", "Sorry, I couldn't process your request."),
            intent=result.get("intent", "general"),
            order_id=result.get("order_id", ""),
            tracking_number=result.get("tracking_number", ""),
            customer_email=result.get("customer_email", ""),
            tool_results=result.get("tool_results", {}),
        )
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
