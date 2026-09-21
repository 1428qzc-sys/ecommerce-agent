"""
Agent Nodes — 图中的三个节点实现

三个节点：
1. triage_node  — 意图识别 + 实体提取
2. tool_node    — 执行工具调用
3. response_node — 组装最终回复
"""
import json
import re
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.config import settings
from src.agent.state import AgentState
from src.agent.tools import (
    lookup_order, lookup_orders_by_email, search_orders,
    track_shipment, get_return_policy, check_return_eligibility, initiate_return,
)

logger = logging.getLogger(__name__)

# ── LLM 初始化 ──────────────────────────────────────────────
llm = ChatOpenAI(
    model=settings.model_name,
    temperature=settings.temperature,
    api_key=settings.openai_api_key or "not-set",
    base_url=settings.openai_base_url,
)

ALL_TOOLS = [
    lookup_order, lookup_orders_by_email, search_orders,
    track_shipment, get_return_policy, check_return_eligibility, initiate_return,
]
TOOL_MAP = {t.name: t for t in ALL_TOOLS}

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

MAX_RETRIES = 3


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


# ── 节点 2: 工具执行 ────────────────────────────────────────
def tool_node(state: AgentState) -> dict:
    """根据意图选择工具并执行"""
    intent = state.get("intent", "general")
    order_id = state.get("order_id", "")
    tracking_number = state.get("tracking_number", "")
    tool_results = {}

    try:
        if intent == "order_status":
            if order_id:
                tool_results["lookup_order"] = lookup_order.invoke({"order_id": order_id})
            else:
                tool_results["search_orders"] = "请提供订单号（格式：ORD-XXXX）或您的邮箱地址。"

        elif intent == "shipping_tracking":
            if tracking_number:
                tool_results["track_shipment"] = track_shipment.invoke({"tracking_number": tracking_number})
            else:
                tool_results["track_shipment"] = "请提供物流单号（格式：XXX-XXXXXXXX）。"

        elif intent == "return_request":
            if order_id:
                tool_results["check_return_eligibility"] = check_return_eligibility.invoke({"order_id": order_id})
            else:
                tool_results["check_return_eligibility"] = "请提供需要退货的订单号。"

        elif intent == "return_policy":
            tool_results["get_return_policy"] = get_return_policy.invoke({})

    except Exception as e:
        logger.error("Tool execution error: %s", e)
        tool_results["error"] = str(e)
        return {
            "tool_results": tool_results,
            "retry_count": state.get("retry_count", 0) + 1,
            "error_message": str(e),
        }

    return {
        "tool_results": tool_results,
        "retry_count": 0,
        "error_message": None,
    }


# ── 节点 3: 回复生成 ────────────────────────────────────────
def response_node(state: AgentState) -> dict:
    """根据工具结果组装最终回复"""
    intent = state.get("intent", "general")
    tool_results = state.get("tool_results", {})
    order_id = state.get("order_id", "")
    tracking_number = state.get("tracking_number", "")

    if intent == "order_status" and "lookup_order" in tool_results:
        response = f"已为您查询到订单：\n\n{tool_results['lookup_order']}"

    elif intent == "shipping_tracking" and "track_shipment" in tool_results:
        response = f"物流信息如下：\n\n{tool_results['track_shipment']}"

    elif intent == "return_request" and "check_return_eligibility" in tool_results:
        result = tool_results["check_return_eligibility"]
        if "✅" in result:
            response = f"{result}\n\n是否需要为您发起订单 {order_id} 的退货申请？"
        else:
            response = result

    elif intent == "return_policy" and "get_return_policy" in tool_results:
        response = f"本店退货政策如下：\n\n{tool_results['get_return_policy']}"

    elif "error" in tool_results:
        response = "处理您的请求时遇到问题，请稍后重试。"

    else:
        response = "我可以帮您查询订单、物流和退货相关信息，请提供更多信息。"

    return {"final_response": response}


# ── 路由函数 ────────────────────────────────────────────────
def should_use_tools(state: AgentState) -> str:
    """条件边：根据意图决定走工具路径还是直接回复"""
    intent = state.get("intent", "general")
    if intent in ("order_status", "shipping_tracking", "return_request", "return_policy"):
        return "tools"
    return "response"
