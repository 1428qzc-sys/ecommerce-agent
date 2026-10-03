"""
Agent Nodes — 图中的节点实现

节点：
1. triage_node     — 意图识别 + 实体提取
2. supervisor_node — 主管：决定派给哪个专员，或判定收尾
3. order_specialist / return_specialist / general_specialist — 三个业务专员
4. *_tools         — 专员专属的工具执行节点（LangGraph ToolNode）
5. response_node   — 组装最终回复
"""
import json
import re
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from langgraph.prebuilt import ToolNode
from src.config import settings
from src.agent.state import AgentState
from src.agent.tools import SPECIALIST_TOOLS

logger = logging.getLogger(__name__)

# ── LLM 初始化 ─────────────────────────────────────────────
llm = ChatOpenAI(
    model=settings.model_name,
    temperature=settings.temperature,
    api_key=settings.effective_api_key or "not-set",
    base_url=settings.openai_base_url,
)

# ── 专员角色设定 ────────────────────────────────────────────
# 每个专员只负责一个业务域：提示词和工具都按域收窄，
# 模型面对的选择变少，选错工具、够不着工具的概率随之下降。
SPECIALIST_SYSTEM = {
    "order_specialist": """你是「优品电商」客服团队的订单与物流专员，全程使用简体中文沟通。

你负责：订单详情查询、订单状态、物流追踪。
工作规则：
1. 用分配给你的工具查询真实数据，不要凭空猜测订单或物流信息。
2. 用户拿着订单号追问"货到哪了"时，先用 lookup_order 拿到物流单号，再用 track_shipment 查位置。
3. 查到结果后用友好的中文整理出来，不要把原始工具数据格式直接给用户。
4. 缺少订单号或物流单号时，礼貌地向用户追问。
5. 不要处理退货、退款问题——那不属于你的职责。""",

    "return_specialist": """你是「优品电商」客服团队的退换货专员，全程使用简体中文沟通。

你负责：退货政策咨询、退货资格判断、创建退货申请。
工作规则：
1. 创建退货申请前，必须先确认该订单符合退货条件。
2. 退款金额较大时系统会自动转人工审核，如实告知用户即可，不要承诺具体到账时间。
3. 用友好的中文回复，不要把原始工具数据格式直接给用户。
4. 缺少订单号或退货原因时，礼貌地向用户追问。
5. 不要处理订单查询、物流追踪——那不属于你的职责。""",

    "general_specialist": """你是「优品电商」客服团队的前台接待，全程使用简体中文沟通。

你负责：问候、闲聊，以及不属于订单和退货范畴的一般问题。
工作规则：
1. 热情、简短地回应用户。
2. 可以主动告知用户你能帮他做什么：查询订单、追踪物流、办理退货。
3. 用户提出具体的订单或退货需求时，说明你会为他转接对应专员。
4. 不要编造任何订单或物流信息。""",
}


def with_task(system_prompt: str, task: str) -> str:
    """把主管写下的派工单拼进专员提示词

    转接场景下，专员看到的上文几乎全是上一位专员留下的内容，很容易被带偏：
    要么跟着上文答成别人的题，要么误用「这不归我管」把本次任务拒掉。
    派工单的作用就是用一句话把它拉回本次该做的事。
    """
    if not task:
        return system_prompt
    return (
        f"{system_prompt}\n\n"
        f"【本次任务】{task}\n"
        f"只围绕上面这个问题作答。历史消息里出现的其他话题属于别的专员的职责，"
        f"既不要重复回答，也不要以「不归我管」为由拒绝本次任务。"
    )


