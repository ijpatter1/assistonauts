"""Scout agent toolkit — utility functions for source ingestion.

Most functions are pure/deterministic (no LLM calls) and independently
testable. The exception is convert_image(), which uses a vision-capable
LLM to extract text from images.
"""

from __future__ import annotations

import base64
import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from assistonauts.cache.content import hash_content as _hash_content


class LLMClientProtocol(Protocol):
    """Minimal protocol for LLM clients used by toolkit functions."""

    def complete(
        self,
        messages: list[dict[str, object]],
        system: str | None = None,
        **kwargs: object,
    ) -> object: ...


def hash_content(path: Path) -> str:
    """Return SHA-256 hex digest of a file's contents."""
    return _hash_content(path)


def check_relevance_keywords(text: str, keywords: list[str]) -> float:
    """Score text relevance against a keyword list.

    Returns a float between 0.0 and 1.0 representing the fraction
    of keywords found in the text (case-insensitive).
    Returns 1.0 if keyword list is empty (no filtering).
    """
    if not keywords:
        return 1.0

    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matches / len(keywords)


def convert_text_file(path: Path) -> str:
    """Read a plain text or markdown file and return its content.

    For .txt and .md files, this is a simple read. More complex formats
    (PDF, HTML, DOCX) use markitdown and are handled by convert_document().
    """
    return path.read_text(encoding="utf-8")


def convert_document(path: Path) -> str:
    """Convert a document (PDF, HTML, DOCX) to markdown via markitdown.

    Falls back to plain text read for .txt/.md files.
    """
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        return convert_text_file(path)

    from markitdown import MarkItDown

    converter = MarkItDown()
    result = converter.convert(str(path))
    return result.text_content


_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})

_IMAGE_MIME_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

_VISION_SYSTEM_PROMPT = """\
You are a precise text transcription agent. Your job is to faithfully transcribe
all visible text from the provided image into clean markdown.

Rules:
- Transcribe ALL text exactly as it appears — do not paraphrase or summarize.
- Preserve the original structure: headings, paragraphs, lists, emphasis.
- Use markdown headings (#, ##, ###) for titles and section headers.
- If the image shows two pages side by side, transcribe left page first, then right.
- For images or photos, insert a brief description: [Image: description].
- Do NOT add commentary, introductions, or explanations.
- Output ONLY the transcribed text.
"""


def _prepare_image(path: Path, max_bytes: int = 4_500_000) -> bytes:
    """Read an image, resizing if it exceeds max_bytes.

    Uses Pillow to progressively downscale large images while
    maintaining aspect ratio and readability for vision models.
    Returns the image as PNG or JPEG bytes.
    """
    raw = path.read_bytes()
    if len(raw) <= max_bytes:
        return raw

    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(raw))

    # Convert RGBA to RGB for JPEG compatibility
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Progressively downscale until under the limit
    quality = 85
    for scale in [0.75, 0.5, 0.4, 0.3, 0.25]:
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        resized = img.resize((new_w, new_h), Image.LANCZOS)

        buf = BytesIO()
        resized.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= max_bytes:
            return buf.getvalue()

    # Last resort: aggressive compression
    buf = BytesIO()
    resized.save(buf, format="JPEG", quality=60)
    return buf.getvalue()


def is_image_file(path: Path) -> bool:
    """Check if a file path has a supported image extension."""
    return path.suffix.lower() in _IMAGE_EXTENSIONS


def convert_image(
    path: Path,
    llm_client: LLMClientProtocol,
) -> str:
    """Convert an image to markdown using a vision-capable LLM.

    Sends the image as a base64-encoded data URL to the LLM and
    returns the extracted text as markdown.

    Args:
        path: Path to the image file.
        llm_client: An LLM client with a complete() method that
            supports multimodal messages (image_url content type).

    Raises:
        ValueError: If the file is not a supported image format.
    """
    if not is_image_file(path):
        raise ValueError(
            f"{path.name} is not a supported image format. "
            f"Supported: {', '.join(sorted(_IMAGE_EXTENSIONS))}"
        )

    # Read image, resize if needed to stay under API limits (5MB)
    raw_bytes = path.read_bytes()
    image_bytes = _prepare_image(path, max_bytes=4_500_000)
    # If we had to resize, it's now JPEG regardless of original format
    if len(raw_bytes) > 4_500_000:
        mime_type = "image/jpeg"
    else:
        mime_type = _IMAGE_MIME_TYPES.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{b64}"

    # Build multimodal message with proper content blocks format
    # (OpenAI/litellm standard for vision models)
    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Transcribe all visible text from this "
                    "image into markdown. Preserve the exact "
                    "wording, structure, and formatting.",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
            ],
        },
    ]

    response = llm_client.complete(
        messages=messages,
        system=_VISION_SYSTEM_PROMPT,
    )
    return response.content  # type: ignore[union-attr] — Protocol.complete returns object, but LLM clients return objects with .content


def clip_web(url: str, output_dir: Path) -> tuple[str, list[Path]]:
    """Fetch a URL, extract content as markdown, download assets.

    Returns a tuple of (markdown_content, list_of_downloaded_asset_paths).
    """
    from markitdown import MarkItDown

    # Download the page to a temp file
    output_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    temp_html = output_dir / f"_web_{url_hash}.html"

    urllib.request.urlretrieve(url, temp_html)

    # Convert to markdown
    converter = MarkItDown()
    result = converter.convert(str(temp_html))

    # Clean up temp file
    temp_html.unlink(missing_ok=True)

    return result.text_content, []


@dataclass
class DedupMatch:
    """A near-duplicate match result."""

    key: str
    similarity: float


def check_dedup(content: str, existing_hashes: dict[str, str]) -> list[DedupMatch]:
    """Check for near-duplicate content using simple n-gram similarity.

    Compares the content's shingle set against existing entries.
    Returns a list of matches above the similarity threshold (0.8).

    Uses a simple Jaccard similarity on 3-gram shingle sets as a
    lightweight approximation of simhash/minhash. Sufficient for
    v1 deduplication; can be upgraded to proper minhash later.
    """
    threshold = 0.8
    content_shingles = _shingle(content)

    if not content_shingles:
        return []

    matches: list[DedupMatch] = []
    for key, existing_text in existing_hashes.items():
        existing_shingles = _shingle(existing_text)
        if not existing_shingles:
            continue
        similarity = _jaccard(content_shingles, existing_shingles)
        if similarity >= threshold:
            matches.append(DedupMatch(key=key, similarity=similarity))

    return sorted(matches, key=lambda m: m.similarity, reverse=True)


def _shingle(text: str, n: int = 3) -> set[str]:
    """Generate n-gram character shingles from text."""
    text = text.lower().strip()
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0
