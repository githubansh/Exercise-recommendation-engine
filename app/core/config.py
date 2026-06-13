from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FitEngine"
    database_url: str = "postgresql+psycopg://fitengine:fitengine@localhost:5432/fitengine"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    imagekit_base_url: str = "https://ik.imagekit.io/yuhonas"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    random_seed: int = 42

    @field_validator("database_url", mode="before")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
