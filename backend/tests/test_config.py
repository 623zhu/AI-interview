import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "SECRET_KEY": "s" * 40,
        "JWT_SECRET_KEY": "j" * 40,
        "DATABASE_URL": "mysql+aiomysql://root:strong-password@localhost:3306/ai_interview",
        "DATABASE_URL_SYNC": "mysql+pymysql://root:strong-password@localhost:3306/ai_interview",
        "DEEPSEEK_API_KEY": "sk-test",
        "SMTP_USER": "mail@example.com",
        "SMTP_PASSWORD": "smtp-secret",
        "SMTP_FROM": "mail@example.com",
        "CORS_ORIGINS": "https://app.example.com",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_debug_mode():
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        _production_settings(DEBUG=True)


def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        _production_settings(JWT_SECRET_KEY="dev-secret-change-in-production")


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="Wildcard CORS"):
        _production_settings(CORS_ORIGINS="https://app.example.com,*")


def test_production_rejects_demo_database_password():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        _production_settings(
            DATABASE_URL="mysql+aiomysql://root:root123456@localhost:3306/ai_interview",
        )


def test_production_accepts_complete_safe_configuration():
    settings = _production_settings()

    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is False
    assert settings.DEEPSEEK_MAX_RETRIES == 2
    assert settings.DEEPSEEK_TIMEOUT_SECONDS == 60
    assert settings.DEEPSEEK_CONNECT_TIMEOUT_SECONDS == 10
    assert settings.DEEPSEEK_READ_TIMEOUT_SECONDS == 60
    assert settings.LLM_RETRY_BACKOFF_BASE_SECONDS == 0.5
    assert settings.LLM_RETRY_BACKOFF_MAX_SECONDS == 5
    assert settings.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD == 5
    assert settings.LLM_CIRCUIT_BREAKER_RECOVERY_SECONDS == 60