def make_specialist(name: str):
    """生成一个专员节点

    三个专员的逻辑完全一致（拼系统提示词 → 调模型 → 追加一条消息），
    区别只在提示词和绑定的工具集，因此用工厂函数生成，避免三段复制粘贴。
    """
    system_prompt = SPECIALIST_SYSTEM[name]
    tools = SPECIALIST_TOOLS[name]
    # 前台接待没有工具，直接用原始模型，不需要 bind_tools
    bound_llm = llm.bind_tools(tools) if tools else llm

    def specialist(state: AgentState) -> dict:
        # 提示词只用于本次调用，不写进 state 历史，避免多轮对话里重复堆叠
        prompt = with_task(system_prompt, state.get("task", ""))
        messages = [SystemMessage(content=prompt)] + state["messages"]
        response = bound_llm.invoke(messages)
        # 只有不带工具调用的那次回复才是「交给用户的答案」，
        # 中间「我要调个工具」的轮次不算，否则会把思考过程混进最终回复
        replies = [response.content] if response.content and not response.tool_calls else []
        return {
            "messages": [response],
            "specialist_replies": replies,
            "retry_count": state.get("retry_count", 0) + 1,
        }

    specialist.__name__ = name
    return specialist


# 三个专员节点实例，供 graph.py 注册
order_specialist = make_specialist("order_specialist")
return_specialist = make_specialist("return_specialist")
general_specialist = make_specialist("general_specialist")

# 每个专员配一个专属的工具执行节点：ToolNode 只认自己绑定的那组工具
SPECIALIST_TOOL_NODES = {
    name: ToolNode(tools) for name, tools in SPECIALIST_TOOLS.items() if tools
}

# 专员 → 它在图里对应的工具执行节点名（供条件边回跳时使用）
SPECIALIST_TOOL_NODE_NAMES = {
    "order_specialist": "order_tools",
    "return_specialist": "return_tools",
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


# ── 主管：决定派给哪个专员 ──────────────────────────────────
SUPERVISOR_SYSTEM = """你是电商客服团队的主管，负责把用户的问题派给合适的专员。

团队里有三位专员：
- order_specialist：订单详情、订单状态、物流追踪
- return_specialist：退货政策、退货资格、创建退货申请
- general_specialist：问候、闲聊、其他一般问题

判断规则：
1. 如果用户的问题已经被专员解决，或用户只是礼貌性回应（如"好的""谢谢"），回复 FINISH。
2. 如果用户提出了新的、属于另一位专员职责的问题，回复那位专员的名字。
3. 不要重复派给刚刚回答过的同一位专员。
4. 派单时必须写清楚 task：用一句话说明这位专员本次要回答的是「哪一个问题」。
   用户一句话里可能提了多件事，前面已答的部分不要放进 task，只写还没答的那件。

严格按以下 JSON 格式回复（不要 markdown，不要多余文字）：
{"next": "<order_specialist|return_specialist|general_specialist|FINISH>", "task": "<一句话任务，FINISH 时留空>"}"""

# triage 识别出的意图 → 首轮直接派给对应专员（省一次模型调用，也不会乱派）
INTENT_TO_SPECIALIST = {
    "order_status": "order_specialist",
    "shipping_tracking": "order_specialist",
    "return_request": "return_specialist",
    "return_policy": "return_specialist",
    "general": "general_specialist",
}

# 一轮对话最多转接几次专员，防止专员之间反复推诿陷入死循环
MAX_HANDOFFS = 3


def supervisor_node(state: AgentState) -> dict:
    """主管节点：决定下一步派给谁，或判定可以收尾

    只写 next 字段、不产生消息——主管负责调度，不产出面向用户的内容，
    这样它的输出不会混进 messages，也就不会干扰最终回复的提取。
    """
    handoff_count = state.get("handoff_count", 0)
    dispatched = state.get("dispatched", [])

    # 转接次数用尽，强制收尾
    if handoff_count >= MAX_HANDOFFS:
        logger.warning("Supervisor reached MAX_HANDOFFS (%d), finishing", MAX_HANDOFFS)
        return {
            "next": "FINISH", "task": "",
            "handoff_count": handoff_count, "dispatched": dispatched,
        }

    # 首轮派单：triage 已经识别出意图，按映射表直接分派
    if handoff_count == 0:
        target = INTENT_TO_SPECIALIST.get(state.get("intent", "general"), "general_specialist")
        # 首轮专员面对的就是用户原话本身，不存在被上文带偏的风险，直接把原话当作派工单
        user_task = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
        )
        return {
            "next": target,
            "task": user_task,
            "handoff_count": 1,
            "dispatched": dispatched + [target],
            "retry_count": 0,   # 新专员接手，工具循环次数重新计数
        }

    # 后续转接：只给模型看「用户最新诉求 + 专员刚给出的回复」两条摘要。
    # 不直接传完整历史，是因为历史里夹着工具消息，截取时容易切断成对关系导致调用失败。
    recent = state["messages"]
    user_msg = next(
        (m.content for m in reversed(recent) if isinstance(m, HumanMessage)), ""
    )
    agent_reply = next(
        (m.content for m in reversed(recent)
         if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)), ""
    )

    try:
        response = llm.invoke([
            SystemMessage(content=SUPERVISOR_SYSTEM),
            HumanMessage(content=f"用户最新消息：{user_msg}\n\n专员刚才的回复：{agent_reply}"),
        ])
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
        next_agent = parsed.get("next", "FINISH")
        task = parsed.get("task", "")
    except Exception as e:
        logger.warning("Supervisor parse failed: %s, finishing", e)
        next_agent, task = "FINISH", ""

    # 模型吐出意外值时兜底收尾，绝不允许派到不存在的专员上
    if next_agent not in set(INTENT_TO_SPECIALIST.values()) and next_agent != "FINISH":
        logger.warning("Supervisor returned unknown target: %s, finishing", next_agent)
        next_agent = "FINISH"

    # 派过的专员不再派第二次：同一领域的追问，专员自己的工具循环就能接着查，
    # 没必要再走一遍转接，白白多花一次模型调用
    if next_agent != "FINISH" and next_agent in dispatched:
        logger.info("Specialist %s already dispatched, finishing", next_agent)
        next_agent = "FINISH"

    return {
        "next": next_agent,
        "task": task if next_agent != "FINISH" else "",
        "handoff_count": handoff_count + 1,
        "dispatched": dispatched + ([next_agent] if next_agent != "FINISH" else []),
        "retry_count": 0,
    }


