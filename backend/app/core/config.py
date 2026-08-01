"""Application configuration loaded from backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 查找.env目录
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
_DEV_SECRETS = {"dev-secret-key", "dev-secret-change-in-production"}
_DEMO_DB_PASSWORDS = {"root123456", "password", "123456", ""}


class Settings(BaseSettings):
    APP_NAME: str = "AI-Interview"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    LOG_FILE_MAX_BYTES: int = Field(default=10 * 1024 * 1024, ge=1024)
    LOG_FILE_BACKUP_COUNT: int = Field(default=5, ge=0, le=100)
    SECRET_KEY: str = "dev-secret-key"

    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    REDIS_URL: str

    LANGGRAPH_CHECKPOINTER_BACKEND: Literal["redis", "memory"] = "redis"
    LANGGRAPH_CHECKPOINT_TTL_MINUTES: int = Field(
        default=7 * 24 * 60,
        ge=60,
        le=90 * 24 * 60,
    )

    CHROMA_PERSIST_DIR: str = "./chroma_data"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0)
    DEEPSEEK_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    DEEPSEEK_READ_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0)
    DEEPSEEK_MAX_RETRIES: int = Field(default=2, ge=0, le=5)
    LLM_RETRY_BACKOFF_BASE_SECONDS: float = Field(default=0.5, ge=0, le=30)
    LLM_RETRY_BACKOFF_MAX_SECONDS: float = Field(default=5.0, ge=0, le=60)
    LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=5, ge=1, le=100)
    LLM_CIRCUIT_BREAKER_RECOVERY_SECONDS: int = Field(default=60, ge=1, le=3600)

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    EMBEDDING_MODEL: str = "bge-m3"
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"

    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, ge=5, le=60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1, le=30)
    VERIFICATION_HMAC_SECRET: str = Field(min_length=32)

    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = Field(default=10, gt=0, le=50)

    EMAIL_DELIVERY_MODE: Literal["console", "smtp"] = "console"
    SMTP_HOST: str = "smtp.qq.com"
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

    CORS_ORIGINS: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # cors_origin_list —— 把字符串拆成列表
    @property #把方法伪装成属性来访问
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self

        if self.DEBUG:
            raise ValueError("DEBUG must be false in production")

        if self.JWT_SECRET_KEY in _DEV_SECRETS or len(self.JWT_SECRET_KEY) < 32:
            raise ValueError("JWT_SECRET_KEY must be a strong random value in production")

        if self.SECRET_KEY in _DEV_SECRETS or len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be a strong random value in production")

        if not self.DEEPSEEK_API_KEY:
            raise ValueError("DEEPSEEK_API_KEY is required in production")

        if self.EMAIL_DELIVERY_MODE != "smtp":
            raise ValueError(
                "EMAIL_DELIVERY_MODE must be smtp in production"
            )

        if not all((self.SMTP_USER, self.SMTP_PASSWORD, self.SMTP_FROM)):
            raise ValueError(
                "SMTP credentials are required in production"
            )

        if "*" in self.cors_origin_list:
            raise ValueError(
                "Wildcard CORS origin is forbidden in production"
            )

        self._validate_database_password(self.DATABASE_URL, "DATABASE_URL")
        self._validate_database_password(self.DATABASE_URL_SYNC, "DATABASE_URL_SYNC")

        return self

    @staticmethod
    def _validate_database_password(database_url: str, field_name: str) -> None:
        if urlparse(database_url).password in _DEMO_DB_PASSWORDS:
            raise ValueError(
                f"{field_name} must not use a demo or empty database password in production"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
