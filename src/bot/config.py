import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be integer") from exc


@dataclass(frozen=True)
class BotSettings:
    telegram_bot_token: str
    reminder_poll_seconds: int


settings = BotSettings(
    telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
    reminder_poll_seconds=_env_int("REMINDER_POLL_SECONDS", 30),
)
