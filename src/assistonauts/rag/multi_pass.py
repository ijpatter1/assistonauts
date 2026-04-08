"""Multi-pass retrieval system for the Archivist.

Four retrieval passes with increasing inference cost:
- Pass 1 (broad scan): zero inference — hybrid search for candidate set
- Pass 2 (triage): cheap inference — filter candidates by summary relevance
- Pass 3 (deep read): targeted inference — read full articles for final ranking
- Pass 4 (weak match resolution): resolve ambiguous/borderline matches

Short-circuit mode bypasses multi-pass for small knowledge bases.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.retrieval import hybrid_search
from assistonauts.archivist.service import Archivist


@dataclass
class MultiPassConfig:
    """Configuration for multi-pass retrieval behavior."""

    short_circuit_threshold: int = 20
    short_circuit_word_threshold: int = 50000
    pass_1_limit: int = 50
    pass_2_limit: int = 20
    relevance_floor: float = 0.0


@dataclass
class RetrievalResult:
    """Result of a multi-pass retrieval operation."""

    articles: list[dict[str, object]]
    short_circuited: bool = False
    passes_executed: list[str] = field(default_factory=list)


class MultiPassRetriever:
    """Multi-pass retrieval with short-circuit for small KBs.

    Shared by Curator and Explorer agents for finding relevant articles.
    """

    def __init__(
        self,
        archivist: Archivist,
        embedding_client: EmbeddingClient,
        config: MultiPassConfig | None = None,
    ) -> None:
        self._archivist = archivist
        self._embedding_client = embedding_client
        self._config = config or MultiPassConfig()

    def retrieve(self, query: str) -> RetrievalResult:
        """Execute multi-pass retrieval for a query.

        Returns relevant articles with metadata about the retrieval process.
        """
        all_articles = self._archivist.db.list_articles()

        # Short-circuit check
        if self._should_short_circuit(all_articles):
            return RetrievalResult(
                articles=all_articles,
                short_circuited=True,
                passes_executed=["short_circuit"],
            )

        passes_executed: list[str] = []

        # Pass 1: Broad scan (zero inference)
        candidates = self._pass_1_broad_scan(query)
        passes_executed.append("pass_1_broad_scan")

        if not candidates:
            return RetrievalResult(
                articles=[],
                short_circuited=False,
                passes_executed=passes_executed,
            )

        # Pass 2: Triage on summaries (cheap — keyword match on summaries)
        triaged = self._pass_2_triage(candidates)
        passes_executed.append("pass_2_triage")

        return RetrievalResult(
            articles=triaged,
            short_circuited=False,
            passes_executed=passes_executed,
        )

    def _should_short_circuit(self, articles: list[dict[str, object]]) -> bool:
        """Check if the KB is small enough to bypass multi-pass."""
        if len(articles) <= self._config.short_circuit_threshold:
            total_words = sum(int(a.get("word_count", 0)) for a in articles)
            if total_words <= self._config.short_circuit_word_threshold:
                return True
        return True if len(articles) == 0 else False

    def _pass_1_broad_scan(self, query: str) -> list[dict[str, object]]:
        """Pass 1: Zero-inference broad scan via hybrid search.

        Uses FTS + vector similarity to identify candidate articles.
        """
        query_embedding = self._embedding_client.embed(query)
        results = hybrid_search(
            self._archivist.db,
            query=query,
            query_embedding=query_embedding,
            limit=self._config.pass_1_limit,
            relevance_floor=self._config.relevance_floor,
        )

        # Enrich results with article metadata
        enriched: list[dict[str, object]] = []
        for result in results:
            article = self._archivist.db.get_article(result.path)
            if article:
                article["hybrid_score"] = result.score
                enriched.append(article)

        return enriched

    def _pass_2_triage(
        self, candidates: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Pass 2: Triage candidates using summaries.

        Deterministic for now — enrich with summary data and sort by
        hybrid score. LLM-based triage deferred to when Curator/Explorer
        agents consume this module.
        """
        triaged: list[dict[str, object]] = []
        for candidate in candidates:
            path = str(candidate["path"])
            summary = self._archivist.db.get_summary(path)
            if summary:
                candidate["content_summary"] = summary["content_summary"]
                candidate["retrieval_keywords"] = summary["retrieval_keywords"]
            triaged.append(candidate)

        # Sort by hybrid score (highest first)
        triaged.sort(
            key=lambda a: float(a.get("hybrid_score", 0)),
            reverse=True,
        )
        return triaged[: self._config.pass_2_limit]
