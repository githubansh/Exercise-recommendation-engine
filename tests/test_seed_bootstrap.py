from seeds.bootstrap import env_enabled, missing_seed_parts


def test_env_enabled_defaults_when_value_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("FORCE_SEED_DATA", raising=False)

    assert env_enabled("FORCE_SEED_DATA") is False
    assert env_enabled("FORCE_SEED_DATA", default=True) is True


def test_env_enabled_accepts_common_truthy_values(monkeypatch) -> None:
    monkeypatch.setenv("FORCE_SEED_DATA", "YES")

    assert env_enabled("FORCE_SEED_DATA") is True


def test_missing_seed_parts_detects_empty_catalog() -> None:
    counts = {
        "exercises": 0,
        "embeddings": 0,
        "patterns": 0,
        "injury_profiles": 0,
        "contraindications": 0,
    }

    assert missing_seed_parts(counts) == [
        "exercises",
        "embeddings",
        "patterns",
        "injury_profiles",
        "contraindications",
    ]


def test_missing_seed_parts_detects_partial_embedding_coverage() -> None:
    counts = {
        "exercises": 800,
        "embeddings": 200,
        "patterns": 1200,
        "injury_profiles": 8,
        "contraindications": 20,
    }

    assert missing_seed_parts(counts) == ["embedding coverage"]


def test_missing_seed_parts_skips_complete_seed_data() -> None:
    counts = {
        "exercises": 800,
        "embeddings": 800,
        "patterns": 1200,
        "injury_profiles": 8,
        "contraindications": 20,
    }

    assert missing_seed_parts(counts) == []
