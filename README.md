# E-Commerce AI Agent

基于 LangGraph 的电商客服 AI Agent。采用前后端分离架构：Vue 3 负责交互界面，FastAPI 提供接口与 Agent 能力，PostgreSQL 统一存放业务数据和会话记录。

## 核心特性

- **前后端分离**：Vue 3 + Vite 独立工程，通过 HTTP / SSE 调用后端，不再由 Python 渲染页面
- **多 Agent 协作**：主管（supervisor）识别意图并派单，订单 / 退货 / 通用三个专员各带自己的工具集处理业务，支持转接
- **工具调用护栏**：ReAct 循环上限 5 次、转接上限 3 次，避免死循环或无限转接
- **后端会话记忆**：前端只传 `session_id`，多轮历史由后端按会话存 PostgreSQL
- **执行轨迹可视化**：`/chat/stream` 以 SSE 推送 `trace` 事件，逐条展示「意图识别 → 主管派单 → 专员处理 → 工具调用（含入参与返回）→ 收尾」的完整链路；前端每条回复下方可展开「Agent 执行轨迹」，多智能体协作过程一眼可见，适合论文演示
- **端到端评测**：11 条黄金用例，校验意图、派单、工具、答案四个维度
- **可观测性**：接入 Langfuse 记录完整链路，未配置时自动跳过
- **容器化**：PostgreSQL + FastAPI + Vue 3（nginx）一条命令起全栈

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 前端 | Vue 3 + Vite |
| 后端框架 | FastAPI |
| 数据库 | PostgreSQL 16 + SQLAlchemy + psycopg 3 |
| Agent 编排 | LangGraph + LangChain |
| 大模型 | DeepSeek（兼容 OpenAI 接口格式） |
| 可观测性 | Langfuse |
| 部署 | Docker / Docker Compose |

## 快速开始

### 1. 准备 PostgreSQL

本地安装 PostgreSQL 后建库：

```sql
CREATE DATABASE ecommerce_agent;
```

登录密码按 `.env` 里的 `DATABASE_URL` 配置，默认是 `postgres / postgres`。

### 2. 配置环境变量

```bash
cp .env.example .env
# 按实际情况填 OPENAI_API_KEY（DeepSeek 的 key 也填这里）和 DATABASE_URL
```

### 3. 启动后端

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

接口文档：`http://localhost:8000/docs`

### 4. 启动前端（另开一个终端）

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 `http://localhost:5173`。开发时 Vite 把 `/api` 请求代理到 `http://localhost:8000`，代理地址可用 `frontend/.env` 里的 `VITE_API_TARGET` 修改。

### 5. Docker 一键启动

```bash
docker compose up -d --build
```

| 服务 | 地址 |
| --- | --- |
| Vue 前端 | http://localhost:5173 |
| FastAPI 接口文档 | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

数据库数据存在名为 `pgdata` 的 volume 里，容器重建不会丢。

## 架构

```
┌──────────────┐   HTTP / SSE    ┌──────────────┐   SQLAlchemy   ┌────────────┐
│  Vue 3 前端  │ ───────────────▶│  FastAPI 后端│ ──────────────▶│ PostgreSQL │
│  (Vite/nginx)│ ◀───────────────│   + LangGraph│                 └────────────┘
└──────────────┘   流式字块       └──────┬───────┘
                                         ▼
                     triage → supervisor → 专员 → response
```

Agent 内部流程：

```
                    ┌──────────┐
   用户消息 ───────▶│  triage  │  意图识别（LLM + 正则兜底）
                    └────┬─────┘
                         ▼
                    ┌──────────┐
                    │supervisor│  派单 / 转接 / 收尾
                    └────┬─────┘
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
  order_specialist  return_specialist  general_specialist
        │ ReAct 循环     │ ReAct 循环
        ▼                ▼
   order_tools      return_tools
        └────────┬───────┘
                 ▼
            ┌─────────┐
            │ response│  汇总专员回复，生成最终答复
            └─────────┘
```

