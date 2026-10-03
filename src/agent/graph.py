"""
Agent Graph — LangGraph 状态图的构建

图结构：
    START → triage（意图识别 + 实体抽取）
          → supervisor（主管：决定派给哪个专员，或判定可以收尾）
               ├→ order_specialist   ←→ order_tools（ReAct 循环，最多 MAX_ITERATIONS 次）
               ├→ return_specialist  ←→ return_tools
               └→ general_specialist（不带工具，直接回话）
          每位专员跑完一步都回到条件判断：
              还要调工具 → 去自己的工具节点 → 执行完再回该专员
              已给出回复 → 回到主管（主管可再次派单，最多转接 MAX_HANDOFFS 次）
          主管判定 FINISH → response → END
"""
from langgraph.graph import StateGraph, START, END
from src.agent.state import AgentState
from src.agent.nodes import (
    triage_node, response_node,
    supervisor_node, route_from_supervisor, should_continue,
    order_specialist, return_specialist, general_specialist,
    SPECIALIST_TOOL_NODES, SPECIALIST_TOOL_NODE_NAMES,
)

# 三位专员：名字 → 节点函数
SPECIALISTS = {
    "order_specialist": order_specialist,
    "return_specialist": return_specialist,
    "general_specialist": general_specialist,
}


def build_graph():
    """构建并编译 Agent 状态图"""
    builder = StateGraph(AgentState)

    # ── 注册节点 ────────────────────────────────────────────
    builder.add_node("triage", triage_node)
    builder.add_node("supervisor", supervisor_node)

    for name, node_fn in SPECIALISTS.items():
        builder.add_node(name, node_fn)

    # 每位带工具的专员配一个专属工具执行节点（前台接待没有）
    builder.add_node("order_tools", SPECIALIST_TOOL_NODES["order_specialist"])
    builder.add_node("return_tools", SPECIALIST_TOOL_NODES["return_specialist"])

    builder.add_node("response", response_node)

    # ── 入口 → 意图识别 → 主管 ──────────────────────────────
    builder.add_edge(START, "triage")
    builder.add_edge("triage", "supervisor")

    # ── 主管派单 → 去对应专员，或收尾 ───────────────────────
    builder.add_conditional_edges("supervisor", route_from_supervisor, {
        "order_specialist": "order_specialist",
        "return_specialist": "return_specialist",
        "general_specialist": "general_specialist",
        "response": "response",
    })

    # ── 每位专员跑完一步 → 调工具？还是回主管？ ──────────────
    # 只为专员注册它自己那条工具边，避免图上出现「订单专员直接跳退货工具」这种不存在的连接
    for name in SPECIALISTS:
        mapping = {"supervisor": "supervisor"}
        tool_node = SPECIALIST_TOOL_NODE_NAMES.get(name)
        if tool_node:
            mapping[tool_node] = tool_node
        builder.add_conditional_edges(name, should_continue, mapping)

    # ── 工具执行完 → 回到发起调用的那位专员 ──────────────────
    builder.add_edge("order_tools", "order_specialist")
    builder.add_edge("return_tools", "return_specialist")

    # ── 收尾 → 结束 ─────────────────────────────────────────
    builder.add_edge("response", END)

    return builder.compile()


# 全局图实例
graph = build_graph()
