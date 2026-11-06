from typing import Any, List, Optional, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "PRAGMATA"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Switch Collaboration
    SWITCH_BASE_URL: str = "http://localhost:8080"
    SWITCH_REGISTRATION_TOKEN: str = "pragmata_dev_token"
    SWITCH_ENABLED: bool = True

    # LLM Providers
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GEMINI_API_KEY: Optional[str] = None

    # Developer Authentication & Authorization (Phase 7)
    DEVELOPER_API_KEYS: List[str] = [
        "dev-secret-key-pragmata",
        "developer_test_token",
    ]
    DEVELOPER_DEFAULT_ID: str = "lead_developer"

    # GitHub & Repository Workspace (Phase 5)
    GITHUB_TOKEN: Optional[str] = None
    WORKSPACE_BASE_DIR: str = "/tmp/pragmata_workspaces"

    # Docker Sandbox (Phase 5 & 6)
    SANDBOX_DEFAULT_IMAGE: str = "python:3.11-alpine@sha256:bb1d70c1df30d8ee1e05214dbe82d6cdfd29833c1f47ce917f20991aca93acaa"
    SANDBOX_DEFAULT_TIMEOUT: int = 30
    SANDBOX_MAX_CPU: str = "1.0"
    SANDBOX_MAX_MEMORY: str = "512m"

    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "pragmata"
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pragmata"
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on", "debug", "dev")
        return False

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)


settings = Settings()
