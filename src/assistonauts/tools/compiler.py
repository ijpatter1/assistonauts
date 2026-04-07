"""Compiler agent toolkit — deterministic utility functions.

Provides structured diff generation for LLM reasoning over changes,
and article statistics computation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# Average reading speed in words per minute
_WPM = 200


@dataclass(frozen=True)
class StructuredDiff:
    """Structured representation of changes between two markdown documents."""

    has_changes: bool
    added_sections: list[str] = field(default_factory=list)
    removed_sections: list[str] = field(default_factory=list)
    modified_sections: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class ArticleStats:
    """Statistics for a wiki article."""

    word_count: int
    reading_time_minutes: int
    source_count: int


def _extract_sections(text: str) -> dict[str, str]:
    """Extract heading→content mapping from markdown.

    Splits on ## headings (h2). Content before the first heading
    is assigned to key "".
    """
    sections: dict[str, str] = {}
    current_heading = ""
    current_lines: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            # Save previous section
            sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    sections[current_heading] = "\n".join(current_lines).strip()
    return sections


def generate_diff(old_content: str, new_content: str) -> StructuredDiff:
    """Generate a structured diff between old and new markdown content.

    Analyzes section-level changes rather than line-level diffs,
    producing output suitable for LLM reasoning about what changed.
    """
    if old_content == new_content:
        return StructuredDiff(has_changes=False)

    old_sections = _extract_sections(old_content)
    new_sections = _extract_sections(new_content)

    old_headings = set(old_sections.keys())
    new_headings = set(new_sections.keys())

    added = sorted(new_headings - old_headings)
    removed = sorted(old_headings - new_headings)
    modified = sorted(
        h for h in old_headings & new_headings if old_sections[h] != new_sections[h]
    )

    # Filter out empty-string key from reporting (it's the preamble)
    added = [h for h in added if h]
    removed = [h for h in removed if h]
    modified = [h for h in modified if h]

    parts: list[str] = []
    if added:
        parts.append(f"Added sections: {', '.join(added)}")
    if removed:
        parts.append(f"Removed sections: {', '.join(removed)}")
    if modified:
        parts.append(f"Modified sections: {', '.join(modified)}")
    # If only preamble changed
    if not parts and old_content != new_content:
        parts.append("Content changed (no section-level structural changes)")

    return StructuredDiff(
        has_changes=True,
        added_sections=added,
        removed_sections=removed,
        modified_sections=modified,
        summary="; ".join(parts),
    )


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter (--- delimited) from content."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3 :].strip()
    return content


def _count_sources_from_frontmatter(content: str) -> int:
    """Count source entries in YAML frontmatter."""
    if not content.startswith("---"):
        return 0
    end = content.find("---", 3)
    if end == -1:
        return 0
    frontmatter = content[3:end]
    # Count lines that look like YAML list items under sources:
    in_sources = False
    count = 0
    for line in frontmatter.split("\n"):
        stripped = line.strip()
        if stripped.startswith("sources:"):
            in_sources = True
            continue
        if in_sources:
            if stripped.startswith("- "):
                count += 1
            elif stripped and not stripped.startswith("#"):
                # New top-level key, stop counting
                break
    return count


def compute_stats(content: str) -> ArticleStats:
    """Compute article statistics: word count, reading time, source count.

    Word count excludes YAML frontmatter. Reading time assumes 200 WPM
    with a minimum of 1 minute. Source count is extracted from frontmatter.
    """
    source_count = _count_sources_from_frontmatter(content)
    body = _strip_frontmatter(content)
    words = re.findall(r"\S+", body)
    word_count = len(words)
    reading_time = max(1, math.ceil(word_count / _WPM))

    return ArticleStats(
        word_count=word_count,
        reading_time_minutes=reading_time,
        source_count=source_count,
    )
