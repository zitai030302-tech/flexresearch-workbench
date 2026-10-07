import numpy as np
import pytest

from flexresearch.retrieval import EMBEDDING_DIMENSION, cosine_scores, deserialize_embedding, embed_text, serialize_embedding


def test_sparse_embedding_is_deterministic_normalized_and_round_trips():
    first = embed_text("Bio-Z 多通道脉搏波")
    second = embed_text("Bio-Z 多通道脉搏波")
    assert first.shape == (EMBEDDING_DIMENSION,)
    assert np.array_equal(first, second)
    assert np.linalg.norm(first) == pytest.approx(1.0)
    assert np.array_equal(deserialize_embedding(serialize_embedding(first)), first)


def test_sparse_cosine_prefers_matching_lab_text():
    candidates = [embed_text("运动伪差去除与脉搏波信号质量"), embed_text("柔性光电探测器暗电流")]
    scores = cosine_scores("脉搏波运动伪差", [serialize_embedding(item) for item in candidates])
    assert scores[0] > scores[1]


def test_malformed_stored_vector_fails_instead_of_silently_scoring():
    with pytest.raises(ValueError, match="stored embedding"):
        deserialize_embedding(b"bad")

