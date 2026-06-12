from app.modules.catalog.service import cosine_vectors


def test_cosine_vectors_scores_semantic_vectors() -> None:
    assert cosine_vectors([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_vectors([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_vectors([0.0, 0.0], [1.0, 0.0]) is None
