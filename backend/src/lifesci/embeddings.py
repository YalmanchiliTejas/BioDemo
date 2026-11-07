"""Text embeddings for memory recall. Production: the Modal service in backend/deploy/modal/embeddings_app.py (text
stays in our Modal workspace). Tests: a deterministic hashing embedder. Recall degrades to lexical when neither works."""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol

from .gateway.providers import modal_settings

TOKEN = re.compile(r'[a-z0-9]+')


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


class ModalEmbedder:
    """OpenAI-style /v1/embeddings behind Modal proxy auth (the wk-/ws- token, sent as Modal-Key / Modal-Secret)."""
    model = 'Qwen/Qwen3-Embedding-0.6B'

    def __init__(self, url: str, token: str, timeout_s: float = 60.) -> None:
        self.url, self.timeout = url.rstrip('/'), timeout_s
        self.key, _, self.secret = token.partition('.')

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        import httpx
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            r = httpx.post(self.url, json={'input': texts[i:i + 128], 'input_type': 'query' if query else 'document'},
                           headers={'Modal-Key': self.key, 'Modal-Secret': self.secret}, timeout=self.timeout)
            r.raise_for_status()
            out.extend(d['embedding'] for d in sorted(r.json()['data'], key=lambda d: d['index']))
        return out


class HashingEmbedder:
    """Deterministic bag-of-words vectors for tests and offline runs: similar wording, similar vector. Not semantic."""
    model = 'hashing-256'

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        vectors = []
        for text in texts:
            v = [0.0] * 256
            for token in TOKEN.findall(text.casefold()):
                v[int(hashlib.md5(token.encode()).hexdigest(), 16) % 256] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / norm for x in v])
        return vectors


def from_env(environ=None) -> Embedder | None:
    env = os.environ if environ is None else environ
    url = env.get('MODAL_EMBEDDINGS_URL', '').strip()
    token, _ = modal_settings(env)
    return ModalEmbedder(url, token) if url and token else None


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are stored normalized
