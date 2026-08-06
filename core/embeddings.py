"""Local, offline embedding generation for theme clustering — no external embedding API
or second API key required. The heavy `sentence-transformers` import is deferred until the
model is actually needed so importing this module (or running tests against a fake embedder)
stays fast.
"""
from functools import lru_cache
from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, normalize_embeddings=True))


@lru_cache(maxsize=1)
def get_default_embedder() -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder()
