<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const STORAGE_KEY = 'ecommerce-agent-sessions'

function newSessionId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'.replace(/x/g, () =>
    Math.floor(Math.random() * 16).toString(16)
  )
}

function welcomeMessage() {
  return {
    role: 'assistant',
    text: '您好，我是智能客服助手，可以帮您查询订单、追踪物流、办理退换货。请问有什么可以帮您？',
    steps: [],
    streaming: false,
  }
}

function createSession() {
  return {
    id: newSessionId(),
    title: '新的咨询',
    createdAt: Date.now(),
    messages: [welcomeMessage()],
  }
}

const demoOrders = [
  { label: '查订单 ORD-1002', text: '帮我查一下订单 ORD-1002 的状态', meta: '已发货 · ¥249.99', tag: '订单' },
  { label: '查物流 SF-78901234', text: '物流单号 SF-78901234 现在到哪了', meta: '已签收 · 顺丰速运', tag: '物流' },
  { label: '查订单 ORD-1001', text: '帮我查一下订单 ORD-1001 的状态', meta: '已送达 · ¥105.97', tag: '订单' },
  { label: '退货政策', text: '你们的退货政策是什么', meta: '签收后 14 天内可退', tag: '政策' },
]

function loadSessions() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (Array.isArray(saved) && saved.length) {
      return saved.map((s) => ({
        ...s,
        messages: (s.messages || []).map((m) => ({ ...m, steps: m.steps || [], streaming: false })),
      }))
    }
  } catch (e) {
    // 本地数据坏了就当没有，重新开一个
  }
  return [createSession()]
}

const sessions = ref(loadSessions())
const currentId = ref(sessions.value[0].id)
const current = computed(() => sessions.value.find((s) => s.id === currentId.value) || sessions.value[0])
const messages = computed(() => current.value.messages)

const input = ref('')
const streaming = ref(false)
const expanded = ref({})
const listEl = ref(null)
const search = ref('')
const showSidebar = ref(false)
let persistTimer = null

const filteredSessions = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return sessions.value
  return sessions.value.filter(
    (s) => s.title.toLowerCase().includes(keyword) || s.id.toLowerCase().includes(keyword)
  )
})

function persist() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(
      sessions.value.map((s) => ({
        id: s.id,
        title: s.title,
        createdAt: s.createdAt,
        messages: s.messages.map((m) => ({ role: m.role, text: m.text, steps: m.steps || [] })),
      }))
    )
  )
}

watch(
  sessions,
  () => {
    clearTimeout(persistTimer)
    persistTimer = setTimeout(persist, 200)
  },
  { deep: true }
)

const autoScroll = ref(true)

watch(
  messages,
  () => { if (autoScroll.value) nextTick(scrollToBottom) },
  { deep: true }
)

