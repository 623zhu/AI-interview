"""Application configuration using pydantic-settings."""
from pathlib import Path
from urllib.parse import urlparse
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from functools import lru_cache

# Compute absolute path to .env regardless of CWD
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# Security-sensitive defaults that MUST be overridden in production
_DEV_SECRETS = {"dev-secret-key", "dev-secret-change-in-production"}
_DEMO_DB_PASSWORDS = {"root123456", "password", "123456", ""}


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AI-Interview"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
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
    DEEPSEEK_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0)
    DEEPSEEK_CONNECT_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
    DEEPSEEK_READ_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0)
    DEEPSEEK_MAX_RETRIES: int = Field(default=2, ge=0, le=5)
    LLM_RETRY_BACKOFF_BASE_SECONDS: float = Field(default=0.5, ge=0, le=30)
    LLM_RETRY_BACKOFF_MAX_SECONDS: float = Field(default=5.0, ge=0, le=60)
    INTERVIEW_AGENT_TIMEOUT_SECONDS: float = Field(default=90.0, gt=0)
    REACT_AGENT_RECURSION_LIMIT: int = Field(default=20, ge=5, le=100)
    LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=5, ge=1, le=100)
    LLM_CIRCUIT_BREAKER_RECOVERY_SECONDS: int = Field(default=60, ge=1, le=3600)

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
    def _validate_runtime_config(self):
        """Fail fast when production configuration is unsafe or incomplete."""
        env = self.ENVIRONMENT.lower()
        is_production = env in {"production", "prod"} or not self.DEBUG

        if is_production:
            if self.DEBUG:
                raise ValueError("DEBUG must be false in production.")
            if self.JWT_SECRET_KEY in _DEV_SECRETS or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError("JWT_SECRET_KEY must be a strong random value in production.")
            if self.SECRET_KEY in _DEV_SECRETS or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be a strong random value in production.")
            if not self.DEEPSEEK_API_KEY:
                raise ValueError("DEEPSEEK_API_KEY is required in production.")
            if not self.SMTP_USER or not self.SMTP_PASSWORD or not self.SMTP_FROM:
                raise ValueError("SMTP_USER, SMTP_PASSWORD, and SMTP_FROM are required in production.")
            if "*" in {o.strip() for o in self.CORS_ORIGINS.split(",")}:
                raise ValueError("Wildcard CORS origins are not allowed in production.")
            if not self.CORS_ORIGINS.strip():
                raise ValueError("CORS_ORIGINS must be configured in production.")
            if self.MAX_UPLOAD_SIZE_MB <= 0 or self.MAX_UPLOAD_SIZE_MB > 50:
                raise ValueError("MAX_UPLOAD_SIZE_MB must be between 1 and 50 in production.")
            self._validate_database_password(self.DATABASE_URL, "DATABASE_URL")
            self._validate_database_password(self.DATABASE_URL_SYNC, "DATABASE_URL_SYNC")
        return self

    @staticmethod
    def _validate_database_password(database_url: str, field_name: str) -> None:
        parsed = urlparse(database_url)
        if parsed.password in _DEMO_DB_PASSWORDS:
            raise ValueError(f"{field_name} must not use a demo or empty database password in production.")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
