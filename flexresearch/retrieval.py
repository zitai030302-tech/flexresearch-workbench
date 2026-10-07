"""Deterministic local sparse embeddings for a small laboratory vault.

This is deliberately not advertised as a neural semantic embedding model. It
uses character n-gram hashing so Chinese/English technical fragments can be
ranked without sending private documents to an external API. SQLite stores the
fixed-width vectors; BM25 remains the complementary lexical retriever.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer


EMBEDDING_MODEL_ID = "sklearn-hashing-char-2-4-v1"
EMBEDDING_DIMENSION = 2048


_VECTORIZER = HashingVectorizer(
    analyzer="char",
    ngram_range=(2, 4),
    n_features=EMBEDDING_DIMENSION,
    alternate_sign=False,
    lowercase=True,
    norm="l2",
)


def embed_text(text: str) -> np.ndarray:
    """Return a deterministic, normalized float32 sparse-hash embedding."""
    return _VECTORIZER.transform([text]).toarray()[0].astype(np.float32)


def serialize_embedding(vector: np.ndarray) -> bytes:
    array = np.asarray(vector, dtype=np.float32)
    if array.shape != (EMBEDDING_DIMENSION,):
        raise ValueError(f"embedding must have shape ({EMBEDDING_DIMENSION},)")
    return array.tobytes(order="C")


def deserialize_embedding(raw: bytes, dimension: int = EMBEDDING_DIMENSION) -> np.ndarray:
    try:
        vector = np.frombuffer(raw, dtype=np.float32)
    except ValueError as exc:
        raise ValueError("stored embedding byte length is invalid") from exc
    if len(vector) != dimension:
        raise ValueError(f"stored embedding has {len(vector)} values, expected {dimension}")
    return vector


def cosine_scores(query: str, vectors: Iterable[bytes]) -> list[float]:
    """Score normalized stored vectors; malformed vectors fail explicitly."""
    query_vector = embed_text(query)
    return [float(np.dot(query_vector, deserialize_embedding(raw))) for raw in vectors]

