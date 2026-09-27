"""
Pydantic Schemas — FastAPI 的请求/响应数据模型
类比 Java: 相当于 Controller 层的 @RequestBody / @ResponseBody DTO
"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息", min_length=1)
    session_id: str = Field(default="default", description="会话 ID（用于多轮对话）")


class ChatResponse(BaseModel):
    response: str = Field(..., description="助手回复")
    intent: str = Field(default="general", description="识别到的意图")
    order_id: str = Field(default="", description="提取的订单号")
    tracking_number: str = Field(default="", description="提取的物流单号")
    customer_email: str = Field(default="", description="提取的客户邮箱")
    tool_results: dict = Field(default_factory=dict, description="工具调用结果")


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
