"""
FastAPI 路由 — 提供 /chat 和 /health 接口
"""
import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage

from src.api.schemas import ChatRequest, ChatResponse, HealthResponse
from src.agent.graph import graph
from src.agent.state import AgentState
from src.services.session_service import load_history, save_turn, clear_session
from src.observability.langfuse_setup import build_trace_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


def _build_messages(session_id: str, current_message: str) -> list:
    """
    从后端会话存储里取历史，拼上本轮的新消息。

    历史只可能是 human / ai 两种角色（存库时就过滤过），
    所以这里拼出来的顺序天然满足接口对消息顺序的要求。
    """
    messages = []
    for item in load_history(session_id):
        if item["role"] == "ai":
            messages.append(AIMessage(content=item["content"]))
        else:
            messages.append(HumanMessage(content=item["content"]))
    messages.append(HumanMessage(content=current_message))
    return messages


def _build_initial_state(messages: list) -> AgentState:
    """构造一次图执行的初始状态（/chat 和 /chat/stream 共用）"""
    return {
        "messages": messages,
        "intent": "",
        "order_id": "",
        "tracking_number": "",
        "customer_email": "",
        "tool_results": {},
        "specialist_replies": [],
        "final_response": "",
        "retry_count": 0,
        "next": "",
        "task": "",
        "handoff_count": 0,
        "dispatched": [],
        "error_message": None,
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """处理用户消息，返回 Agent 回复（多轮上下文由后端按 session_id 维护）"""
    try:
        messages = _build_messages(request.session_id, request.message)

        result = graph.invoke(_build_initial_state(messages), config=build_trace_config())
        final_response = result.get("final_response", "抱歉，暂时无法处理您的请求。")

        # 本轮对话落库，下一轮请求就能带着上下文继续聊
        save_turn(request.session_id, request.message, final_response)

        return ChatResponse(
            response=final_response,
            intent=result.get("intent", "general"),
            order_id=result.get("order_id", ""),
            tracking_number=result.get("tracking_number", ""),
            customer_email=result.get("customer_email", ""),
            tool_results=result.get("tool_results", {}),
        )
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── 流式输出（SSE）───────────────────────────────────────────────
# 执行轨迹的中文标签：图节点 → (角色, 阶段, 动作说明)
# 前端据此渲染「Agent 执行轨迹」，把多智能体协作过程呈现出来
AGENT_LABELS = {
    "triage":            ("意图识别",       "analyze",     "正在识别您的意图..."),
    "supervisor":        ("调度主管",       "dispatch",    "正在为您分配专员..."),
    "order_specialist":  ("订单与物流专员", "specialist",  "订单专员正在处理..."),
    "return_specialist": ("退换货专员",     "specialist",  "退货专员正在处理..."),
    "general_specialist":("前台接待",       "specialist",  "客服正在回复..."),
    "order_tools":       ("订单与物流专员", "tool",        "正在查询订单与物流数据..."),
    "return_tools":      ("退换货专员",     "tool",        "正在查询退货相关数据..."),
    "response":          ("系统",           "final",       "正在整理回复..."),
}

# 工具内部名 → 给用户看的中文名
TOOL_LABELS = {
    "lookup_order": "查询订单详情",
    "lookup_orders_by_email": "按邮箱查订单",
    "search_orders": "搜索订单",
    "track_shipment": "查询物流进度",
    "get_return_policy": "查询退货政策",
    "check_return_eligibility": "校验退货资格",
    "initiate_return": "创建退货申请",
}

SPECIALIST_LABELS = {
    "order_specialist": "订单与物流专员",
    "return_specialist": "退换货专员",
    "general_specialist": "前台接待",
}

# 只有这三个专员的模型输出才会逐字推给用户
# 主管只做调度、不产出面向用户的内容，它的输出不能混进正文
SPECIALIST_NODES = {"order_specialist", "return_specialist", "general_specialist"}

# 意图的中文名，给用户展示进度用（不暴露内部字段值）
INTENT_LABELS = {
    "order_status": "订单状态查询",
    "shipping_tracking": "物流追踪",
    "return_request": "退货申请",
    "return_policy": "退货政策咨询",
    "general": "通用问答",
}


def _sse(payload: dict) -> str:
    """把一块数据包装成 SSE 协议的格式：一行 data: 加一个空行"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _tool_identity(event: dict) -> tuple[str, str]:
    """工具事件里工具名藏在哪几个字段因版本而异，统一取出来"""
    name = event.get("name") or ""
    if not name:
        name = event.get("metadata", {}).get("langgraph_tool_name", "")
    return name, TOOL_LABELS.get(name, name)


async def _stream_reply(session_id: str, current_message: str):
    """
    边跑边推的生成器：把 Agent 图的执行过程逐步推给前端。

    事件三类：
      - trace ：执行轨迹的一步（谁在干、调哪个工具、传了什么、返回什么）
      - token ：专员模型输出的正文，打字机效果
      - done  ：跑完落库后的完整回复

    只有专员节点的模型输出会当 token 推出去——
    triage 输出的是意图 JSON、主管输出的是派单 JSON，都不能给用户看。

    落库时机仍然坚持「跑完才存」：等所有字块推完、拼出完整回复
    之后再 save_turn，保证库里存的永远是完整的问答对。
    """
    messages = _build_messages(session_id, current_message)
    chunks: list[str] = []
    last_start_node = ""   # 同一节点连续两次 start 时去重（LangGraph 会重复推）

    def emit_trace(phase: str, agent: str, content: str, **extra):
        payload = {"type": "trace", "phase": phase, "agent": agent, "content": content}
        payload.update(extra)
        return _sse(payload)

    try:
        async for event in graph.astream_events(
            _build_initial_state(messages), version="v2", config=build_trace_config()
        ):
            node = event.get("metadata", {}).get("langgraph_node", "")
            kind = event["event"]

            # 1) 节点开始执行 → 一条轨迹（含角色和阶段）
            # LangGraph 对同一节点会连推两次 start，这里去重，避免轨迹里刷重复行
            if kind == "on_chain_start" and node in AGENT_LABELS:
                if node != last_start_node:
                    agent, phase, desc = AGENT_LABELS[node]
                    yield emit_trace(phase, agent, desc, node=node)
                last_start_node = node

            # 2) 意图识别完成 → 用中文告诉用户识别到了什么
            elif kind == "on_chain_end" and node == "triage":
                output = event["data"].get("output")
                if isinstance(output, dict):
                    intent = output.get("intent", "")
                    if intent:
                        label = INTENT_LABELS.get(intent, intent)
                        entities = [
                            f"{k}={output[k]}"
                            for k in ("order_id", "tracking_number", "customer_email")
                            if output.get(k)
                        ]
                        detail = f"识别到：{label}"
                        if entities:
                            detail += "（提取实体：" + "、".join(entities) + "）"
                        yield emit_trace("analyze", "意图识别", detail, node=node)

            # 3) 主管派单决策 → 揭示调度过程，让「多智能体」看得见
            elif kind == "on_chain_end" and node == "supervisor":
                output = event["data"].get("output")
                if isinstance(output, dict):
                    target = output.get("next", "")
                    if target and target != "FINISH":
                        agent_name = SPECIALIST_LABELS.get(target, target)
                        task = output.get("task", "")
                        detail = f"主管派单 → {agent_name}"
                        if task:
                            detail += f"，任务：{task}"
                        yield emit_trace("dispatch", "调度主管", detail, node=node, target=target)
                    elif target == "FINISH":
                        yield emit_trace("dispatch", "调度主管", "主管判定：可以收尾", node=node, target="FINISH")

            # 4) 工具调用开始 → 工具名 + 入参
            elif kind == "on_tool_start":
                tool_name, tool_label = _tool_identity(event)
                if tool_name:
                    raw_input = event["data"].get("input")
                    args = raw_input if isinstance(raw_input, dict) else {"输入": str(raw_input)}
                    agent = AGENT_LABELS.get(node, ("专员",))[0]
                    yield emit_trace("tool", agent, f"调用工具：{tool_label}", node=node,
                                     tool=tool_name, tool_label=tool_label, args=args)

            # 5) 工具调用结束 → 返回结果（截断，避免刷屏）
            elif kind == "on_tool_end":
                tool_name, tool_label = _tool_identity(event)
                if tool_name:
                    raw_output = event["data"].get("output")
                    result = str(raw_output) if raw_output is not None else ""
                    if len(result) > 400:
                        result = result[:400] + "…"
                    agent = AGENT_LABELS.get(node, ("专员",))[0]
                    yield emit_trace("tool_result", agent, f"工具返回：{tool_label}", node=node,
                                     tool=tool_name, tool_label=tool_label, result=result)

            # 6) 专员节点的模型输出 → 逐字推给用户
            elif kind == "on_chat_model_stream" and node in SPECIALIST_NODES:
                text = event["data"]["chunk"].content
                if not text:
                    continue
                chunks.append(text)
                yield _sse({"type": "token", "content": text})

        final_response = "".join(chunks).strip() or "抱歉，暂时无法处理您的请求。"
        save_turn(session_id, current_message, final_response)
        yield _sse({"type": "done", "content": final_response, "session_id": session_id})
    except Exception as e:
        logger.error("Stream chat error: %s", e)
        yield _sse({"type": "error", "content": "服务处理出错，请稍后重试。"})


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天：模型边生成边推给前端，不用干等整段回复"""
    return StreamingResponse(
        _stream_reply(request.session_id, request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 防止反向代理把流缓冲住
        },
    )


@router.delete("/chat/{session_id}")
async def reset_chat(session_id: str):
    """清空某个会话的历史记录"""
    deleted = clear_session(session_id)
    return {"status": "ok", "session_id": session_id, "deleted": deleted}


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
