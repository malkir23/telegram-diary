from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    diary_service_url: str = Field(
        default="http://localhost:8080", alias="DIARY_SERVICE_URL"
    )
    diary_service_api_key: str = Field(alias="DIARY_SERVICE_API_KEY")
    reminder_poll_seconds: int = Field(default=30, alias="REMINDER_POLL_SECONDS")


settings = BotSettings()
