"""Dependency-free deterministic text embeddings for the prototype."""
from __future__ import annotations

import hashlib
import math
import re

DIMENSIONS = 96


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u0600-\u06ff]+", text.lower())


def generate_embedding(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DIMENSIONS
        sign = 1.0 if digest[4] % 2 else -1.0
        vector[index] += sign
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector
