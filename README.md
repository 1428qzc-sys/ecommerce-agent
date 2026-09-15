# E-Commerce AI Agent

电商客服 AI Agent，支持订单查询、物流追踪、退货处理。

## 技术栈

- **后端**: FastAPI + SQLAlchemy + SQLite
- **Agent 框架**: LangGraph + LangChain（开发中）
- **LLM**: DeepSeek（兼容 OpenAI 格式）
- **前端**: Streamlit（开发中）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env

# 3. 启动后端
uvicorn src.main:app --reload --port 8000
```

## 项目结构

```
ecommerce-agent/
├── src/
│   ├── agent/          # Agent 核心（开发中）
│   ├── services/       # 业务层（订单/物流/退货）
│   ├── api/            # FastAPI 接口（开发中）
│   ├── ui/             # Streamlit 前端（开发中）
│   ├── config.py       # 配置管理
│   └── main.py         # 入口
└── tests/              # 测试
```
