"""
Agent Nodes — 图中的节点实现

节点：
1. triage_node  — 意图识别 + 实体提取
2. agent_node   — LLM 自主决策工具调用
3. tool_executor — 工具执行（LangGraph ToolNode）
4. response_node — 组装最终回复
"""
import json
import re
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from langgraph.prebuilt import ToolNode
from src.config import settings
from src.agent.state import AgentState
from src.agent.tools import (
    lookup_order, lookup_orders_by_email, search_orders,
    track_shipment, get_return_policy, check_return_eligibility, initiate_return,
)

logger = logging.getLogger(__name__)

# ── LLM 初始化 ─────────────────────────────────────────────
llm = ChatOpenAI(
    model=settings.model_name,
    temperature=settings.temperature,
    api_key=settings.effective_api_key or "not-set",
    base_url=settings.openai_base_url,
)

ALL_TOOLS = [
    lookup_order, lookup_orders_by_email, search_orders,
    track_shipment, get_return_policy, check_return_eligibility, initiate_return,
]

# ── 真正的 Tool Calling：让 LLM 自己选工具 ──────────────────
llm_with_tools = llm.bind_tools(ALL_TOOLS)
tool_executor = ToolNode(ALL_TOOLS)


def agent_node(state: AgentState) -> dict:
    """Agent 节点：LLM 看到所有消息，自己决定调哪个工具、传什么参数"""
    response = llm_with_tools.invoke(state["messages"])
    return {
        "messages": [response],
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ── 意图识别 Prompt ──────────────────────────────────────────
TRIAGE_SYSTEM = """你是一个电商客服 Agent 的意图分类器。
将客户消息归类为以下意图中的恰好一种：
- order_status: 查询订单详情、状态或历史
- shipping_tracking: 查询物流跟踪或配送情况
- return_request: 想要退货
- return_policy: 咨询退货规则或退货期限
- general: 其他（问候、投诉、一般问题）

同时提取以下实体（如有）：
- order_id: 格式 ORD-XXXX
- tracking_number: 格式 XXX-XXXXXXXX
- customer_email: 格式 xxx@xxx.com

严格按以下 JSON 格式回复（不要 markdown，不要多余文字）：
{"intent": "<intent>", "order_id": "<id or empty>", "tracking_number": "<num or empty>", "customer_email": "<email or empty>"}"""

# Agent 单轮最多执行几轮「思考 → 调工具」，防止模型反复调用工具陷入死循环
MAX_ITERATIONS = 5


# ── 节点 1: 意图识别 ────────────────────────────────────────
def triage_node(state: AgentState) -> dict:
    """分析用户消息 → 识别意图 + 提取实体"""
    messages = state["messages"]
    user_msg = messages[-1].content if messages else ""

    try:
        response = llm.invoke([
            SystemMessage(content=TRIAGE_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Triage parse failed: %s, falling back to regex", e)
        parsed = _fallback_extract(user_msg)

    return {
        "intent": parsed.get("intent", "general"),
        "order_id": parsed.get("order_id", ""),
        "tracking_number": parsed.get("tracking_number", ""),
        "customer_email": parsed.get("customer_email", ""),
    }


def _fallback_extract(text: str) -> dict:
    """LLM 解析失败时的正则兜底"""
    intent = "general"
    lower = text.lower()
    if any(w in lower for w in ["退货", "退款", "换货", "return", "refund"]):
        intent = "return_request"
    elif any(w in lower for w in ["物流", "快递", "配送", "到哪了", "track", "shipping"]):
        intent = "shipping_tracking"
    elif any(w in lower for w in ["订单", "状态", "买了", "order", "status"]):
        intent = "order_status"

    order_id = ""
    m = re.search(r"ORD-\d{4}", text)
    if m:
        order_id = m.group()

    tracking = ""
    m = re.search(r"[A-Z]{3}-\d{8}", text)
    if m:
        tracking = m.group()

    email = ""
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if m:
        email = m.group()

    return {"intent": intent, "order_id": order_id, "tracking_number": tracking, "customer_email": email}



# ── 节点 2: 回复生成 ────────────────────────────────────────
def response_node(state: AgentState) -> dict:
    """从 Agent 的消息历史中提取最终回复，同时收集工具调用结果给 API

    工具结果统一合并进 AI 回复的 content，不再单独保留工具消息，
    使 messages 列表中只出现 HumanMessage 和 AIMessage。
    """
    messages = state.get("messages", [])

    # 从 messages 里找到最后一条 AI 回复（没有 tool_calls 的那种）
    final_response = "抱歉，暂时无法处理您的请求。"
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            final_response = msg.content
            break

    # 从 ToolMessage 里收集工具结果
    tool_results = {}
    for msg in messages:
        if hasattr(msg, "name") and msg.name and hasattr(msg, "content"):
            tool_results[msg.name] = msg.content

    # 如果有工具结果，把它的关键信息拼到 final_response 里
    # 这样下次 LLM 看到这条消息时，能从 content 里读到工具返回的数据
    if tool_results:
        tool_summary = "\n".join(f"[{name}: {content}]" for name, content in tool_results.items())
        if final_response:
            final_response = f"{final_response}\n\n{tool_summary}"
        else:
            final_response = tool_summary

    return {"final_response": final_response, "tool_results": tool_results}


# ── 路由函数 ────────────────────────────────────────────────
def should_use_tools(state: AgentState) -> str:
    """条件边：根据意图决定走工具路径还是直接回复"""
    intent = state.get("intent", "general")
    if intent in ("order_status", "shipping_tracking", "return_request", "return_policy"):
        return "tools"
    return "response"


def should_continue(state: AgentState) -> str:
    """条件边：Agent 调完工具以后，判断是否还需要继续调工具"""
    # 超过最大循环次数，强制走回复（防止死循环）
    if state.get("retry_count", 0) >= MAX_ITERATIONS:
        logger.warning("Agent reached MAX_ITERATIONS (%d), forcing response", MAX_ITERATIONS)
        return "response"

    last_message = state["messages"][-1]
    # 如果 AI 消息里有 tool_calls，说明还要执行工具
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    # 没有 tool_calls，说明 Agent 已经给出最终回答
    return "response"
