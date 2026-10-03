"""
Agent State — 定义 LangGraph 中流转的数据结构
"""
import operator
from typing import Annotated, Any, Dict, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Agent 的状态定义，每个字段都会在节点间传递"""
    # 用 add_messages 做追加：每个节点产生的消息依次追加到历史里，
    # 保证「AI 发起工具调用 → 工具回结果」的先后次序不会丢
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str                          # 识别出的意图
    order_id: str                        # 提取到的订单号
    tracking_number: str                 # 提取到的物流单号
    customer_email: str                  # 提取到的客户邮箱
    tool_results: Dict[str, Any]        # 工具调用结果
    # 本轮各位专员给出的回答，用 add 累积：一次转接链里可能有多位专员各答一段，
    # 只取最后一条会丢掉前面专员的成果
    specialist_replies: Annotated[list, operator.add]
    final_response: str                  # 最终回复文本
    retry_count: int                     # 专员内部的工具循环次数（防死循环）
    next: str                            # 主管的调度结果：下一个专员名，或 FINISH
    task: str                            # 派工单：主管写给专员的一句话任务，明确本次要回答什么
    handoff_count: int                   # 已转接次数（防专员之间互相推诿）
    dispatched: list                     # 本轮已派过的专员（防重复派单）
    error_message: Optional[str]         # 错误信息
