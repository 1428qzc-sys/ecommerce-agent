"""
Agent State — 定义 LangGraph 中流转的数据结构
类比 Java: 相当于一个 DTO / Context 对象，在图的各个节点之间传递
"""
from typing import Any, Dict, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Agent 的状态定义，每个字段都会在节点间传递"""
    messages: list[BaseMessage]          # 消息列表（用 add_messages reducer 自动追加）
    intent: str                          # 识别出的意图
    order_id: str                        # 提取到的订单号
    tracking_number: str                 # 提取到的物流单号
    customer_email: str                  # 提取到的客户邮箱
    tool_results: Dict[str, Any]        # 工具调用结果
    final_response: str                  # 最终回复文本
    retry_count: int                     # 重试次数（防止死循环）
    error_message: Optional[str]         # 错误信息
