"""Explorer agent — query synthesis against the knowledge base.

The Explorer accepts natural language questions, retrieves relevant articles
via multi-pass retrieval, assembles context within a token budget, and
synthesizes answers with citations to specific wiki articles.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from assistonauts.agents.base import Agent, LLMClientProtocol
from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.service import Archivist
from assistonauts.rag.multi_pass import MultiPassRetriever
from assistonauts.tools.explorer import (
    Citation,
    ContextBudget,
    calculate_context_budget,
    render_answer_markdown,
)

_EXPLORER_SYSTEM_PROMPT = """\
You are Explorer, a knowledge synthesis agent for the Assistonauts knowledge base.
Your job is to answer questions by drawing on wiki articles provided as context.

Guidelines:
- Ground every claim in the provided article context. Do not invent facts.
- When referencing an article, mention it by title so citations can be traced.
- If the context is insufficient to fully answer the question, say so explicitly \
and indicate what is missing.
- Be concise but thorough. Prefer specifics over generalities.
- Structure your answer with clear paragraphs. Use bullet points for lists.
- Do not include a sources section — the system adds citations automatically.
"""

# Default context window budget for article content
_DEFAULT_MAX_CONTEXT_TOKENS = 8000


@dataclass
class ExplorerResult:
    """Result of an Explorer query."""

    success: bool
    query: str = ""
    answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    formatted_answer: str = ""
    context_tokens_used: int = 0
    articles_retrieved: int = 0
    articles_used: int = 0
    output_path: Path | None = None
    output_paths: list[Path] = field(default_factory=list)


class ExplorerAgent(Agent):
    """Explorer agent — query synthesis with citations.

    Owns: wiki/explorations/
    Reads: wiki/, index/
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        workspace_root: Path,
        archivist: Archivist | None = None,
        embedding_client: EmbeddingClient | None = None,
        max_context_tokens: int = _DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> None:
        wiki_dir = workspace_root / "wiki"
        explorations_dir = wiki_dir / "explorations"
        index_dir = workspace_root / "index"

        super().__init__(
            role="explorer",
            system_prompt=_EXPLORER_SYSTEM_PROMPT,
            llm_client=llm_client,
            owned_dirs=[explorations_dir],
            readable_dirs=[wiki_dir, index_dir],
            toolkit={
                "calculate_context_budget": calculate_context_budget,
                "render_answer_markdown": render_answer_markdown,
            },
        )
        self._workspace_root = workspace_root
        self._archivist = archivist
        self._embedding_client = embedding_client
        self._max_context_tokens = max_context_tokens
        self._setup_persistent_logger(workspace_root)

    def explore(
        self,
        query: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ExplorerResult:
        """Answer a question against the knowledge base.

        Args:
            query: The question to answer.
            conversation_history: Prior Q&A pairs for conversational flow.
                Each dict has 'role' ('user' or 'assistant') and 'content'.

        Pipeline:
        1. Retrieve relevant articles via multi-pass retrieval
        2. Calculate context budget — select articles that fit
        3. Read full content of included articles
        4. Synthesize answer via LLM with article context
        5. Extract citations from used articles
        """
        archivist = self._archivist
        embedding = self._embedding_client

        if archivist is None or embedding is None:
            return ExplorerResult(
                success=False,
                query=query,
                answer="Archivist and embedding client required.",
            )

        # Step 1: Retrieve relevant articles
        retriever = MultiPassRetriever(
            archivist=archivist,
            embedding_client=embedding,
            llm_client=self.llm_client,
        )
        retrieval = retriever.retrieve(query)
        articles_retrieved = len(retrieval.articles)

        if not retrieval.articles:
            # No articles found — still answer but without context
            answer = self._synthesize_no_context(query)
            result = ExplorerResult(
                success=True,
                query=query,
                answer=answer,
                formatted_answer=render_answer_markdown(answer, [], query=query),
                articles_retrieved=0,
                articles_used=0,
            )
            self._log_query(
                result,
                passes_executed=retrieval.passes_executed,
                retrieval_log=retrieval.log,
            )
            return result

        # Step 2: Calculate context budget
        budget = calculate_context_budget(
            retrieval.articles,
            max_tokens=self._max_context_tokens,
        )

        # Step 3: Read full content of included articles
        article_contexts = self._read_article_contents(budget)
        articles_used = len(article_contexts)

        # Step 4: Synthesize answer via LLM
        answer = self._synthesize(query, article_contexts, conversation_history)

        # Step 5: Build citations from used articles
        citations = self._build_citations(budget.included)

        formatted = render_answer_markdown(answer, citations, query=query)

        result = ExplorerResult(
            success=True,
            query=query,
            answer=answer,
            citations=citations,
            formatted_answer=formatted,
            context_tokens_used=budget.total_tokens,
            articles_retrieved=articles_retrieved,
            articles_used=articles_used,
        )
        self._log_query(
            result,
            passes_executed=retrieval.passes_executed,
            retrieval_log=retrieval.log,
        )
        return result

    def _read_article_contents(
        self,
        budget: ContextBudget,
    ) -> list[dict[str, str]]:
        """Read full content of budget-included articles.

        Returns list of dicts with 'title', 'path', and 'content' keys.
        """
        contexts: list[dict[str, str]] = []
        for article in budget.included:
            path = str(article.get("path", ""))
            full_path = self._workspace_root / path
            if not full_path.exists():
                continue
            content = self.read_file(full_path)
            # Strip frontmatter for context
            body = re.sub(r"^---\n.*?\n---\n?", "", content, count=1, flags=re.DOTALL)
            title = str(article.get("title", Path(path).stem))
            contexts.append({"title": title, "path": path, "content": body.strip()})
        return contexts

    def _synthesize(
        self,
        query: str,
        article_contexts: list[dict[str, str]],
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """Build prompt with article context and call LLM for synthesis."""
        context_block = self._format_context_block(article_contexts)

        prompt = (
            f"Question: {query}\n\n"
            f"---\n\n"
            f"Knowledge base articles:\n\n"
            f"{context_block}\n\n"
            f"---\n\n"
            f"Answer the question using the articles above. "
            f"Reference article titles when making claims."
        )

        # Build message list with conversation history for follow-ups
        messages: list[dict[str, str]] = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": prompt})

        return self.call_llm(messages=messages)

    def _synthesize_no_context(self, query: str) -> str:
        """Handle queries when no articles are retrieved."""
        prompt = (
            f"Question: {query}\n\n"
            f"The knowledge base has no articles relevant to this question. "
            f"Explain that you cannot answer based on the available knowledge "
            f"and suggest what kind of sources might help."
        )
        return self.call_llm(messages=[{"role": "user", "content": prompt}])

    @staticmethod
    def _format_context_block(article_contexts: list[dict[str, str]]) -> str:
        """Format article contexts into a prompt block."""
        parts: list[str] = []
        for ctx in article_contexts:
            parts.append(f"### {ctx['title']} ({ctx['path']})\n\n{ctx['content']}")
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _build_citations(articles: list[dict[str, object]]) -> list[Citation]:
        """Build Citation objects from included articles."""
        citations: list[Citation] = []
        for article in articles:
            path = str(article.get("path", ""))
            title = str(article.get("title", Path(path).stem))
            relevance = str(article.get("hybrid_score", ""))
            citations.append(
                Citation(title=title, path=path, relevance=relevance or None)
            )
        return citations

    def _log_query(
        self,
        result: ExplorerResult,
        passes_executed: list[str] | None = None,
        retrieval_log: object | None = None,
    ) -> None:
        """Append a query record to .assistonauts/explorer/queries.jsonl.

        Every explore() call is logged automatically for audit trail,
        regardless of whether the user saves the exploration.
        """
        log_dir = self._workspace_root / ".assistonauts" / "explorer"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "queries.jsonl"

        entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "query": result.query,
            "answer": result.answer,
            "citations": [
                {"title": c.title, "path": c.path, "section": c.section}
                for c in result.citations
            ],
            "articles_retrieved": result.articles_retrieved,
            "articles_used": result.articles_used,
            "context_tokens_used": result.context_tokens_used,
            "passes_executed": passes_executed or [],
            "success": result.success,
        }

        # Include full retrieval log if available
        if retrieval_log is not None and hasattr(retrieval_log, "to_dict"):
            entry["retrieval"] = retrieval_log.to_dict()

        with open(log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def file_exploration(self, result: ExplorerResult) -> Path:
        """Save an exploration result to wiki/explorations/ with frontmatter.

        Creates a markdown file following the exploration article template:
        frontmatter (title, type, sources, created_at), Question section,
        Analysis section, and Sources section.

        Returns the path to the created file.
        """
        slug = _query_to_slug(result.query) or "untitled-exploration"
        explorations_dir = self._workspace_root / "wiki" / "explorations"
        explorations_dir.mkdir(parents=True, exist_ok=True)
        file_path = explorations_dir / f"{slug}.md"

        # Build frontmatter
        sources_yaml = ""
        if result.citations:
            source_lines = "\n".join(f"  - {c.path}" for c in result.citations)
            sources_yaml = f"sources:\n{source_lines}"
        else:
            sources_yaml = "sources: []"

        frontmatter = (
            f"---\n"
            f"title: {result.query}\n"
            f"type: exploration\n"
            f"{sources_yaml}\n"
            f"created_at: {date.today().isoformat()}\n"
            f"status: exploration\n"
            f"---\n"
        )

        # Build body sections (matches _EXPLORATION_TEMPLATE in models/schema.py)
        body_parts: list[str] = [
            f"## Question\n\n{result.query}",
            f"## Analysis\n\n{result.answer}",
            "## Findings\n\n*To be added upon promotion.*",
            "## Open Questions\n\n*To be added upon promotion.*",
        ]

        # Sources section with citation links
        if result.citations:
            source_lines_md = "\n".join(
                f"- [{c.title}]({c.path})" for c in result.citations
            )
            body_parts.append(f"## Sources\n\n{source_lines_md}")
        else:
            body_parts.append("## Sources\n\nNo sources cited.")

        content = frontmatter + "\n" + "\n\n".join(body_parts) + "\n"
        self.write_file(file_path, content)

        return file_path

    def run_task(self, task: dict[str, str]) -> ExplorerResult:
        """Execute an Explorer task.

        Expects task dict with 'query'.
        """
        query = task.get("query", "")
        return self.explore(query)


def _query_to_slug(query: str, max_length: int = 80) -> str:
    """Convert a query string to a URL-safe slug for file naming."""
    slug = query.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)  # Remove non-word chars except hyphens
    slug = re.sub(r"[\s_]+", "-", slug)  # Replace whitespace/underscores with hyphens
    slug = re.sub(r"-+", "-", slug)  # Collapse multiple hyphens
    slug = slug.strip("-")
    return slug[:max_length]
