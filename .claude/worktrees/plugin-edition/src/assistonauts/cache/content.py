"""Content hash cache (manifest) for skip-if-unchanged logic."""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def hash_content(path: Path) -> str:
    """Return SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ManifestEntry:
    """A single entry in the content manifest."""

    hash: str
    last_processed: str
    processed_by: str
    downstream: list[str] = field(default_factory=list)


class Manifest:
    """Content hash manifest for tracking processed files.

    Supports skip-if-unchanged logic and downstream dependency tracking.
    Uses atomic writes (write-to-temp-then-rename) to prevent corruption.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self.entries: dict[str, ManifestEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load manifest from disk."""
        if not self._path.exists():
            return

        data = json.loads(self._path.read_text())
        for key, val in data.items():
            if isinstance(val, dict):
                self.entries[key] = ManifestEntry(
                    hash=val.get("hash", ""),
                    last_processed=val.get("last_processed", ""),
                    processed_by=val.get("processed_by", ""),
                    downstream=val.get("downstream", []),
                )

    def get(self, key: str) -> ManifestEntry | None:
        """Get a manifest entry by key, or None if not found."""
        return self.entries.get(key)

    def set(self, key: str, entry: ManifestEntry) -> None:
        """Set a manifest entry."""
        self.entries[key] = entry

    def has_changed(self, file_path: Path, key: str) -> bool:
        """Check if a file has changed since last processing.

        Returns True if the file is new or its hash differs from the manifest.

        Note on key semantics: The key identifies the *output* (e.g.
        ``wiki/concept/foo.md``) but the stored hash is of the *input*
        file at ``file_path`` (e.g. the raw source). This lets agents
        skip reprocessing when the source hasn't changed. The Archivist
        (Phase 3) should use separate index entries if it needs to track
        wiki article content hashes for staleness detection.
        """
        entry = self.get(key)
        if entry is None:
            return True
        return hash_content(file_path) != entry.hash

    def save(self) -> None:
        """Write manifest to disk atomically (write-to-temp-then-rename)."""
        data: dict[str, dict[str, object]] = {}
        for key, entry in self.entries.items():
            data[key] = {
                "hash": entry.hash,
                "last_processed": entry.last_processed,
                "processed_by": entry.processed_by,
                "downstream": entry.downstream,
            }

        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file in same directory, then rename
        fd, tmp_path = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with open(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            Path(tmp_path).replace(self._path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise
