"""
FastAPI 路由 — 提供 /chat 和 /health 接口
"""
import logging
from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage, AIMessage

from src.api.schemas import ChatRequest, ChatResponse, HealthResponse
from src.agent.graph import graph
from src.agent.state import AgentState

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """处理用户消息，返回 Agent 回复"""
    try:
        # 从历史消息 + 新消息构建完整对话上下文
        # 注意：只接受 human/ai 角色，忽略 tool 角色，避免 DeepSeek API 对 ToolMessage 顺序的严格要求
        messages = []
        for msg in request.history:
            role = msg.get("role", "human")
            content = msg.get("content", "")
            if role == "ai":
                messages.append(AIMessage(content=content))
            elif role == "human":
                messages.append(HumanMessage(content=content))
            # 忽略 tool 等其他角色
        messages.append(HumanMessage(content=request.message))

        initial_state: AgentState = {
            "messages": messages,
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
