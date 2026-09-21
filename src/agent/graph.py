"""
Agent Graph — LangGraph 状态图的构建

图结构：
    START → triage → [条件判断]
                        ├─ order_status / shipping_tracking / return_request / return_policy → tools → response → END
                        └─ general → response → END
"""
from langgraph.graph import StateGraph, START, END
from src.agent.state import AgentState
from src.agent.nodes import triage_node, tool_node, response_node, should_use_tools, MAX_RETRIES


def build_graph():
    """构建并编译 Agent 状态图"""
    builder = StateGraph(AgentState)

    # 注册三个节点
    builder.add_node("triage", triage_node)
    builder.add_node("tools", tool_node)
    builder.add_node("response", response_node)

    # 入口 → 意图识别
    builder.add_edge(START, "triage")

    # 意图识别后 → 条件路由
    builder.add_conditional_edges("triage", should_use_tools, {
        "tools": "tools",
        "response": "response",
    })

    # 工具执行后 → 回复生成
    builder.add_edge("tools", "response")

    # 回复后 → 结束
    builder.add_edge("response", END)

    return builder.compile()


# 全局图实例
graph = build_graph()
