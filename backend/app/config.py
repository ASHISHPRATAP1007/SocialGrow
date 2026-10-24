"""App configuration — read from environment variables (and backend/.env when present)."""
import os
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


class Settings:
    APP_NAME = env("APP_NAME", "SocialGrow AI")
    # postgresql://user:pass@host/db  (Neon / Render / local). Falls back to a local SQLite file for development.
    DATABASE_URL = env("DATABASE_URL", "sqlite:///./socialgrow.db")
    JWT_SECRET = env("JWT_SECRET", "dev-only-insecure-secret-change-me-in-production")
    JWT_EXPIRE_DAYS = int(env("JWT_EXPIRE_DAYS", "7"))
    # Comma separated list of allowed frontend origins, e.g. https://socialgrow.vercel.app
    CORS_ORIGINS = [o.strip() for o in env("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    PUBLIC_API_URL = env("PUBLIC_API_URL", "http://localhost:8000")
    FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000")

    # AI: gemini (free tier) | openai | anthropic
    AI_PROVIDER = env("AI_PROVIDER", "gemini").lower()
    GEMINI_API_KEY = env("GEMINI_API_KEY")
    GEMINI_MODEL = env("GEMINI_MODEL", "gemini-3.8-flash")
    OPENAI_API_KEY = env("OPENAI_API_KEY")
    OPENAI_MODEL = env("OPENAI_MODEL", "gpt-4o-mini")
    ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-haiku-4-5")
    # Free backups — if the main AI fails, SocialGrow tries these automatically (only those with a key)
    GROQ_API_KEY = env("GROQ_API_KEY")
    GROQ_MODEL = env("GROQ_MODEL", "llama-3.3-70b-versatile")
    OPENROUTER_API_KEY = env("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = env("OPENROUTER_MODEL", "openrouter/free")

    # Email (password reset codes) — any SMTP, e.g. Gmail with an App Password
    SMTP_HOST = env("SMTP_HOST")
    SMTP_PORT = int(env("SMTP_PORT", "587"))
    SMTP_USER = env("SMTP_USER")
    SMTP_PASSWORD = env("SMTP_PASSWORD")
    SMTP_FROM = env("SMTP_FROM") or env("SMTP_USER")

    # Background jobs: built-in scheduler + secret for an external free cron (cron-job.org)
    ENABLE_SCHEDULER = env("ENABLE_SCHEDULER", "true").lower() == "true"
    CRON_SECRET = env("CRON_SECRET")


settings = Settings()
