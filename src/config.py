"""
Configuration — 集中管理所有环境变量
类比 Java: 相当于 Spring Boot 的 application.yml + @ConfigurationProperties
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM 配置 — 支持 OpenAI 和 DeepSeek（DeepSeek 兼容 OpenAI 格式）
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.0

    # API 服务配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Langfuse 可观测性（可选）
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
