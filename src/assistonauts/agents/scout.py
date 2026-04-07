"""Scout agent — ingests source material into the knowledge base."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from assistonauts.agents.base import Agent, LLMClientProtocol
from assistonauts.cache.content import Manifest, hash_content
from assistonauts.tools.scout import (
    check_dedup,
    check_relevance_keywords,
    clip_web,
    convert_document,
    convert_text_file,
)

_SCOUT_SYSTEM_PROMPT = """\
You are Scout, an ingestion agent for the Assistonauts knowledge base framework.
Your job is to evaluate source material for relevance to the expedition scope,
convert it to clean markdown, and file it in the raw/ directory with proper
metadata frontmatter.

You use deterministic toolkit functions for format conversion and hashing.
You only use LLM inference for borderline relevance decisions.
"""


@dataclass
class IngestResult:
    """Result of a Scout ingest operation."""

    success: bool
    skipped: bool = False
    output_path: Path | None = None
    manifest_key: str = ""
    message: str = ""


class ScoutAgent(Agent):
    """Scout agent — ingests and converts source material.

    Owns: raw/
    Reads: index/ (for manifest)
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        workspace_root: Path,
    ) -> None:
        raw_dir = workspace_root / "raw"
        index_dir = workspace_root / "index"

        super().__init__(
            role="scout",
            system_prompt=_SCOUT_SYSTEM_PROMPT,
            llm_client=llm_client,
            owned_dirs=[raw_dir],
            readable_dirs=[index_dir],
            toolkit={
                "hash_content": hash_content,
                "check_relevance_keywords": check_relevance_keywords,
                "convert_text_file": convert_text_file,
                "convert_document": convert_document,
                "clip_web": clip_web,
                "check_dedup": check_dedup,
            },
        )
        self._workspace_root = workspace_root
        self._manifest_path = index_dir / "manifest.json"

    def ingest(
        self,
        source_path: Path,
        category: str = "articles",
    ) -> IngestResult:
        """Ingest a source file into raw/.

        Pipeline:
        1. Check manifest — skip if unchanged
        2. Convert to markdown
        3. Add frontmatter
        4. Write to raw/<category>/
        5. Update manifest
        """
        source_path = source_path.resolve()
        manifest = Manifest(self._manifest_path)

        # Determine output location and manifest key
        output_dir = self._workspace_root / "raw" / category
        output_dir.mkdir(parents=True, exist_ok=True)
        output_name = source_path.stem + ".md"
        output_path = output_dir / output_name
        manifest_key = f"raw/{category}/{output_name}"

        # Check if content has changed
        if not manifest.has_changed(source_path, manifest_key):
            return IngestResult(
                success=True,
                skipped=True,
                output_path=output_path,
                manifest_key=manifest_key,
                message="Content unchanged, skipped.",
            )

        # Convert to markdown
        content = convert_document(source_path)

        # Add frontmatter
        now = datetime.now(UTC).isoformat()
        frontmatter = (
            "---\n"
            f"source: {source_path.name}\n"
            f"source_path: {source_path}\n"
            f"ingested_by: scout\n"
            f"ingested_at: {now}\n"
            f"category: {category}\n"
            "---\n\n"
        )

        full_content = frontmatter + content

        # Write output (using base class write_file for ownership enforcement)
        self.write_file(output_path, full_content)

        # Update manifest
        content_hash = hash_content(source_path)
        from assistonauts.cache.content import ManifestEntry

        manifest.set(
            manifest_key,
            ManifestEntry(
                hash=content_hash,
                last_processed=now,
                processed_by="scout",
            ),
        )
        manifest.save()

        return IngestResult(
            success=True,
            skipped=False,
            output_path=output_path,
            manifest_key=manifest_key,
            message=f"Ingested {source_path.name} → {manifest_key}",
        )

    def run_mission(self, mission: dict[str, str]) -> IngestResult:
        """Execute a Scout mission (ingest a source).

        Expects mission dict with 'source_path' and optional 'category'.
        """
        source_path = Path(mission["source_path"])
        category = mission.get("category", "articles")
        return self.ingest(source_path, category=category)