状态通过共享 `AgentState` 传递：专员只往 `specialist_replies` 追加结论，主管派的活写在 `task` 字段上，转接时不丢任务上下文。

## 数据表

| 表 | 说明 |
| --- | --- |
| `customers` | 客户 |
| `orders` | 订单 |
| `order_items` | 订单商品 |
| `shipments` | 物流单 |
| `chat_messages` | 会话历史（只存 human / ai 两种角色） |

`chat_messages` 独立管理：重置业务表时不会把对话历史一起清掉。

## 工具清单

| 工具 | 职责 | 归属专员 |
| --- | --- | --- |
| `lookup_order` | 按订单号查订单 | order |
| `lookup_orders_by_email` | 按邮箱查名下订单 | order |
| `search_orders` | 按关键词搜索订单 | order |
| `track_shipment` | 按运单号查物流 | order |
| `get_return_policy` | 查询退货政策 | return |
| `check_return_eligibility` | 校验订单是否可退 | return |
| `initiate_return` | 发起退货并计算退款 | return |

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/chat` | 同步对话，返回完整答复 |
| POST | `/api/v1/chat/stream` | SSE 流式对话，推送进度与字块 |
| DELETE | `/api/v1/chat/{session_id}` | 清空指定会话 |
| GET | `/api/v1/health` | 健康检查 |

## 评测

评测走完整链路（triage → supervisor → 专员 → response），每条用例同时校验意图分类、派单目标、工具调用与答案关键词，另设负例关键词防止模型编造信息。

```bash
python -m evals.runner                    # 跑全部用例
python -m evals.runner --category order   # 只跑某一类
python -m evals.runner --verbose          # 打印每条的实际回复
python -m evals.runner --threshold 0.9    # 自定义通过率下限
```

## 测试

```bash
pytest tests/ -v
```

测试前会用种子数据重置业务表，因此需要 PostgreSQL 可连接。

## 项目结构

```
ecommerce-agent/
├── frontend/              # Vue 3 前端工程
│   ├── src/
│   │   ├── App.vue        # 客服工作台（会话列表 / 聊天 / 客户信息三栏）+ SSE 消费
│   │   ├── main.js
│   │   └── style.css
│   ├── Dockerfile         # 多阶段构建，nginx 托管
│   └── nginx.conf         # 静态资源 + /api 反向代理
├── src/
│   ├── agent/             # Agent 核心：状态、节点、图、工具
│   ├── services/          # 业务层 + PostgreSQL 数据访问
│   ├── api/               # FastAPI 路由与请求响应模型
│   ├── observability/     # Langfuse 接入
│   ├── config.py          # 配置管理
│   └── main.py            # 入口
├── evals/                 # 端到端评测集与跑分器
├── tests/                 # 单元测试与集成测试
├── Dockerfile
└── docker-compose.yml     # db + api + web
```

## 环境变量

复制 `.env.example` 为 `.env` 后按需填写，主要配置项：

| 变量 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | 大模型接口密钥，DeepSeek 的 key 也填这里 |
| `OPENAI_BASE_URL` | 接口地址，默认 DeepSeek |
| `MODEL_NAME` | 模型名称，默认 `deepseek-chat` |
| `TEMPERATURE` | 采样温度，默认 0 |
| `API_HOST` / `API_PORT` | 服务监听地址与端口 |
| `DATABASE_URL` | PostgreSQL 连接串，SQLAlchemy 格式 |
| `RESET_DB_ON_START` | 启动时是否清空并重建演示数据，默认 false |
| `CORS_ORIGINS` | 允许访问接口的前端地址，逗号分隔 |
| `LANGFUSE_PUBLIC_KEY` | Langfuse 公钥，留空则不启用追踪 |
| `LANGFUSE_SECRET_KEY` | Langfuse 私钥 |
| `LANGFUSE_HOST` | Langfuse 服务地址 |
