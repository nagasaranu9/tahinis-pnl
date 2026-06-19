from typing import Annotated

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "Tahinis Financial Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Security
    JWT_PRIVATE_KEY: str  # RS256 PEM
    JWT_PUBLIC_KEY: str  # RS256 PEM
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: PostgresDsn
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: RedisDsn

    # Object Storage (S3 / Cloudflare R2)
    STORAGE_BUCKET: str
    STORAGE_ENDPOINT_URL: str | None = None  # set for R2 / MinIO
    STORAGE_PUBLIC_URL: str | None = None  # browser-reachable base URL to rewrite presigned URLs
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "us-east-1"

    # Token encryption key (AES-256 for integration credentials)
    CREDENTIAL_ENCRYPTION_KEY: str  # 32-byte base64-encoded key

    # OCR adapter selection: "auto" (Google if configured else Claude),
    # "google" (Document AI — cheap), "claude" (Vision — pricey), "tesseract"
    # (free local), "mock". Default "auto" avoids burning Anthropic credits when
    # Google Document AI is configured.
    OCR_ADAPTER: str = "auto"

    # Google
    GOOGLE_DOC_AI_PROJECT_ID: str = ""
    GOOGLE_DOC_AI_LOCATION: str = "us"
    GOOGLE_DOC_AI_PROCESSOR_ID: str = ""
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""

    # Pipeboard (Google/Meta/TikTok Ads via MCP). Token is per-tenant in DB.
    PIPEBOARD_ADAPTER: str = "mock"  # "http" in prod, "mock" for dev/tests

    # Microsoft (Outlook only — no OneDrive)
    MICROSOFT_OAUTH_CLIENT_ID: str = ""
    MICROSOFT_OAUTH_CLIENT_SECRET: str = ""
    MICROSOFT_TENANT_ID: str = "common"

    # Toast
    TOAST_API_BASE_URL: str = "https://ws-api.toasttab.com"
    TOAST_CLIENT_ID: str = ""
    TOAST_CLIENT_SECRET: str = ""

    # Virus scanning (ClamAV)
    CLAMAV_HOST: str = ""  # empty = skip AV scan (dev/test)
    CLAMAV_PORT: int = 3310
    CLAMAV_STRICT: bool = False  # True = reject upload if ClamAV unreachable

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # Rate limiting
    RATE_LIMIT_LOGIN_PER_5MIN: int = 10

    # CORS
    # NoDecode: skip pydantic's eager JSON parse so the before-validator below
    # receives the raw env string and can split comma-separated values.
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # URLs
    FRONTEND_URL: str = "http://localhost:3000"
    API_BASE_URL: str = "http://localhost:8000"

    # SMTP (location invite emails) — empty SMTP_HOST = no-op send, invite link is logged + returned in API response
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@tahinis.app"
    SMTP_USE_TLS: bool = True

    # Resend HTTP API (preferred on Railway — outbound SMTP ports 25/465/587 are blocked).
    # Set RESEND_API_KEY=re_... and email goes over HTTPS:443 instead of SMTP.
    RESEND_API_KEY: str = ""

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: object) -> object:
        # Accept comma-separated string (Railway-friendly) in addition to JSON array.
        # "https://a.com,https://b.com" -> ["https://a.com", "https://b.com"]
        if isinstance(v, str):
            s = v.strip()
            if not s.startswith("["):
                return [origin.strip() for origin in s.split(",") if origin.strip()]
        return v

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        # Railway injects DATABASE_URL with postgres:// — normalize to postgresql+asyncpg://
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


settings = Settings()  # type: ignore[call-arg]  # env vars supply required fields
