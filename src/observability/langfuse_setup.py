"""
Langfuse 可观测性 — 追踪 Agent 调用链、评估质量、统计成本
可选功能：在 .env 中配置 Langfuse key 后自动启用
"""
import logging
import os

from src.config import settings

logger = logging.getLogger(__name__)

_client = None
_handler = None


def _is_configured() -> bool:
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def init_langfuse():
    """启动时调用一次 — 设置环境变量，初始化 client 和 handler"""
    global _client, _handler
    if _client is not None:
        return
    if not _is_configured():
        logger.info("Langfuse not configured — tracing disabled.")
        return

    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host

    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    _client = Langfuse()
    _handler = CallbackHandler()
    logger.info("Langfuse tracing enabled → %s", settings.langfuse_host)


def get_langfuse_handler():
    return _handler


def build_trace_config() -> dict:
    """
    生成传给图调用的 config。

    没配 key 时返回空字典，调用方照常传参即可，不用到处判断 None。
    """
    return {"callbacks": [_handler]} if _handler is not None else {}


def get_langfuse_client():
    return _client
