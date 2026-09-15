"""
FastAPI 入口 — 应用启动文件
类比 Java: 相当于 Spring Boot 的 @SpringBootApplication main 方法
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.services.database import init_db

# 日志配置
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 初始化数据库
init_db()

# 创建 FastAPI 应用
app = FastAPI(title="E-Commerce AI Agent", version="0.1.0")

# CORS — 允许 Streamlit 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO: 添加 API 路由
# from src.api.routes import router
# app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.api_host, port=settings.api_port, reload=True)