# ── 节点 2: 回复生成 ────────────────────────────────────────
def response_node(state: AgentState) -> dict:
    """从 Agent 的消息历史中提取最终回复，同时收集工具调用结果给 API

    工具结果统一合并进 AI 回复的 content，不再单独保留工具消息，
    使 messages 列表中只出现 HumanMessage 和 AIMessage。
    """
    messages = state.get("messages", [])

    # 一次对话里可能有多位专员先后作答，答案要全部收上来。
    # 只用「最后一条 AI 消息」是单体 Agent 时代的做法，放到多 Agent 下会丢掉前面专员的成果。
    replies = [r for r in state.get("specialist_replies", []) if r]
    if replies:
        final_response = "\n\n".join(replies)
    else:
        # 没有专员产出过正式回复时（例如首轮就异常中断），退回最后一条 AI 消息
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
def route_from_supervisor(state: AgentState) -> str:
    """条件边：主管派单之后，决定去哪个专员（或收尾）

    主管已经把结论写进 state["next"]，这里只做一次翻译：
    FINISH 翻译成 response 节点，专员名则原样返回。
    """
    next_agent = state.get("next", "FINISH")
    if next_agent == "FINISH":
        return "response"
    return next_agent


def should_continue(state: AgentState) -> str:
    """条件边：专员跑完一步后，判断是去执行工具、还是把活交回主管"""
    last_message = state["messages"][-1]
    needs_tools = hasattr(last_message, "tool_calls") and last_message.tool_calls

    # 还想调工具，但工具循环次数已用尽 → 强制交回主管，防止死循环
    if needs_tools and state.get("retry_count", 0) >= MAX_ITERATIONS:
        logger.warning(
            "Specialist %s reached MAX_ITERATIONS (%d), returning to supervisor",
            state.get("next"), MAX_ITERATIONS,
        )
        return "supervisor"

    # 想调工具 → 去「当前专员自己」的工具节点
    # 前台接待没有工具节点，映射不到就直接回主管兜底
    if needs_tools:
        return SPECIALIST_TOOL_NODE_NAMES.get(state.get("next", ""), "supervisor")

    # 没调工具，说明专员已经把回答写出来了 → 交回主管，由它决定收尾还是转派
    return "supervisor"
