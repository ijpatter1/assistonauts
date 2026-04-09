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
from typing import Protocol

from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.retrieval import hybrid_search
from assistonauts.archivist.service import Archivist


class LLMClientProtocol(Protocol):
    """Protocol for injectable LLM clients used by multi-pass retrieval."""

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> object: ...


@dataclass
class MultiPassConfig:
    """Configuration for multi-pass retrieval behavior."""

    short_circuit_threshold: int = 20
    short_circuit_word_threshold: int = 50000
    pass_1_limit: int = 50
    pass_2_limit: int = 20
    pass_3_limit: int = 10
    relevance_floor: float = 0.0
    triage_confidence_threshold: float = 0.5


@dataclass
class RetrievalLog:
    """Observability log for a multi-pass retrieval operation.

    Records per-pass metrics so users can audit what was retrieved,
    filtered, and why.
    """

    query: str = ""
    total_articles: int = 0
    passes: list[dict[str, object]] = field(default_factory=list)

    def add_pass(
        self,
        name: str,
        input_count: int,
        output_count: int,
        **details: object,
    ) -> None:
        """Record metrics for a single retrieval pass."""
        entry: dict[str, object] = {
            "name": name,
            "input_count": input_count,
            "output_count": output_count,
        }
        entry.update(details)
        self.passes.append(entry)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a dict for JSON logging."""
        return {
            "query": self.query,
            "total_articles": self.total_articles,
            "passes": self.passes,
        }


@dataclass
class RetrievalResult:
    """Result of a multi-pass retrieval operation."""

    articles: list[dict[str, object]]
    short_circuited: bool = False
    passes_executed: list[str] = field(default_factory=list)
    log: RetrievalLog = field(default_factory=RetrievalLog)


class MultiPassRetriever:
    """Multi-pass retrieval with short-circuit for small KBs.

    Shared by Curator and Explorer agents for finding relevant articles.
    """

    def __init__(
        self,
        archivist: Archivist,
        embedding_client: EmbeddingClient,
        config: MultiPassConfig | None = None,
        llm_client: LLMClientProtocol | None = None,
    ) -> None:
        self._archivist = archivist
        self._embedding_client = embedding_client
        self._config = config or MultiPassConfig()
        self._llm_client = llm_client

    def retrieve(self, query: str) -> RetrievalResult:
        """Execute multi-pass retrieval for a query.

        Returns relevant articles with metadata about the retrieval process,
        including a RetrievalLog with per-pass metrics.
        """
        all_articles = self._archivist.db.list_articles()
        log = RetrievalLog(query=query, total_articles=len(all_articles))

        # Short-circuit check
        if self._should_short_circuit(all_articles):
            log.add_pass(
                "short_circuit",
                input_count=len(all_articles),
                output_count=len(all_articles),
            )
            return RetrievalResult(
                articles=all_articles,
                short_circuited=True,
                passes_executed=["short_circuit"],
                log=log,
            )

        passes_executed: list[str] = []

        # Pass 1: Broad scan (zero inference)
        candidates = self._pass_1_broad_scan(query)
        passes_executed.append("pass_1_broad_scan")
        log.add_pass(
            "pass_1_broad_scan",
            input_count=len(all_articles),
            output_count=len(candidates),
        )

        if not candidates:
            return RetrievalResult(
                articles=[],
                short_circuited=False,
                passes_executed=passes_executed,
                log=log,
            )

        # Pass 2: Triage on summaries (cheap LLM inference or deterministic)
        triaged = self._pass_2_triage(candidates, query)
        passes_executed.append("pass_2_triage")
        log.add_pass(
            "pass_2_triage",
            input_count=len(candidates),
            output_count=len(triaged),
            used_llm=self._llm_client is not None,
        )

        if not triaged:
            return RetrievalResult(
                articles=[],
                short_circuited=False,
                passes_executed=passes_executed,
                log=log,
            )

        # Pass 3: Deep read — full article content for top candidates
        deep_read = self._pass_3_deep_read(triaged, query)
        passes_executed.append("pass_3_deep_read")
        log.add_pass(
            "pass_3_deep_read",
            input_count=len(triaged),
            output_count=len(deep_read),
            used_llm=self._llm_client is not None,
        )

        # Pass 4: Weak match resolution — resolve borderline matches
        resolved = self._pass_4_weak_match(deep_read, query)
        passes_executed.append("pass_4_weak_match")
        log.add_pass(
            "pass_4_weak_match",
            input_count=len(deep_read),
            output_count=len(resolved),
            used_llm=self._llm_client is not None,
        )

        return RetrievalResult(
            articles=resolved,
            short_circuited=False,
            passes_executed=passes_executed,
            log=log,
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
        self,
        candidates: list[dict[str, object]],
        query: str,
    ) -> list[dict[str, object]]:
        """Pass 2: Triage candidates using summaries.

        When an LLM client is available, uses cheap inference to score
        each candidate's summary against the query. Without an LLM
        client, falls back to deterministic sorting by hybrid score.
        """
        triaged: list[dict[str, object]] = []
        for candidate in candidates:
            path = str(candidate["path"])
            summary = self._archivist.db.get_summary(path)
            if summary:
                candidate["content_summary"] = summary["content_summary"]
                candidate["retrieval_keywords"] = summary["retrieval_keywords"]
            triaged.append(candidate)

        if self._llm_client is not None and triaged:
            # Use LLM to score relevance of summaries
            triaged = self._llm_triage_summaries(triaged, query)
        else:
            # Deterministic fallback — sort by hybrid score
            triaged.sort(
                key=lambda a: float(a.get("hybrid_score", 0)),
                reverse=True,
            )

        return triaged[: self._config.pass_2_limit]

    def _llm_triage_summaries(
        self,
        candidates: list[dict[str, object]],
        query: str,
    ) -> list[dict[str, object]]:
        """Use cheap LLM inference to triage candidates by summary relevance.

        Asks the LLM to rate each candidate 0.0-1.0 for query relevance.
        """
        assert self._llm_client is not None
        summaries_text = ""
        for i, c in enumerate(candidates):
            title = c.get("title", c.get("path", f"article_{i}"))
            summary = c.get("content_summary", "No summary available.")
            summaries_text += f"{i}. {title}: {summary}\n"

        prompt = (
            f"Query: {query}\n\n"
            f"Rate each article's relevance to the query (0.0 to 1.0).\n"
            f"Return ONLY lines in format: INDEX SCORE\n\n"
            f"{summaries_text}"
        )
        response = self._llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            system="You are a relevance scorer. Output only index-score pairs.",
        )
        content = getattr(response, "content", str(response))

        # Parse scores from response
        scores: dict[int, float] = {}
        for line in content.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    idx = int(parts[0].rstrip("."))
                    score = float(parts[1])
                    scores[idx] = score
                except (ValueError, IndexError):
                    continue

        # Annotate candidates with triage scores and sort
        for i, c in enumerate(candidates):
            c["triage_score"] = scores.get(i, 0.0)

        candidates.sort(
            key=lambda a: float(a.get("triage_score", 0)),
            reverse=True,
        )
        return candidates

    def _pass_3_deep_read(
        self,
        candidates: list[dict[str, object]],
        query: str,
    ) -> list[dict[str, object]]:
        """Pass 3: Deep read — read full article content for top candidates.

        For high-confidence candidates, reads the full article and uses
        targeted LLM inference to produce a final relevance assessment.
        Without an LLM client, passes through the top candidates unchanged.
        """
        top = candidates[: self._config.pass_3_limit]

        if self._llm_client is None:
            # Deterministic fallback — tag all as confirmed
            for c in top:
                c["deep_read"] = True
                c["relevance"] = "confirmed"
            return top

        confirmed: list[dict[str, object]] = []
        for candidate in top:
            path = str(candidate["path"])
            full_path = self._archivist.workspace / path
            if not full_path.exists():
                candidate["deep_read"] = True
                candidate["relevance"] = "unreadable"
                confirmed.append(candidate)
                continue

            content = full_path.read_text()[:2000]  # First 2000 chars
            prompt = (
                f"Query: {query}\n\n"
                f"Article content:\n{content}\n\n"
                f"Is this article relevant to the query? "
                f"Answer YES or NO, then a brief reason."
            )
            response = self._llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                system="You are a relevance assessor. Be concise.",
            )
            answer = getattr(response, "content", str(response)).strip()
            candidate["deep_read"] = True
            candidate["relevance"] = (
                "confirmed" if answer.upper().startswith("YES") else "rejected"
            )
            candidate["deep_read_reason"] = answer
            confirmed.append(candidate)

        return [c for c in confirmed if c.get("relevance") != "rejected"]

    def _pass_4_weak_match(
        self,
        candidates: list[dict[str, object]],
        query: str,
    ) -> list[dict[str, object]]:
        """Pass 4: Weak match resolution — resolve borderline/ambiguous matches.

        Re-evaluates any candidates that had borderline scores or ambiguous
        relevance assessments. Without an LLM client, passes through unchanged.
        """
        if self._llm_client is None or not candidates:
            for c in candidates:
                c["final_pass"] = True
            return candidates

        # Identify borderline candidates (triage_score between thresholds)
        threshold = self._config.triage_confidence_threshold
        strong: list[dict[str, object]] = []
        borderline: list[dict[str, object]] = []

        for c in candidates:
            score = float(c.get("triage_score", 1.0))
            if score >= threshold:
                c["final_pass"] = True
                strong.append(c)
            else:
                borderline.append(c)

        if not borderline:
            return strong

        # Ask LLM to resolve borderline matches collectively
        descriptions = ""
        for i, c in enumerate(borderline):
            title = c.get("title", c.get("path", f"article_{i}"))
            reason = c.get("deep_read_reason", "No assessment.")
            descriptions += f"{i}. {title}: {reason}\n"

        prompt = (
            f"Query: {query}\n\n"
            f"These articles had ambiguous relevance. "
            f"For each, answer INCLUDE or EXCLUDE:\n\n"
            f"{descriptions}"
        )
        response = self._llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            system="You are a relevance resolver. Output only index-decision pairs.",
        )
        content = getattr(response, "content", str(response))

        for line in content.strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    idx = int(parts[0].rstrip("."))
                    decision = parts[1].upper()
                    if 0 <= idx < len(borderline) and decision == "INCLUDE":
                        borderline[idx]["final_pass"] = True
                        strong.append(borderline[idx])
                except (ValueError, IndexError):
                    continue

        return strong
