"""
Agent Graph — LangGraph 状态图的构建

图结构：
    START → triage → [条件判断: 需要工具?]
                        ├─ 是 → agent ←→ tools (循环，直到 Agent 满意)
                        │              ↓
                        │           response → END
                        └─ 否 → response → END
"""
from langgraph.graph import StateGraph, START, END
from src.agent.state import AgentState
from src.agent.nodes import (
    triage_node, agent_node, tool_executor, response_node,
    should_use_tools, should_continue,
)


def build_graph():
    """构建并编译 Agent 状态图"""
    builder = StateGraph(AgentState)

    # 注册四个节点
    builder.add_node("triage", triage_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_executor)
    builder.add_node("response", response_node)

    # 入口 → 意图识别
    builder.add_edge(START, "triage")

    # 意图识别后 → 条件路由（需要工具？还是直接回复？）
    builder.add_conditional_edges("triage", should_use_tools, {
        "tools": "agent",
        "response": "response",
    })

    # Agent 执行后 → 条件路由（还要继续调工具？还是已经给出回答？）
    builder.add_conditional_edges("agent", should_continue, {
        "tools": "tools",
        "response": "response",
    })

    # 工具执行完 → 回到 Agent（让 Agent 看工具结果，决定下一步）
    builder.add_edge("tools", "agent")

    # 回复后 → 结束
    builder.add_edge("response", END)

    return builder.compile()


# 全局图实例
graph = build_graph()
