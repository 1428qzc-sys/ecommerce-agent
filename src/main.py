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

# 初始化数据库：业务表 + 会话表（会话表独立，重置业务表不会影响历史对话）
init_db()
from src.services.session_service import init_session_table
init_session_table()

# 初始化可观测性链路：未配置时自动跳过，不影响服务启动
init_langfuse()

# 创建 FastAPI 应用
app = FastAPI(title="E-Commerce AI Agent", version="0.1.0")

# CORS — 前后端分离后只允许配置里的 Vue 前端地址访问
allowed_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", include_in_schema=False)
async def root():
    """根路径给个提示，避免浏览器打开后端地址时看到裸的 404"""
    return {
        "message": "E-Commerce AI Agent API",
        "docs": "/docs",
        "frontend": "http://localhost:5173",
    }


from src.api.routes import router
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=settings.api_host, port=settings.api_port, reload=True)
