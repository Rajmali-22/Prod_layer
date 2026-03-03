"""
ProviderManager — single entry point for the multi-LLM provider system.

Wraps the router (model selection), context (smart routing), and memory
into one interface consumed by ai_backend_service.py.
"""

import os
import sys
import litellm

from providers.router import (
    discover_available_models,
    get_available_agents,
    pick_model_for_group,
    pick_model_for_group_excluding,
    PROVIDER_REGISTRY,
)
from providers.context import resolve_model, build_messages_with_memory
from providers.memory import MemoryManager

# Suppress litellm debug noise
litellm.suppress_debug_info = True
litellm.set_verbose = False


class ProviderManager:
    """
    Unified interface for multi-provider LLM access.

    Usage:
        pm = ProviderManager()
        model = pm.resolve_model(agent="auto", mode="backtick", prompt="fix this")
        for chunk in pm.stream(model, messages):
            ...
        pm.store_interaction(window_title, prompt, response, group)
    """

    def __init__(self):
        self.available = discover_available_models()
        self.memory = MemoryManager()
        self._failed_models = set()  # models that failed auth — skip on fallback

        # Count total available models
        total = sum(len(v) for v in self.available.values())
        if total == 0:
            print(
                "[WARN] No LLM provider keys found. "
                "Set at least one API key (e.g. MISTRAL_API_KEY, GROQ_API_KEY).",
                file=sys.stderr,
            )

    def has_any_provider(self):
        """Check if at least one provider is configured."""
        return any(len(v) > 0 for v in self.available.values())

    def get_available_agents(self):
        """Return agent list for UI dropdown."""
        return get_available_agents()

    def resolve_model(self, agent="auto", mode="prompt", prompt=""):
        """Pick the right model string for the given context."""
        return resolve_model(agent, mode, prompt)

    def get_model_group(self, model_string):
        """Return the group (fast/powerful/reasoning) for a model string."""
        for _env, reg_model, group, _name in PROVIDER_REGISTRY:
            if reg_model == model_string:
                return group
        return "powerful"  # default

    def mark_model_failed(self, model_string):
        """Mark a model as failed (e.g. bad API key). It will be skipped on future fallbacks."""
        self._failed_models.add(model_string)
        print(f"[WARN] Model marked as failed: {model_string}", file=sys.stderr)

    def get_fallback_model(self, failed_model):
        """
        Get the next available model after a failure, skipping all previously failed models.
        Uses the same group as the failed model, with fallback chain.
        Returns model_string or None if no alternatives exist.
        """
        self._failed_models.add(failed_model)
        group = self.get_model_group(failed_model)
        return pick_model_for_group_excluding(group, self._failed_models, self.available)

    def stream(self, model, messages):
        """
        Stream a completion from LiteLLM.
        Yields chunk text strings.
        """
        response = litellm.completion(
            model=model,
            messages=messages,
            stream=True,
        )

        for part in response:
            choices = part.get("choices", []) if isinstance(part, dict) else getattr(part, "choices", [])
            for choice in choices:
                delta = choice.get("delta", {}) if isinstance(choice, dict) else getattr(choice, "delta", None)
                if delta:
                    content = delta.get("content", "") if isinstance(delta, dict) else getattr(delta, "content", "")
                    if content:
                        yield content

    def complete(self, model, messages):
        """
        Non-streaming completion. Returns full text.
        """
        response = litellm.completion(
            model=model,
            messages=messages,
            stream=False,
        )
        choices = response.get("choices", []) if isinstance(response, dict) else getattr(response, "choices", [])
        if choices:
            msg = choices[0].get("message", {}) if isinstance(choices[0], dict) else getattr(choices[0], "message", None)
            if msg:
                return msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        return ""

    def get_memory_history(self, window_title, group="powerful", mode="prompt"):
        """Get conversation history for a window."""
        return self.memory.get_history(window_title, group, mode)

    def store_interaction(self, window_title, user_prompt, assistant_response, group="powerful", mode="prompt"):
        """Store a user/assistant exchange in per-window memory."""
        self.memory.store_interaction(window_title, user_prompt, assistant_response, group, mode)

    def test_provider(self, model_string):
        """
        Test a provider with a simple completion.
        Returns {"success": True/False, "message": str}
        """
        try:
            response = litellm.completion(
                model=model_string,
                messages=[{"role": "user", "content": "Say 'ok' in one word."}],
                max_tokens=5,
                stream=False,
            )
            choices = response.get("choices", []) if isinstance(response, dict) else getattr(response, "choices", [])
            if choices:
                return {"success": True, "message": "Provider working"}
            return {"success": False, "message": "No response from provider"}
        except Exception as e:
            return {"success": False, "message": str(e)}
