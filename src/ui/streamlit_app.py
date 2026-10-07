"""
Streamlit 前端 — 客服聊天界面
启动: streamlit run src/ui/streamlit_app.py
"""
import json
import os
import uuid

import streamlit as st
import requests

# ── 页面配置 ──────────────────────────────────────────────────
st.set_page_config(page_title="电商智能客服", page_icon="●", layout="centered")

# ── 样式 ─────────────────────────────────────────────────────
# 主题色由 .streamlit/config.toml 固定为浅色，这里只做细节排版
st.markdown("""<style>
:root {
    --brand: #4f46e5;
    --brand-soft: #eef2ff;
    --ink: #111827;
    --ink-2: #6b7280;
    --line: #e5e7eb;
    --surface: #ffffff;
}

/* 隐藏 Streamlit 默认的页眉菜单和页脚 */
#MainMenu, footer, header [data-testid="stDecoration"],
[data-testid="stToolbar"], [data-testid="stStatusWidget"],
.stDeployButton { display: none !important; }

/* 页面背景与内容宽度 */
.stApp { background: #f7f8fa; }
.block-container {
    max-width: 760px;
    padding-top: 1.6rem;
    padding-bottom: 7rem;
}

/* 页头 */
.brand { display: flex; align-items: center; gap: 10px; }
.brand-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--brand); box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.12);
}
.brand-name {
    font-size: 1.15rem; font-weight: 700; color: var(--ink);
    letter-spacing: 0.2px;
}
.brand-sub {
    font-size: 0.82rem; color: var(--ink-2);
    margin: 6px 0 20px 20px;
}

/* 快捷按钮：胶囊形，白底深色字，悬停变主色 */
.stButton > button {
    width: 100%;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    font-size: 0.82rem;
    font-weight: 500;
    padding: 0.55rem 0.6rem;
    white-space: nowrap;
    box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
    transition: all 0.15s ease;
}
.stButton > button p { font-size: 0.82rem; font-weight: 500; }
.stButton > button:hover {
    border-color: var(--brand);
    background: var(--brand-soft);
    color: var(--brand);
}
.stButton > button:hover p { color: var(--brand); }
.stButton > button:focus:not(:active) {
    border-color: var(--brand); color: var(--brand);
}

/* 聊天气泡 */
[data-testid="stChatMessage"] {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 0.85rem 1.1rem;
    margin: 0.5rem 0;
    box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
[data-testid="stChatMessage"] p {
    color: var(--ink);
    font-size: 0.94rem;
    line-height: 1.75;
    margin-bottom: 0.35rem;
}
[data-testid="stChatMessage"] p:last-child { margin-bottom: 0; }

/* 用户消息：主色底、白字、靠右 */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: var(--brand);
    border-color: var(--brand);
    flex-direction: row-reverse;
    margin-left: auto;
    max-width: 84%;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) li,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) code {
    color: #ffffff;
}
/* 用户消息里的链接、代码块底色也跟着调一下，避免糊成一团 */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) code {
    background: rgba(255, 255, 255, 0.18);
}

/* 头像：缩小并去掉默认灰底，视觉更干净 */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    width: 1.9rem; height: 1.9rem;
    background: transparent !important;
}

/* 进度提示（正在识别意图…） */
[data-testid="stCaptionContainer"] p, .stCaption {
    color: var(--ink-2) !important;
    font-size: 0.8rem !important;
}

/* 「查看处理过程」折叠面板 */
[data-testid="stExpander"] {
    border: 1px solid var(--line);
    border-radius: 10px;
    background: #fbfbfd;
    margin-top: 0.4rem;
}
[data-testid="stExpander"] summary p {
    font-size: 0.78rem; color: var(--ink-2); font-weight: 500;
}
[data-testid="stExpander"] pre {
    background: #f3f4f6; border-radius: 8px;
    border: none;
}
[data-testid="stExpander"] code {
    color: #374151; font-size: 0.78rem;
}

/* 输入框 */
[data-testid="stChatInput"] {
    border-radius: 14px;
    border: 1px solid var(--line);
    box-shadow: 0 2px 8px rgba(16, 24, 40, 0.06);
}
[data-testid="stChatInput"] textarea {
    color: var(--ink);
    font-size: 0.92rem;
}
[data-testid="stChatInput"] textarea::placeholder { color: #9ca3af; }

/* 分隔线 */
hr { border-color: var(--line); margin: 0.6rem 0 1rem 0; }
</style>""", unsafe_allow_html=True)

# ── 页头 ─────────────────────────────────────────────────────
st.markdown(
    '<div class="brand"><div class="brand-dot"></div>'
    '<span class="brand-name">电商智能客服</span></div>'
    '<div class="brand-sub">订单查询 · 物流追踪 · 退换货办理</div>',
    unsafe_allow_html=True,
)

