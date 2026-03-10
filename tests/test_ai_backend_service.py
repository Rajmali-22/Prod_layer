"""Tests for ai_backend_service.py — clean_response, build_messages, handle_request with ProviderManager."""
import json
import os
import sys
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

import ai_backend_service as svc


class TestCleanResponse:
    """Test clean_response strips subject lines and normalizes text."""

    def test_clean_response_empty(self):
        assert svc.clean_response("") == ""
        assert svc.clean_response(None) == ""

    def test_clean_response_strips_subject_line_and_next_blank(self):
        text = "Subject: Hello\n\nBody line one.\nBody line two."
        assert "Subject:" not in svc.clean_response(text)
        assert "Body line one" in svc.clean_response(text)

    def test_clean_response_preserves_normal_lines(self):
        text = "Line one.\nLine two.\nLine three."
        assert svc.clean_response(text) == text

    def test_clean_response_strips_whitespace(self):
        text = "  Hello world  \n  Second line  "
        assert svc.clean_response(text).strip() == svc.clean_response(text)


class TestBuildMessages:
    """Test build_messages for each mode."""

    def test_build_messages_backtick_mode(self):
        messages = svc.build_messages("fix this sentance", {"mode": "backtick"})
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "autocorrect" in messages[0]["content"].lower()
        assert messages[1]["content"] == "fix this sentance"

    def test_build_messages_extension_mode_includes_last_output(self):
        messages = svc.build_messages("original", {"mode": "extension", "last_output": "Previous text."})
        assert len(messages) == 1
        assert "Previous text." in messages[0]["content"]
        assert "original" in messages[0]["content"]

    def test_build_messages_clipboard_mode(self):
        messages = svc.build_messages("two sum problem", {"mode": "clipboard"})
        assert len(messages) == 2
        assert "CODE" in messages[0]["content"] or "clipboard" in messages[0]["content"].lower()

    def test_build_messages_prompt_mode_default_tone(self):
        messages = svc.build_messages("Write a greeting", {"mode": "prompt"})
        assert len(messages) == 1
        assert "professional" in messages[0]["content"].lower() or "TONE" in messages[0]["content"]

    def test_build_messages_explanation_mode_includes_code(self):
        messages = svc.build_messages("two sum", {"mode": "explanation", "code": "def two_sum(): pass"})
        assert len(messages) == 2
        assert "def two_sum" in messages[1]["content"]
        assert "Explain" in messages[0]["content"] or "interview" in messages[0]["content"].lower()

    def test_build_messages_clipboard_with_instruction(self):
        messages = svc.build_messages("some text", {"mode": "clipboard_with_instruction", "instruction": "summarize"})
        assert len(messages) == 2
        assert "summarize" in messages[1]["content"]
        assert "some text" in messages[1]["content"]


class TestHandleRequest:
    """Test handle_request command routing (with mocked ProviderManager and IPC)."""

    def _make_mock_pm(self):
        pm = MagicMock()
        pm.resolve_model.return_value = "groq/llama-3.3-70b-versatile"
        pm.get_model_group.return_value = "fast"
        pm.get_memory_history.return_value = []
        pm.get_available_agents.return_value = [
            {"value": "auto", "label": "Auto", "group": "auto"},
        ]
        pm.test_provider.return_value = {"success": True, "message": "ok"}
        return pm

    def test_handle_request_ping_sends_pong(self):
        pm = self._make_mock_pm()
        with patch.object(svc.IPC, "send") as mock_send:
            svc.handle_request({"cmd": "ping"}, pm)
            mock_send.assert_called()
            call_arg = mock_send.call_args[0][0]
            assert call_arg.get("event") == "pong"

    def test_handle_request_unknown_command_sends_error(self):
        pm = self._make_mock_pm()
        with patch.object(svc.IPC, "send_error") as mock_err:
            svc.handle_request({"cmd": "unknown_cmd"}, pm)
            mock_err.assert_called_once()
            assert "Unknown command" in mock_err.call_args[0][0]

    def test_handle_request_generate_empty_prompt_sends_complete_with_error(self):
        pm = self._make_mock_pm()
        with patch.object(svc.IPC, "send") as mock_send:
            svc.handle_request({"cmd": "generate", "prompt": "", "context": {}}, pm)
            call_arg = mock_send.call_args[0][0]
            assert call_arg.get("event") == "complete"
            assert "error" in call_arg or call_arg.get("text") == ""

    def test_handle_request_shutdown_returns_shutdown(self):
        pm = self._make_mock_pm()
        with patch.object(svc.IPC, "send"):
            result = svc.handle_request({"cmd": "shutdown"}, pm)
            assert result == "shutdown"

    def test_handle_request_get_agents(self):
        pm = self._make_mock_pm()
        with patch.object(svc.IPC, "send") as mock_send:
            svc.handle_request({"cmd": "get_agents"}, pm)
            mock_send.assert_called()
            call_arg = mock_send.call_args[0][0]
            assert call_arg.get("event") == "agents"
            assert isinstance(call_arg.get("agents"), list)

    def test_handle_request_test_provider(self):
        pm = self._make_mock_pm()
        with patch.object(svc.IPC, "send") as mock_send:
            svc.handle_request({"cmd": "test_provider", "model": "groq/llama-3.3-70b-versatile"}, pm)
            mock_send.assert_called()
            call_arg = mock_send.call_args[0][0]
            assert call_arg.get("event") == "test_result"
            assert call_arg.get("success") is True

    def test_handle_request_test_provider_no_model(self):
        pm = self._make_mock_pm()
        with patch.object(svc.IPC, "send_error") as mock_err:
            svc.handle_request({"cmd": "test_provider"}, pm)
            mock_err.assert_called_once()


class TestChatMemory:
    def test_generate_streaming_with_messages_attaches_memory(self):
        pm = MagicMock()
        pm.resolve_model.return_value = "deepseek/deepseek-chat"
        pm.get_model_group.return_value = "powerful"
        pm.get_memory_history.return_value = [
            {"role": "user", "content": "my name is Raj"},
            {"role": "assistant", "content": "I know your name is Raj."},
        ]
        pm.stream.return_value = iter(["I remember your name is Raj."])

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "what do you know about me?"},
        ]

        with patch.object(svc.IPC, "send_chunk"):
            result = svc.generate_streaming_with_messages(
                messages,
                {"mode": "chat", "window": "chat", "agent": "auto"},
                pm,
            )

        assert result == "I remember your name is Raj."
        streamed_messages = pm.stream.call_args[0][1]
        assert any(m["content"] == "my name is Raj" for m in streamed_messages)
        pm.store_interaction.assert_called_once()
