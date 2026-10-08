"""
FastAPI 入口 — 应用启动文件
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.services.database import init_db
from src.observability.langfuse_setup import init_langfuse

# 日志配置
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 初始化数据库
init_db()

# 初始化可观测性链路：未配置时自动跳过，不影响服务启动
init_langfuse()

# 创建 FastAPI 应用
app = FastAPI(title="E-Commerce AI Agent", version="0.1.0")

# CORS — 允许 Streamlit 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.api.routes import router
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.api_host, port=settings.api_port, reload=True)
