"""Tests for screenshot_vision.py - load_api_key (mocked)."""
import os
from unittest.mock import patch
import pytest
import screenshot_vision as vision


class TestScreenshotVisionApiKey:
    def test_load_api_key_from_env(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-123"}, clear=False):
            assert vision.load_api_key() == "test-key-123"
