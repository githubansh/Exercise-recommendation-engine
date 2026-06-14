import json

from seeds.load_seeds import load_precomputed_embeddings


def test_load_precomputed_embeddings_returns_mapping(tmp_path) -> None:
    path = tmp_path / "embeddings.json"
    path.write_text(json.dumps([["Pushup", [0.1, 0.2]], ["Squat", [0.3, 0.4]]]), encoding="utf-8")

    assert load_precomputed_embeddings(path) == {
        "Pushup": [0.1, 0.2],
        "Squat": [0.3, 0.4],
    }


def test_load_precomputed_embeddings_returns_empty_mapping_when_missing(tmp_path) -> None:
    assert load_precomputed_embeddings(tmp_path / "missing.json") == {}
