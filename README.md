# E-Commerce AI Agent

基于 LangGraph 的电商客服 AI Agent。主管 Agent 负责意图识别与派单，订单 / 退货 / 通用三个专员 Agent 各带自己的工具集处理具体业务，支持多轮对话、流式输出与端到端评测。

> 持续开发中。

## 核心特性

- **多 Agent 协作**：主管（supervisor）识别意图后派单给对应专员，专员之间可转接，主管汇总各方回复后统一答复
- **工具调用护栏**：ReAct 循环上限 5 次、转接上限 3 次，避免模型陷入死循环或无限转接
- **会话状态收敛到后端**：前端只发 `session_id`，多轮历史由后端会话存储维护
- **流式响应**：`/chat/stream` 以 SSE 推送节点进度与专员回复字块
- **端到端评测**：11 条黄金用例，从意图、派单、工具、答案四个维度断言，通过率不达标直接让 CI 失败
- **可观测性**：接入 Langfuse 记录每次调用的完整链路，未配置时自动跳过
- **容器化**：Dockerfile + docker-compose，一条命令起服务

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 后端框架 | FastAPI + SQLAlchemy + SQLite |
| Agent 编排 | LangGraph + LangChain |
| 大模型 | DeepSeek（兼容 OpenAI 接口格式） |
| 前端 | Streamlit |
| 可观测性 | Langfuse |
| 部署 | Docker / Docker Compose |

## 快速开始

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env

# 3. 启动后端
uvicorn src.main:app --reload --port 8000

# 4. 启动前端（另开一个终端）
streamlit run src/ui/streamlit_app.py
```

### Docker 运行

```bash
docker-compose up -d
```

服务启动后访问 `http://localhost:8000/docs` 查看接口文档。

## 架构

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
  ┌────────────┐  ┌────────────┐  ┌──────────────┐
  │order_      │  │return_     │  │general_      │
  │specialist  │  │specialist  │  │specialist    │
  └─────┬──────┘  └─────┬──────┘  └──────────────┘
        │ ReAct 循环     │ ReAct 循环
        ▼                ▼
   order_tools      return_tools
        └────────┬───────┘
                 ▼
            ┌─────────┐
            │ response│  汇总专员回复，生成最终答复
            └─────────┘
```

状态通过共享 `AgentState` 传递：专员只往 `specialist_replies` 里追加自己的结论，主管派的活写在 `task` 字段上，避免转接时丢失任务上下文。

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
| POST | `/chat` | 同步对话，返回完整答复 |
| POST | `/chat/stream` | SSE 流式对话，推送节点进度与字块 |
| DELETE | `/chat/{session_id}` | 清空指定会话 |
| GET | `/health` | 健康检查 |

## 评测

评测走完整链路（triage → supervisor → 专员 → response），每条用例同时校验意图分类、派单目标、工具调用与答案关键词，另设负例关键词防止模型编造信息。

```bash
python -m evals.runner                    # 跑全部用例
python -m evals.runner --category order   # 只跑某一类
python -m evals.runner --verbose          # 打印每条的实际回复
python -m evals.runner --threshold 0.9    # 自定义通过率下限，不达标返回非零退出码
```

可直接接入 CI：`python -m evals.runner` 退出码非 0 即判定本次改动不合格。

## 测试

```bash
pytest tests/ -v
```

## 项目结构

```
ecommerce-agent/
├── src/
│   ├── agent/          # Agent 核心：状态、节点、图、工具
│   │   ├── state.py    # 共享状态定义
│   │   ├── nodes.py    # triage / supervisor / 专员 / response
│   │   ├── graph.py    # StateGraph 与条件边
│   │   └── tools.py    # 业务工具与专员工具集
│   ├── services/       # 业务层：订单 / 物流 / 退货 / 会话
│   ├── api/            # FastAPI 路由与请求响应模型
│   ├── ui/             # Streamlit 前端
│   ├── observability/  # Langfuse 接入
│   ├── config.py       # 配置管理
│   └── main.py         # 入口
├── evals/              # 端到端评测集与跑分器
├── tests/              # 单元测试与集成测试
├── Dockerfile
└── docker-compose.yml
```

## 环境变量

复制 `.env.example` 为 `.env` 后按需填写，主要配置项：

| 变量 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | 大模型接口密钥，DeepSeek 的 key 也填这里 |
| `OPENAI_BASE_URL` | 接口地址，默认 DeepSeek；换成 OpenAI 地址即可切换厂商 |
| `MODEL_NAME` | 模型名称，默认 `deepseek-chat` |
| `TEMPERATURE` | 采样温度，默认 0，保证回答稳定 |
| `API_HOST` / `API_PORT` | 服务监听地址与端口 |
| `LANGFUSE_PUBLIC_KEY` | Langfuse 公钥，留空则不启用追踪 |
| `LANGFUSE_SECRET_KEY` | Langfuse 私钥 |
| `LANGFUSE_HOST` | Langfuse 服务地址 |
