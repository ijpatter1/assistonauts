"""Embedding generation, chunking, and keyword extraction for the Archivist."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter

# Common English stop words for keyword filtering
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could and but or nor for "
    "yet so at by from in into of on to with as it its this that "
    "these those he she they we you i me him her us them my your "
    "his our their what which who whom how when where why all each "
    "every both few more most other some such no not only own same "
    "than too very just about also back even still".split()
)


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 50,
) -> list[str]:
    """Split text into chunks for embedding generation.

    Prefers splitting on paragraph boundaries. Falls back to word
    boundaries if paragraphs are too long. Uses simple word-count
    approximation for token counting.

    Args:
        text: The text to chunk.
        max_tokens: Maximum words per chunk.
        overlap_tokens: Number of words to overlap between chunks.

    Returns:
        List of text chunks.
    """
    text = text.strip()
    if not text:
        return []

    # Clamp overlap to less than max_tokens to prevent infinite loops
    overlap_tokens = min(overlap_tokens, max_tokens - 1)
    if overlap_tokens < 0:
        overlap_tokens = 0

    # Split into paragraphs first
    paragraphs = re.split(r"\n\n+", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: list[str] = []
    current_words: list[str] = []

    for para in paragraphs:
        para_words = para.split()
        # If adding this paragraph would exceed limit, flush current
        if current_words and len(current_words) + len(para_words) > max_tokens:
            chunks.append(" ".join(current_words))
            # Keep overlap from end of previous chunk
            if overlap_tokens > 0:
                current_words = current_words[-overlap_tokens:]
            else:
                current_words = []

        current_words.extend(para_words)

        # If a single paragraph exceeds the limit, split it
        while len(current_words) > max_tokens:
            chunks.append(" ".join(current_words[:max_tokens]))
            if overlap_tokens > 0:
                current_words = current_words[max_tokens - overlap_tokens :]
            else:
                current_words = current_words[max_tokens:]

    # Flush remaining
    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def generate_retrieval_keywords(
    text: str,
    max_keywords: int = 30,
) -> list[str]:
    """Extract retrieval keywords from text using term frequency.

    Deterministic keyword extraction — no LLM. Filters stop words
    and short tokens, returns the most frequent significant terms.
    """
    if not text.strip():
        return []

    # Tokenize: lowercase, strip non-alpha
    words = re.findall(r"[a-z][a-z0-9-]+", text.lower())

    # Filter stop words and very short tokens
    significant = [w for w in words if w not in _STOP_WORDS and len(w) > 2]

    # Count and return top-N unique terms
    counts = Counter(significant)
    return [word for word, _ in counts.most_common(max_keywords)]


class EmbeddingClient(ABC):
    """Abstract embedding client interface.

    Implementations can wrap litellm, OpenAI, Ollama, or provide
    fake embeddings for testing.
    """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """The dimensionality of embeddings produced by this client."""
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Generate an embedding for a single text."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts. Default: sequential."""
        return [self.embed(t) for t in texts]


class LiteLLMEmbeddingClient(EmbeddingClient):
    """Embedding client using litellm for provider-agnostic API calls."""

    def __init__(
        self,
        model: str = "ollama/nomic-embed-text",
        base_url: str | None = None,
        dimensions: int = 384,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        import litellm

        kwargs: dict[str, object] = {"model": self._model, "input": [text]}
        if self._base_url:
            kwargs["api_base"] = self._base_url
        response = litellm.embedding(**kwargs)
        return response.data[0]["embedding"]  # type: ignore[index] — litellm returns dict-like

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import litellm

        kwargs: dict[str, object] = {"model": self._model, "input": texts}
        if self._base_url:
            kwargs["api_base"] = self._base_url
        response = litellm.embedding(**kwargs)
        return [d["embedding"] for d in response.data]  # type: ignore[index] — litellm returns dict-like
