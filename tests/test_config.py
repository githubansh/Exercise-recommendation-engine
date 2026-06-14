from app.core.config import Settings


def test_postgresql_url_uses_installed_psycopg_driver() -> None:
    settings = Settings(database_url="postgresql://user:pass@example.com:5432/fitengine")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/fitengine"


def test_explicit_psycopg_url_is_preserved() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:pass@example.com:5432/fitengine")

    assert settings.database_url == "postgresql+psycopg://user:pass@example.com:5432/fitengine"


def test_runtime_embeddings_are_disabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.enable_runtime_embeddings is False


def test_gemini_model_default_is_real_model_identifier(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    settings = Settings(_env_file=None)

    assert settings.gemini_model == "gemini-1.5-flash"


def test_cors_origins_accepts_plural_env_name(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://ui-fit-engine.vercel.app")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == "https://ui-fit-engine.vercel.app"


def test_cors_origins_accepts_singular_env_name(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ORIGIN", "https://ui-fit-engine.vercel.app")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == "https://ui-fit-engine.vercel.app"
