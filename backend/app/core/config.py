"""Application configuration using pydantic-settings."""
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache

# Compute absolute path to .env regardless of CWD
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# Security-sensitive defaults that MUST be overridden in production
_DEV_SECRETS = {"dev-secret-key", "dev-secret-change-in-production"}


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AI-Interview"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key"  # General purpose secret key

    # Database
    DATABASE_URL: str = "mysql+aiomysql://root:root123456@localhost:3306/ai_interview?charset=utf8mb4"
    DATABASE_URL_SYNC: str = "mysql+pymysql://root:root123456@localhost:3306/ai_interview?charset=utf8mb4"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Chroma
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # DeepSeek LLM
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Ollama Embedding
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    EMBEDDING_MODEL: str = "bge-m3"

    # Reranker (in-process FlagEmbedding cross-encoder)
    # Ollama does not expose cross-encoder rerank; we load BGE reranker locally.
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # SMTP Email
    SMTP_HOST: str = "smtp.qq.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

    model_config = {"env_file": str(_ENV_PATH), "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def _warn_dev_secrets(self):
        """Warn if default dev secrets are used in non-debug mode."""
        if not self.DEBUG:
            if self.JWT_SECRET_KEY in _DEV_SECRETS:
                raise ValueError(
                    "JWT_SECRET_KEY is still set to the dev default. "
                    "Set a strong random key via .env for production."
                )
            if self.SECRET_KEY in _DEV_SECRETS:
                raise ValueError(
                    "SECRET_KEY is still set to the dev default. "
                    "Set a strong random key via .env for production."
                )
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
