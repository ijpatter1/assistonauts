"""Tests for image ingestion in the Scout agent — vision model support."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.agents.scout import ScoutAgent
from assistonauts.tools.scout import convert_image, is_image_file
from tests.helpers import FakeLLMClient


class TestIsImageFile:
    """Test image file detection."""

    def test_png(self) -> None:
        assert is_image_file(Path("photo.png")) is True

    def test_jpg(self) -> None:
        assert is_image_file(Path("photo.jpg")) is True

    def test_jpeg(self) -> None:
        assert is_image_file(Path("photo.jpeg")) is True

    def test_gif(self) -> None:
        assert is_image_file(Path("photo.gif")) is True

    def test_webp(self) -> None:
        assert is_image_file(Path("photo.webp")) is True

    def test_markdown_not_image(self) -> None:
        assert is_image_file(Path("doc.md")) is False

    def test_pdf_not_image(self) -> None:
        assert is_image_file(Path("doc.pdf")) is False

    def test_case_insensitive(self) -> None:
        assert is_image_file(Path("photo.PNG")) is True
        assert is_image_file(Path("photo.JPG")) is True


class TestConvertImage:
    """Test image-to-markdown conversion via vision model."""

    def test_convert_returns_markdown(self, tmp_path: Path) -> None:
        # Create a minimal PNG (1x1 pixel)
        img = tmp_path / "test.png"
        img.write_bytes(_minimal_png())

        llm = FakeLLMClient(
            responses=["# Chapter 1\n\nThis is extracted text from the image."]
        )
        result = convert_image(img, llm)
        assert "Chapter 1" in result
        assert "extracted text" in result

    def test_convert_sends_image_to_llm(self, tmp_path: Path) -> None:
        img = tmp_path / "test.png"
        img.write_bytes(_minimal_png())

        llm = FakeLLMClient(responses=["Extracted content."])
        convert_image(img, llm)
        # Should have made one LLM call
        assert len(llm.calls) == 1

    def test_convert_unsupported_format_raises(self, tmp_path: Path) -> None:
        txt = tmp_path / "test.txt"
        txt.write_text("not an image")
        llm = FakeLLMClient()
        with pytest.raises(ValueError, match="not a supported image"):
            convert_image(txt, llm)


class TestScoutImageIngestion:
    """Test Scout agent ingesting image files."""

    def test_ingest_image(self, initialized_workspace: Path) -> None:
        img = initialized_workspace / "book-page.png"
        img.write_bytes(_minimal_png())

        llm = FakeLLMClient(
            responses=["# Book Content\n\nExtracted from the book page."]
        )
        scout = ScoutAgent(llm_client=llm, workspace_root=initialized_workspace)
        result = scout.ingest(img)

        assert result.success is True
        assert result.output_path is not None
        assert result.output_path.exists()
        content = result.output_path.read_text()
        assert "Book Content" in content
        assert "ingested_by: scout" in content

    def test_ingest_image_uses_vision(self, initialized_workspace: Path) -> None:
        img = initialized_workspace / "page.jpg"
        img.write_bytes(_minimal_png())  # Content doesn't matter for test

        llm = FakeLLMClient(responses=["Extracted text."])
        scout = ScoutAgent(llm_client=llm, workspace_root=initialized_workspace)
        scout.ingest(img)
        # Should have called LLM for vision extraction
        assert len(llm.calls) == 1


def _minimal_png() -> bytes:
    """Return a minimal valid 1x1 pixel PNG file."""
    import struct
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        raw = chunk_type + data
        crc = zlib.crc32(raw) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + raw + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_data = b"\x00\xff\xff\xff"  # filter byte + RGB
    idat = _chunk(b"IDAT", zlib.compress(raw_data))
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend
