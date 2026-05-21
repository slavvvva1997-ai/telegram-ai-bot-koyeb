from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    public_url: str = Field(default="", alias="PUBLIC_URL")
    database_url: str = Field(default="sqlite:///bot.db", alias="DATABASE_URL")
    openai_model: str = Field(default="gpt-5-mini", alias="OPENAI_MODEL")
    admin_telegram_ids: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admin_ids(self) -> set[int]:
        ids: set[int] = set()
        for raw in self.admin_telegram_ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                ids.add(int(raw))
        return ids

    @property
    def database_mode(self) -> str:
        if self.database_url.startswith("postgres"):
            return "postgresql"
        if self.database_url.startswith("sqlite"):
            return "sqlite"
        return "unknown"


@lru_cache
def get_settings() -> Settings:
    return Settings()
