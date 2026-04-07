"""Tests for the content hash cache (manifest)."""

import json
from pathlib import Path

from assistonauts.cache.content import (
    Manifest,
    ManifestEntry,
    hash_content,
)


class TestHashContent:
    """Test SHA-256 content hashing."""

    def test_hash_returns_hex_string(self, tmp_path: Path) -> None:
        """hash_content returns a hex string."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = hash_content(f)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Same content produces same hash."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        assert hash_content(f) == hash_content(f)

    def test_hash_differs_for_different_content(self, tmp_path: Path) -> None:
        """Different content produces different hashes."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")
        assert hash_content(f1) != hash_content(f2)


class TestManifest:
    """Test manifest CRUD operations."""

    def test_load_empty_manifest(self, tmp_path: Path) -> None:
        """Loading a manifest with empty JSON returns empty entries."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("{}\n")
        m = Manifest(manifest_path)
        assert len(m.entries) == 0

    def test_load_nonexistent_creates_empty(self, tmp_path: Path) -> None:
        """Loading from nonexistent path creates empty manifest."""
        m = Manifest(tmp_path / "manifest.json")
        assert len(m.entries) == 0

    def test_get_entry(self, tmp_path: Path) -> None:
        """Can retrieve a stored entry by key."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("{}\n")
        m = Manifest(manifest_path)

        entry = ManifestEntry(
            hash="abc123",
            last_processed="2026-04-07T12:00:00Z",
            processed_by="scout",
        )
        m.set("raw/test.md", entry)

        retrieved = m.get("raw/test.md")
        assert retrieved is not None
        assert retrieved.hash == "abc123"
        assert retrieved.processed_by == "scout"

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        """Getting a nonexistent key returns None."""
        m = Manifest(tmp_path / "manifest.json")
        assert m.get("nonexistent") is None

    def test_has_changed_detects_new_file(self, tmp_path: Path) -> None:
        """has_changed returns True for files not in manifest."""
        m = Manifest(tmp_path / "manifest.json")
        f = tmp_path / "new.txt"
        f.write_text("new content")
        assert m.has_changed(f, "raw/new.txt") is True

    def test_has_changed_detects_modified_file(self, tmp_path: Path) -> None:
        """has_changed returns True when file content has changed."""
        m = Manifest(tmp_path / "manifest.json")
        f = tmp_path / "doc.txt"
        f.write_text("original")

        m.set(
            "raw/doc.txt",
            ManifestEntry(
                hash=hash_content(f),
                last_processed="2026-04-07T12:00:00Z",
                processed_by="scout",
            ),
        )

        f.write_text("modified")
        assert m.has_changed(f, "raw/doc.txt") is True

    def test_has_changed_returns_false_for_unchanged(self, tmp_path: Path) -> None:
        """has_changed returns False when content hash matches."""
        m = Manifest(tmp_path / "manifest.json")
        f = tmp_path / "doc.txt"
        f.write_text("stable content")

        m.set(
            "raw/doc.txt",
            ManifestEntry(
                hash=hash_content(f),
                last_processed="2026-04-07T12:00:00Z",
                processed_by="scout",
            ),
        )

        assert m.has_changed(f, "raw/doc.txt") is False

    def test_save_writes_json(self, tmp_path: Path) -> None:
        """save() writes manifest to disk as JSON."""
        manifest_path = tmp_path / "manifest.json"
        m = Manifest(manifest_path)

        m.set(
            "raw/test.md",
            ManifestEntry(
                hash="deadbeef",
                last_processed="2026-04-07T12:00:00Z",
                processed_by="scout",
            ),
        )
        m.save()

        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert "raw/test.md" in data
        assert data["raw/test.md"]["hash"] == "deadbeef"

    def test_save_is_atomic(self, tmp_path: Path) -> None:
        """save() uses write-to-temp-then-rename for atomicity."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("{}\n")
        m = Manifest(manifest_path)

        m.set(
            "raw/test.md",
            ManifestEntry(
                hash="abc",
                last_processed="2026-04-07T12:00:00Z",
                processed_by="scout",
            ),
        )
        m.save()

        # No temp files should remain
        temp_files = list(tmp_path.glob("*.tmp"))
        assert len(temp_files) == 0

        # Original file should have the data
        data = json.loads(manifest_path.read_text())
        assert "raw/test.md" in data

    def test_roundtrip_save_load(self, tmp_path: Path) -> None:
        """Data survives a save/load cycle."""
        manifest_path = tmp_path / "manifest.json"
        m1 = Manifest(manifest_path)
        m1.set(
            "raw/a.md",
            ManifestEntry(
                hash="hash1",
                last_processed="2026-04-07T12:00:00Z",
                processed_by="scout",
                downstream=["wiki/article.md"],
            ),
        )
        m1.save()

        m2 = Manifest(manifest_path)
        entry = m2.get("raw/a.md")
        assert entry is not None
        assert entry.hash == "hash1"
        assert entry.downstream == ["wiki/article.md"]

    def test_downstream_tracking(self, tmp_path: Path) -> None:
        """ManifestEntry tracks downstream dependencies."""
        entry = ManifestEntry(
            hash="abc",
            last_processed="2026-04-07T12:00:00Z",
            processed_by="scout",
            downstream=["wiki/concepts/foo.md", "wiki/entities/bar.md"],
        )
        assert len(entry.downstream) == 2
