from app.modules.catalog.service import CatalogService, cosine_vectors, vector_search_status


def test_cosine_vectors_scores_semantic_vectors() -> None:
    assert cosine_vectors([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_vectors([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_vectors([0.0, 0.0], [1.0, 0.0]) is None


def test_vector_search_skips_runtime_embeddings_by_default() -> None:
    service = CatalogService()

    assert service._vector_search(None, "push exercise", [object()], 5) is None
    assert vector_search_status() == "ok"
