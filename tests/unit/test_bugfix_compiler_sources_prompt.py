"""Tests for Bug 3: Compiler prompt should instruct LLM to use template source names."""

from __future__ import annotations

from assistonauts.agents.compiler import _COMPILER_SYSTEM_PROMPT


class TestCompilerSystemPromptSourceInstruction:
    """Bug 3: System prompt should tell the LLM to use template source names."""

    def test_system_prompt_instructs_template_sources(self) -> None:
        """The system prompt should explicitly instruct the LLM to use
        the source filenames from the template, not from raw content."""
        # Must contain an explicit instruction about using template source names
        # in the frontmatter output, not the ones from the raw content
        assert "template" in _COMPILER_SYSTEM_PROMPT.lower()
        assert "source" in _COMPILER_SYSTEM_PROMPT.lower()
        # The key instruction: use template sources for frontmatter, not raw content
        has_instruction = (
            "not from the raw" in _COMPILER_SYSTEM_PROMPT.lower()
            or "not from the source material" in _COMPILER_SYSTEM_PROMPT.lower()
        )
        assert has_instruction, (
            "System prompt must warn against using source names from raw content"
        )
