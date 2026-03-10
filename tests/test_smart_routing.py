"""Tests for providers.context — smart routing (resolve_model) and message building."""
import os
from unittest.mock import patch

import pytest

from providers.context import (
    resolve_model,
    build_messages_with_memory,
    _detect_clipboard_group,
    MODE_TO_GROUP,
)


class TestModeToGroupMapping:
    """Verify the mode → group mapping is correct per the plan."""

    def test_backtick_is_fast(self):
        assert MODE_TO_GROUP["backtick"] == "fast"

    def test_extension_is_fast(self):
        assert MODE_TO_GROUP["extension"] == "fast"

    def test_live_is_fast(self):
        assert MODE_TO_GROUP["live"] == "fast"

    def test_clipboard_is_fast(self):
        assert MODE_TO_GROUP["clipboard"] == "fast"

    def test_clipboard_with_instruction_is_powerful(self):
        assert MODE_TO_GROUP["clipboard_with_instruction"] == "powerful"

    def test_explanation_is_reasoning(self):
        assert MODE_TO_GROUP["explanation"] == "reasoning"

    def test_prompt_is_powerful(self):
        assert MODE_TO_GROUP["prompt"] == "powerful"


class TestDetectClipboardGroup:
    """Test clipboard content classification."""

    def test_code_content_returns_powerful(self):
        code = """def two_sum(nums, target):
    hash_map = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in hash_map:
            return [hash_map[complement], i]
        hash_map[num] = i"""
        assert _detect_clipboard_group(code) == "powerful"

    def test_plain_text_returns_fast(self):
        text = "Please fix the grammar in this sentence for me."
        assert _detect_clipboard_group(text) == "fast"

    def test_empty_returns_fast(self):
        assert _detect_clipboard_group("") == "fast"
        assert _detect_clipboard_group(None) == "fast"

    def test_email_text_returns_fast(self):
        email = "Hi John, thanks for the update. Let me know when you're free to discuss."
        assert _detect_clipboard_group(email) == "fast"

    def test_javascript_code_returns_powerful(self):
        code = """function fetchData() {
    const response = await fetch('/api/data');
    const data = await response.json();
    return data;
}"""
        assert _detect_clipboard_group(code) == "powerful"


class TestResolveModel:
    """Test resolve_model picks correct model for agent + mode combinations."""

    def test_specific_agent_returns_that_model(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}, clear=True):
            model = resolve_model("groq/llama-3.3-70b-versatile", "prompt")
            assert model == "groq/llama-3.3-70b-versatile"

    def test_auto_backtick_picks_fast(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}, clear=True):
            model = resolve_model("auto", "backtick")
            assert model is not None

    def test_auto_prompt_picks_powerful(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "dsk_test"}, clear=True):
            model = resolve_model("auto", "prompt")
            assert model is not None
            assert "deepseek" in model

    def test_auto_with_no_providers_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            model = resolve_model("auto", "backtick")
            assert model is None

    def test_auto_clipboard_code_picks_powerful(self):
        code = "def main():\n    pass\n    for i in range(10):\n        print(i)"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "dsk_test"}, clear=True):
            model = resolve_model("auto", "clipboard", code)
            assert model is not None

    def test_auto_clipboard_text_picks_fast(self):
        text = "Hey, just wanted to check in about the meeting tomorrow."
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}, clear=True):
            model = resolve_model("auto", "clipboard", text)
            assert model is not None


class TestBuildMessagesWithMemory:
    """Test memory message injection."""

    def test_no_memory_returns_original(self):
        messages = [{"role": "user", "content": "hello"}]
        result = build_messages_with_memory(messages, None)
        assert result == messages

    def test_empty_memory_returns_original(self):
        messages = [{"role": "user", "content": "hello"}]
        result = build_messages_with_memory(messages, [])
        assert result == messages

    def test_memory_inserted_between_system_and_user(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
        ]
        memory = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        result = build_messages_with_memory(messages, memory)
        assert len(result) == 4
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "previous question"
        assert result[2]["role"] == "assistant"
        assert result[3]["role"] == "user"
        assert result[3]["content"] == "hello"

    def test_memory_without_system_message(self):
        messages = [{"role": "user", "content": "hello"}]
        memory = [
            {"role": "user", "content": "prev"},
            {"role": "assistant", "content": "ans"},
        ]
        result = build_messages_with_memory(messages, memory)
        assert len(result) == 3
        assert result[0]["content"] == "prev"
        assert result[2]["content"] == "hello"

    def test_duplicate_memory_already_in_chat_is_filtered(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "my name is Raj"},
            {"role": "assistant", "content": "Nice to meet you, Raj."},
            {"role": "user", "content": "what do you know about me?"},
        ]
        memory = [
            {"role": "user", "content": "my name is Raj"},
            {"role": "assistant", "content": "Nice to meet you, Raj."},
            {"role": "user", "content": "I work on Prod Layer"},
            {"role": "assistant", "content": "I'll remember that."},
        ]
        result = build_messages_with_memory(messages, memory)
        assert result[0]["role"] == "system"
        assert result[1]["content"] == "I work on Prod Layer"
        assert result[2]["content"] == "I'll remember that."
        assert result[-1]["content"] == "what do you know about me?"
        assert sum(1 for m in result if m["content"] == "my name is Raj") == 1
