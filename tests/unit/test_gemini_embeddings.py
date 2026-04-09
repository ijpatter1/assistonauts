"""Tests for Gemini embedding support via litellm and multimodal embedding."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from assistonauts.archivist.embeddings import (
    LiteLLMEmbeddingClient,
    create_embedding_client,
)
from assistonauts.models.config import EmbeddingConfig, EmbeddingProviderConfig


class TestLiteLLMMultimodal:
    """Test multimodal embedding support on LiteLLMEmbeddingClient."""

    def _mock_litellm(self, embeddings: list[list[float]]) -> MagicMock:
        """Create a mock litellm module returning the given embeddings."""
        mock = MagicMock()
        mock.embedding.return_value = MagicMock(
            data=[{"embedding": e} for e in embeddings]
        )
        return mock

    def test_embed_content_encodes_base64_data_uri(self) -> None:
        """embed_content() should encode bytes as a data URI and call litellm."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=3,
        )
        raw_bytes = b"\x89PNG fake image"
        expected_b64 = base64.b64encode(raw_bytes).decode("ascii")
        expected_uri = f"data:image/png;base64,{expected_b64}"

        mock_litellm = self._mock_litellm([[0.1, 0.2, 0.3]])
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = client.embed_content(raw_bytes, "image/png")

        assert result == [0.1, 0.2, 0.3]
        mock_litellm.embedding.assert_called_once_with(
            model="gemini/gemini-embedding-2-preview",
            input=[expected_uri],
        )

    def test_embed_content_returns_list_of_floats(self) -> None:
        """embed_content() return type should be list[float]."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=2,
        )
        mock_litellm = self._mock_litellm([[0.5, 0.6]])
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = client.embed_content(b"data", "application/pdf")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_embed_multimodal_text_and_image(self) -> None:
        """embed_multimodal() should handle mixed text + binary parts."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=2,
        )
        image_bytes = b"\x89PNG"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        expected_inputs = [
            "caption text",
            f"data:image/png;base64,{b64}",
        ]

        mock_litellm = self._mock_litellm([[0.7, 0.8], [0.9, 1.0]])
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = client.embed_multimodal(
                [
                    {"text": "caption text"},
                    {"data": image_bytes, "mime_type": "image/png"},
                ]
            )

        # Returns first embedding
        assert result == [0.7, 0.8]
        mock_litellm.embedding.assert_called_once_with(
            model="gemini/gemini-embedding-2-preview",
            input=expected_inputs,
        )

    def test_embed_multimodal_text_only(self) -> None:
        """embed_multimodal() with only text parts should work."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=2,
        )
        mock_litellm = self._mock_litellm([[0.1, 0.2]])
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = client.embed_multimodal([{"text": "hello"}])
        assert result == [0.1, 0.2]

    def test_embed_multimodal_empty_parts_raises(self) -> None:
        """embed_multimodal() with empty parts should raise ValueError."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=2,
        )
        with pytest.raises(ValueError, match="No valid parts"):
            client.embed_multimodal([])

    def test_embed_multimodal_invalid_data_type_raises(self) -> None:
        """embed_multimodal() with non-bytes data should raise TypeError."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=2,
        )
        with pytest.raises(TypeError, match="Expected bytes"):
            client.embed_multimodal([{"data": "not bytes", "mime_type": "image/png"}])

    def test_embed_uses_call_litellm(self) -> None:
        """embed() should use _call_litellm internally."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=2,
        )
        mock_litellm = self._mock_litellm([[0.3, 0.4]])
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = client.embed("test text")
        assert result == [0.3, 0.4]

    def test_embed_batch_calls_litellm_once(self) -> None:
        """embed_batch() should make a single litellm call."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            dimensions=2,
        )
        mock_litellm = self._mock_litellm([[0.1, 0.2], [0.3, 0.4]])
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = client.embed_batch(["text one", "text two"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        mock_litellm.embedding.assert_called_once()

    def test_base_url_passed_to_litellm(self) -> None:
        """base_url should be passed as api_base when set."""
        client = LiteLLMEmbeddingClient(
            model="gemini/gemini-embedding-2-preview",
            base_url="http://custom:8080",
            dimensions=2,
        )
        mock_litellm = self._mock_litellm([[0.1, 0.2]])
        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            client.embed("test")
        mock_litellm.embedding.assert_called_once_with(
            model="gemini/gemini-embedding-2-preview",
            input=["test"],
            api_base="http://custom:8080",
        )


class TestGetEmbeddingDimensions:
    """Test the get_embedding_dimensions helper."""

    def test_gemini_config_returns_768(self) -> None:
        from assistonauts.archivist.embeddings import get_embedding_dimensions

        config = EmbeddingConfig(
            active="gemini",
            providers={
                "gemini": EmbeddingProviderConfig(
                    model="gemini-embedding-2-preview", dimensions=768
                )
            },
        )
        assert get_embedding_dimensions(config) == 768

    def test_ollama_config_returns_384(self) -> None:
        from assistonauts.archivist.embeddings import get_embedding_dimensions

        config = EmbeddingConfig(
            active="ollama",
            providers={
                "ollama": EmbeddingProviderConfig(
                    model="nomic-embed-text", dimensions=384
                )
            },
        )
        assert get_embedding_dimensions(config) == 384

    def test_empty_config_defaults_to_768(self) -> None:
        from assistonauts.archivist.embeddings import get_embedding_dimensions

        assert get_embedding_dimensions(EmbeddingConfig()) == 768

    def test_no_dimensions_defaults_to_768(self) -> None:
        from assistonauts.archivist.embeddings import get_embedding_dimensions

        config = EmbeddingConfig(
            active="gemini",
            providers={
                "gemini": EmbeddingProviderConfig(model="gemini-embedding-2-preview")
            },
        )
        assert get_embedding_dimensions(config) == 768


class TestEmbeddingClientABCMultimodal:
    """Test that the ABC has optional multimodal methods with NotImplementedError."""

    def test_embed_content_raises_not_implemented_by_default(self) -> None:
        from tests.helpers import FakeEmbeddingClient

        client = FakeEmbeddingClient(dimensions=4)
        with pytest.raises(NotImplementedError):
            client.embed_content(b"data", "image/png")

    def test_embed_multimodal_raises_not_implemented_by_default(self) -> None:
        from tests.helpers import FakeEmbeddingClient

        client = FakeEmbeddingClient(dimensions=4)
        with pytest.raises(NotImplementedError):
            client.embed_multimodal([{"text": "hello"}])


class TestEmbeddingProviderConfigDimensions:
    """Test that EmbeddingProviderConfig supports dimensions field."""

    def test_dimensions_field_exists(self) -> None:
        config = EmbeddingProviderConfig(model="test", dimensions=768)
        assert config.dimensions == 768

    def test_dimensions_defaults_to_none(self) -> None:
        config = EmbeddingProviderConfig(model="test")
        assert config.dimensions is None


class TestCreateEmbeddingClientFactory:
    """Test the create_embedding_client factory function."""

    def test_gemini_provider_creates_litellm_client_with_prefix(self) -> None:
        """gemini provider should create LiteLLMEmbeddingClient with gemini/ prefix."""
        config = EmbeddingConfig(
            active="gemini",
            providers={
                "gemini": EmbeddingProviderConfig(
                    model="gemini-embedding-2-preview",
                    dimensions=768,
                ),
            },
        )
        client = create_embedding_client(config)
        assert isinstance(client, LiteLLMEmbeddingClient)
        assert client._model == "gemini/gemini-embedding-2-preview"
        assert client.dimensions == 768

    def test_gemini_provider_default_dimensions(self) -> None:
        """gemini provider without explicit dimensions should default to 768."""
        config = EmbeddingConfig(
            active="gemini",
            providers={
                "gemini": EmbeddingProviderConfig(model="gemini-embedding-2-preview"),
            },
        )
        client = create_embedding_client(config)
        assert isinstance(client, LiteLLMEmbeddingClient)
        assert client.dimensions == 768

    def test_ollama_provider_creates_litellm_client(self) -> None:
        config = EmbeddingConfig(
            active="ollama",
            providers={
                "ollama": EmbeddingProviderConfig(
                    model="nomic-embed-text",
                    base_url="http://localhost:11434",
                    dimensions=384,
                ),
            },
        )
        client = create_embedding_client(config)
        assert isinstance(client, LiteLLMEmbeddingClient)
        assert client._model == "ollama/nomic-embed-text"
        assert client.dimensions == 384

    def test_already_prefixed_model_not_double_prefixed(self) -> None:
        """If model already has provider prefix, don't add another."""
        config = EmbeddingConfig(
            active="gemini",
            providers={
                "gemini": EmbeddingProviderConfig(
                    model="gemini/gemini-embedding-2-preview",
                ),
            },
        )
        client = create_embedding_client(config)
        assert isinstance(client, LiteLLMEmbeddingClient)
        assert client._model == "gemini/gemini-embedding-2-preview"

    def test_unknown_provider_returns_none(self) -> None:
        config = EmbeddingConfig(active="nonexistent", providers={})
        assert create_embedding_client(config) is None

    def test_empty_config_returns_none(self) -> None:
        config = EmbeddingConfig()
        assert create_embedding_client(config) is None

    def test_missing_model_returns_none(self) -> None:
        config = EmbeddingConfig(
            active="gemini",
            providers={"gemini": EmbeddingProviderConfig()},
        )
        assert create_embedding_client(config) is None


class TestConfigLoaderDimensions:
    """Test that config loader parses dimensions from YAML."""

    def test_dimensions_parsed_from_yaml(self, tmp_path: str) -> None:
        from pathlib import Path

        from assistonauts.config.loader import load_config

        workspace = Path(str(tmp_path))
        config_dir = workspace / ".assistonauts"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            "embedding:\n"
            "  active: gemini\n"
            "  providers:\n"
            "    gemini:\n"
            "      model: gemini-embedding-2-preview\n"
            "      dimensions: 768\n"
        )
        config = load_config(workspace)
        provider = config.embedding.providers["gemini"]
        assert provider.dimensions == 768

    def test_dimensions_absent_defaults_to_none(self, tmp_path: str) -> None:
        from pathlib import Path

        from assistonauts.config.loader import load_config

        workspace = Path(str(tmp_path))
        config_dir = workspace / ".assistonauts"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            "embedding:\n"
            "  active: ollama\n"
            "  providers:\n"
            "    ollama:\n"
            "      model: nomic-embed-text\n"
        )
        config = load_config(workspace)
        provider = config.embedding.providers["ollama"]
        assert provider.dimensions is None