function scrollToBottom() {
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

function onListScroll() {
  const el = listEl.value
  if (!el) return
  // 距底部 60px 内视为「跟着最新」，往上翻时不强行拉回
  autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < 60
}

onMounted(() => nextTick(scrollToBottom))

function formatTime(ts) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function lastPreview(session) {
  const lastUser = [...session.messages].reverse().find((m) => m.role === 'user')
  if (!lastUser) return '新的咨询'
  return lastUser.text.replace(/\s+/g, ' ').slice(0, 22)
}

function switchSession(id) {
  if (streaming.value) return
  currentId.value = id
  expanded.value = {}
  showSidebar.value = false
  nextTick(scrollToBottom)
}

function startNewSession() {
  if (streaming.value) return
  const session = createSession()
  sessions.value.unshift(session)
  currentId.value = session.id
  expanded.value = {}
  search.value = ''
  showSidebar.value = false
  persist()
  nextTick(scrollToBottom)
}

function deleteSession(id) {
  if (streaming.value) return
  const index = sessions.value.findIndex((s) => s.id === id)
  if (index === -1) return
  sessions.value.splice(index, 1)
  if (!sessions.value.length) sessions.value.push(createSession())
  if (currentId.value === id) currentId.value = sessions.value[0].id
  expanded.value = {}
  fetch(`${API_BASE}/api/v1/chat/${id}`, { method: 'DELETE' }).catch(() => {})
  persist()
}

/** 解析 SSE 流：后端每次推一条 `data: {...}` + 空行 */
async function sendMessage(question) {
  const text = (question ?? input.value).trim()
  if (!text || streaming.value) return

  if (current.value.title === '新的咨询' || current.value.title === '新会话') {
    current.value.title = text.length > 16 ? `${text.slice(0, 16)}…` : text
  }

  input.value = ''
  autoScroll.value = true
  messages.value.push({ role: 'user', text, steps: [], streaming: false })
  const reply = { role: 'assistant', text: '', steps: [], streaming: true }
  messages.value.push(reply)
  // 新回复的执行轨迹默认展开，演示时直接看到 Agent 在做什么
  expanded.value[messages.value.length - 1] = true
  streaming.value = true

  try {
    const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: current.value.id }),
    })
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let splitAt = buffer.indexOf('\n\n')
      while (splitAt !== -1) {
        const block = buffer.slice(0, splitAt)
        buffer = buffer.slice(splitAt + 2)
        const dataLine = block.split('\n').find((line) => line.startsWith('data:'))
        if (dataLine) {
          try {
            const event = JSON.parse(dataLine.slice(5).trim())
            if (event.type === 'trace' || event.type === 'progress') {
              if (event.content) reply.steps.push(event)
            } else if (event.type === 'token') {
              reply.text += event.content || ''
            } else if (event.type === 'done') {
              reply.text = event.content || reply.text
            } else if (event.type === 'error') {
              reply.text = event.content || '服务处理出错，请稍后重试。'
            }
          } catch (e) {
            // 半包或者非 JSON 的事件直接丢掉，不影响后面正常字块
          }
        }
        splitAt = buffer.indexOf('\n\n')
      }
    }
  } catch (e) {
    reply.text = reply.text || '无法连接后端服务。请先启动 FastAPI：uvicorn src.main:app --reload'
  } finally {
    reply.streaming = false
    streaming.value = false
    persist()
    await nextTick()
    if (autoScroll.value) scrollToBottom()
  }
}

function toggleSteps(index) {
  expanded.value[index] = !expanded.value[index]
}
</script>

