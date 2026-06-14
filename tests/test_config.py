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