# 后端地址走环境变量，本地直接跑用 localhost，容器里由 compose 指向 api 服务
API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
STREAM_URL = f"{API_BASE}/api/v1/chat/stream"

# ── 会话状态 ─────────────────────────────────────────────────
# 会话 ID 只生成一次，之后每轮请求都带上它
# 多轮上下文由后端按这个 ID 自己维护，前端不再传历史
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex

if "msgs" not in st.session_state:
    st.session_state.msgs = [
        {"role": "a", "text": "您好，我是智能客服助手，可以帮您查询订单、追踪物流、办理退换货。", "steps": None}
    ]
if "pq" not in st.session_state:
    st.session_state.pq = None


def thinking_text(steps):
    """把后端推来的进度事件拼成处理过程文本（中文文案由后端提供）"""
    if not steps:
        return ""
    lines = steps.get("progress", [])
    return "\n".join(f"●  {line}" for line in lines)


def iter_sse_events(resp):
    """把 SSE 响应逐行解析成事件字典（每行形如 `data: {json}`）"""
    for raw in resp.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        try:
            yield json.loads(line[len("data:"):].strip())
        except ValueError:
            continue


def call_api_stream(query, status_ph, body_ph):
    """
    消费后端的 SSE 流：进度提示写进 status_ph，回复正文逐字写进 body_ph。

    流结束后清空进度条、定格完整回复。
    返回（完整回复, 处理过程），处理过程为 None 时表示这一轮没有进度事件。
    """
    progress = []
    full = ""
    try:
        with requests.post(
            STREAM_URL,
            json={"message": query, "session_id": st.session_state.session_id},
            stream=True,
            timeout=120,
        ) as r:
            if r.status_code != 200:
                full = f"服务返回错误（{r.status_code}）。"
            else:
                for ev in iter_sse_events(r):
                    kind = ev.get("type")
                    if kind == "progress":
                        text = ev.get("content", "")
                        progress.append(text)
                        status_ph.caption(text)
                    elif kind == "token":
                        full += ev.get("content", "")
                        body_ph.markdown(full + "▌")
                    elif kind == "done":
                        full = ev.get("content", full)
                    elif kind == "error":
                        full = ev.get("content", "服务处理出错，请稍后重试。")
    except requests.exceptions.ConnectionError:
        full = "**无法连接后端服务。** 请先启动：`uvicorn src.main:app --reload`"
    except Exception as e:
        full = f"出错了：{e}"

    status_ph.empty()
    final = full or "抱歉，服务暂时没有返回结果。"
    body_ph.markdown(final)
    return final, ({"progress": progress} if progress else None)


# ── 快捷按钮 ─────────────────────────────────────────────────
actions = [
    ("查订单 ORD-1002", "帮我查一下订单 ORD-1002 的状态"),
    ("查物流 SF-78901234", "物流单号 SF-78901234 现在到哪了"),
    ("退货政策", "你们的退货政策是什么"),
    ("我的订单", "帮我查 james@example.com 的订单"),
]
cols = st.columns(4)
for i, (label, query) in enumerate(actions):
    with cols[i]:
        if st.button(label, use_container_width=True, key=f"qa_{i}"):
            st.session_state.pq = query
            st.rerun()
st.divider()

# ── 聊天历史 ─────────────────────────────────────────────────
for m in st.session_state.msgs:
    with st.chat_message("assistant" if m["role"] == "a" else "user"):
        st.markdown(m["text"])
        if m["role"] == "a" and m.get("steps"):
            tt = thinking_text(m["steps"])
            if tt:
                with st.expander("查看处理过程", expanded=False):
                    st.markdown(f"```\n{tt}\n```")

# ── 快捷查询处理 ─────────────────────────────────────────────
if st.session_state.pq:
    q = st.session_state.pq
    st.session_state.pq = None
    st.session_state.msgs.append({"role": "u", "text": q, "steps": None})
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        status_ph = st.empty()
        body_ph = st.empty()
        reply, steps = call_api_stream(q, status_ph, body_ph)
        if steps:
            tt = thinking_text(steps)
            if tt:
                with st.expander("查看处理过程", expanded=False):
                    st.markdown(f"```\n{tt}\n```")
        st.session_state.msgs.append({"role": "a", "text": reply, "steps": steps})
    st.rerun()

# ── 用户输入 ─────────────────────────────────────────────────
if prompt := st.chat_input("请输入您的问题..."):
    st.session_state.msgs.append({"role": "u", "text": prompt, "steps": None})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        status_ph = st.empty()
        body_ph = st.empty()
        reply, steps = call_api_stream(prompt, status_ph, body_ph)
        if steps:
            tt = thinking_text(steps)
            if tt:
                with st.expander("查看处理过程", expanded=False):
                    st.markdown(f"```\n{tt}\n```")
        st.session_state.msgs.append({"role": "a", "text": reply, "steps": steps})