<template>
  <div class="page" :class="{ 'sidebar-open': showSidebar }">
    <aside class="sidebar">
      <div class="side-brand">
        <div class="side-brand-row">
          <span class="side-logo"></span>
          <span class="side-name">电商智能客服</span>
        </div>
        <div class="side-sub">订单查询 · 物流追踪 · 退换货办理</div>
      </div>

      <button class="new-chat" :disabled="streaming" @click="startNewSession">+ 新建会话</button>

      <div class="side-search">
        <input v-model="search" placeholder="搜索会话" />
      </div>

      <div class="side-list">
        <div
          v-for="session in filteredSessions"
          :key="session.id"
          class="side-item"
          :class="{ active: session.id === currentId }"
          @click="switchSession(session.id)"
        >
          <span class="side-avatar">{{ session.title.slice(0, 1) }}</span>
          <div class="side-meta">
            <div class="side-title">{{ session.title }}</div>
            <div class="side-preview">{{ lastPreview(session) }}</div>
          </div>
          <span class="side-time">{{ formatTime(session.createdAt) }}</span>
          <button class="side-del" :disabled="streaming" @click.stop="deleteSession(session.id)">×</button>
        </div>
        <div v-if="!filteredSessions.length" class="side-empty">没有找到会话</div>
      </div>

      <div class="side-foot">智能客服工作台 · v1.0</div>
    </aside>

    <main class="chat">
      <header class="chat-header">
        <button class="mobile-menu" @click="showSidebar = !showSidebar">会话</button>
        <div class="chat-title">{{ current.title }}</div>
        <div class="chat-status"><span class="online-dot"></span>智能客服在线</div>
      </header>

      <div ref="listEl" class="message-list" @scroll.passive="onListScroll">
        <div
          v-for="(msg, index) in messages"
          :key="index"
          class="row"
          :class="msg.role === 'user' ? 'row-user' : 'row-assistant'"
        >
          <div class="msg-avatar" :class="msg.role === 'user' ? 'avatar-user' : 'avatar-bot'">
            {{ msg.role === 'user' ? '客' : '智' }}
          </div>
          <div class="bubble" :class="msg.role === 'user' ? 'bubble-user' : 'bubble-assistant'">
            <div class="msg-role">{{ msg.role === 'user' ? '访客' : '智能客服' }}</div>
            <div class="text">{{ msg.text }}<span v-if="msg.streaming" class="cursor">▌</span></div>
            <div v-if="msg.steps.length" class="steps">
              <button class="steps-toggle" @click="toggleSteps(index)">
                <span class="steps-badge">AGENT</span>
                {{ expanded[index] ? '收起执行轨迹' : `查看 Agent 执行轨迹（${msg.steps.length} 步）` }}
                <span class="steps-caret">{{ expanded[index] ? '▴' : '▾' }}</span>
              </button>
              <div v-if="expanded[index]" class="steps-body">
                <div v-for="(step, i) in msg.steps" :key="i" class="trace-step" :class="'phase-' + (step.phase || 'progress')">
                  <span class="trace-index">{{ i + 1 }}</span>
                  <div class="trace-main">
                    <div class="trace-head">
                      <span v-if="typeof step === 'object' && step.agent" class="trace-agent">{{ step.agent }}</span>
                      <span class="trace-content">{{ typeof step === 'string' ? step : step.content }}</span>
                    </div>
                    <div v-if="step.args && Object.keys(step.args).length" class="trace-detail">
                      <span class="trace-key">入参</span>
                      <code v-for="(val, key) in step.args" :key="key" class="trace-arg">{{ key }} = {{ val }}</code>
                    </div>
                    <div v-if="step.result" class="trace-detail">
                      <span class="trace-key">返回</span><span class="trace-result">{{ step.result }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <button v-if="!autoScroll" class="jump-latest" @click="scrollToBottom(); autoScroll = true">
        ↓ 回到最新
      </button>

      <div class="quick-bar">
        <button
          v-for="item in demoOrders"
          :key="item.label"
          class="quick-chip"
          :disabled="streaming"
          @click="sendMessage(item.text)"
        >
          {{ item.label }}
        </button>
      </div>

      <footer class="composer">
        <textarea
          v-model="input"
          rows="1"
          placeholder="请输入您的问题，Enter 发送，Shift + Enter 换行"
          :disabled="streaming"
          @keydown.enter.exact.prevent="sendMessage()"
        ></textarea>
        <button class="send-btn" :disabled="streaming || !input.trim()" @click="sendMessage()">
          {{ streaming ? '回复中' : '发送' }}
        </button>
      </footer>
    </main>

    <aside class="info">
      <div class="info-card">
        <div class="info-card-title">客户信息</div>
        <div class="customer">
          <div class="customer-avatar">访</div>
          <div>
            <div class="customer-name">访客 {{ current.id.slice(0, 6) }}</div>
            <div class="customer-sub">网页在线咨询</div>
          </div>
        </div>
        <div class="info-kv"><span>会话状态</span><span>进行中</span></div>
        <div class="info-kv"><span>接入方式</span><span>智能客服</span></div>
        <div class="info-kv"><span>会话编号</span><span>{{ current.id.slice(0, 8) }}</span></div>
      </div>

      <div class="info-card">
        <div class="info-card-title">常用查询</div>
        <button
          v-for="item in demoOrders"
          :key="item.label"
          class="info-row"
          :disabled="streaming"
          @click="sendMessage(item.text)"
        >
          <span class="tag">{{ item.tag }}</span>
          <span class="info-row-main">{{ item.label }}</span>
          <span class="info-row-meta">{{ item.meta }}</span>
        </button>
      </div>

      <div class="info-card">
        <div class="info-card-title">服务说明</div>
        <p class="info-note">
          支持订单状态查询、物流追踪、退货政策咨询与退货资格校验。<br />
          服务时间 9:00 - 22:00，复杂问题将转接人工处理。
        </p>
      </div>
    </aside>
  </div>
</template>
