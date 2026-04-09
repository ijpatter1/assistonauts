"""Embedding generation, chunking, and keyword extraction for the Archivist."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter

from assistonauts.models.config import EmbeddingConfig

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

    Implementations can wrap litellm, OpenAI, Ollama, google-genai,
    or provide fake embeddings for testing.
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

    def embed_content(self, data: bytes, mime_type: str) -> list[float]:
        """Generate an embedding for binary content (image, PDF, etc.).

        Only supported by multimodal embedding providers (e.g. Gemini).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support multimodal embedding"
        )

    def embed_multimodal(self, parts: list[dict[str, object]]) -> list[float]:
        """Generate an embedding for interleaved text + binary parts.

        Each part is either {"text": "..."} or {"data": b"...", "mime_type": "..."}.
        Only supported by multimodal embedding providers (e.g. Gemini).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support multimodal embedding"
        )


class LiteLLMEmbeddingClient(EmbeddingClient):
    """Embedding client using litellm for provider-agnostic API calls.

    Supports text embedding for all litellm providers. For providers
    that support multimodal embedding (e.g. Gemini), also supports
    binary content via base64 data URIs.
    """

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

    def _call_litellm(self, inputs: list[str]) -> list[list[float]]:
        """Call litellm embedding API and return raw embedding vectors."""
        import litellm

        kwargs: dict[str, object] = {"model": self._model, "input": inputs}
        if self._base_url:
            kwargs["api_base"] = self._base_url
        response = litellm.embedding(**kwargs)
        return [d["embedding"] for d in response.data]  # type: ignore[index] — litellm returns dict-like

    def embed(self, text: str) -> list[float]:
        return self._call_litellm([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._call_litellm(texts)

    def embed_content(self, data: bytes, mime_type: str) -> list[float]:
        """Generate an embedding for binary content via base64 data URI.

        Requires a model that supports multimodal embedding (e.g. gemini/).
        """
        import base64

        b64 = base64.b64encode(data).decode("ascii")
        data_uri = f"data:{mime_type};base64,{b64}"
        return self._call_litellm([data_uri])[0]

    def embed_multimodal(self, parts: list[dict[str, object]]) -> list[float]:
        """Embed multiple parts and return the first part's embedding.

        Each part is {"text": "..."} or {"data": b"...", "mime_type": "..."}.
        Parts are embedded independently via litellm's batch API — this does
        NOT produce a single joint embedding from interleaved content.
        Returns the embedding of the first part.

        Requires a multimodal model (e.g. gemini/).
        """
        import base64

        inputs: list[str] = []
        for part in parts:
            if "text" in part:
                inputs.append(str(part["text"]))
            elif "data" in part and "mime_type" in part:
                raw = part["data"]
                if not isinstance(raw, bytes):
                    raise TypeError(
                        f"Expected bytes for 'data', got {type(raw).__name__}"
                    )
                b64 = base64.b64encode(raw).decode("ascii")
                inputs.append(f"data:{part['mime_type']};base64,{b64}")
        if not inputs:
            raise ValueError("No valid parts provided to embed_multimodal")
        return self._call_litellm(inputs)[0]


def get_embedding_dimensions(config: EmbeddingConfig) -> int:
    """Get the embedding dimensions from the active provider config.

    Returns 768 (Gemini default) if no provider is configured.
    """
    if not config.active:
        return 768
    provider_config = config.providers.get(config.active)
    if not provider_config:
        return 768
    return provider_config.dimensions or 768


def create_embedding_client(config: EmbeddingConfig) -> EmbeddingClient | None:
    """Factory: create an EmbeddingClient from an EmbeddingConfig.

    Returns None if the config is empty or the provider is unknown.
    """
    if not config.active:
        return None

    provider_config = config.providers.get(config.active)
    if not provider_config or not provider_config.model:
        return None

    model = provider_config.model
    # Prefix with provider name if not already prefixed (e.g. "ollama/nomic-embed-text")
    if "/" not in model and config.active != "litellm":
        model = f"{config.active}/{model}"
    return LiteLLMEmbeddingClient(
        model=model,
        base_url=provider_config.base_url,
        dimensions=provider_config.dimensions or 768,
    )
