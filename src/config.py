"""
Configuration — 集中管理所有环境变量
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM 配置 — 默认 DeepSeek，支持切换 OpenAI
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    model_name: str = "deepseek-chat"
    temperature: float = 0.0

    @property
    def effective_api_key(self) -> str:
        """优先使用 DEEPSEEK_API_KEY，否则用 OPENAI_API_KEY"""
        return self.deepseek_api_key or self.openai_api_key

    # API 服务配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # PostgreSQL 连接串（SQLAlchemy 格式）
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ecommerce_agent"
    reset_db_on_start: bool = False

    # 前后端分离后，允许访问接口的前端地址（逗号分隔）
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Langfuse 可观测性（可选） 
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
