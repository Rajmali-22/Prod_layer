"""
LiteLLM Router — model groups, auto-discovery, and fallback chains.

Groups:
  fast      → low-latency models for grammar, autocomplete, live suggestions
  powerful  → high-quality models for code gen, complex tasks
  reasoning → chain-of-thought models for explanations
"""

import os
import litellm

# Suppress litellm info logs (keep warnings/errors)
litellm.suppress_debug_info = True

# ══════════════════════════════════════════════════════════════════════════════
# PROVIDER REGISTRY — maps (provider, env_var) → list of (model_string, group)
# ══════════════════════════════════════════════════════════════════════════════

PROVIDER_REGISTRY = [
    # (env_var, litellm_model_string, group, display_name)
    ("GROQ_API_KEY",          "groq/llama-3.3-70b-versatile",                        "fast",      "Groq Llama 3.3 70B"),
    ("MISTRAL_API_KEY",       "mistral/mistral-small-latest",                        "fast",      "Mistral Small"),
    ("OPENAI_API_KEY",        "openai/gpt-4o-mini",                                  "fast",      "GPT-4o Mini"),
    ("GEMINI_API_KEY",        "gemini/gemini-2.0-flash",                             "fast",      "Gemini 2.0 Flash"),
    ("DEEPSEEK_API_KEY",      "deepseek/deepseek-chat",                              "powerful",  "DeepSeek Chat"),
    ("ANTHROPIC_API_KEY",     "anthropic/claude-sonnet-4-20250514",                   "powerful",  "Claude Sonnet"),
    ("OPENAI_API_KEY",        "openai/gpt-4o",                                       "powerful",  "GPT-4o"),
    ("XAI_API_KEY",           "xai/grok-2-latest",                                   "powerful",  "Grok 2"),
    ("TOGETHERAI_API_KEY",    "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo", "powerful",  "Together Llama 3.3 70B"),
    ("PERPLEXITYAI_API_KEY",  "perplexity/sonar-pro",                                "powerful",  "Perplexity Sonar Pro"),
    ("COHERE_API_KEY",        "cohere_chat/command-r-plus",                           "powerful",  "Cohere Command R+"),
    ("REPLICATE_API_TOKEN",   "replicate/meta/meta-llama-3.1-405b-instruct",         "powerful",  "Replicate Llama 405B"),
    ("DEEPSEEK_API_KEY",      "deepseek/deepseek-reasoner",                          "reasoning", "DeepSeek Reasoner"),
]

# Fallback group order: if requested group has no providers, try these
GROUP_FALLBACK_ORDER = {
    "fast":      ["fast", "powerful", "reasoning"],
    "powerful":  ["powerful", "fast", "reasoning"],
    "reasoning": ["reasoning", "powerful", "fast"],
}


def discover_available_models():
    """
    Scan environment variables and return available models grouped by category.
    Returns: {group: [(model_string, display_name), ...]}
    """
    available = {"fast": [], "powerful": [], "reasoning": []}
    seen_models = set()

    for env_var, model_string, group, display_name in PROVIDER_REGISTRY:
        key = os.environ.get(env_var, "")
        if key and "your-" not in key and model_string not in seen_models:
            available[group].append((model_string, display_name))
            seen_models.add(model_string)

    return available


def get_available_agents():
    """
    Return a list of agent choices for the UI dropdown.
    Format: [{value, label, group}, ...]
    Only includes models whose API keys are configured.
    """
    available = discover_available_models()
    agents = [{"value": "auto", "label": "Auto", "group": "auto"}]

    for group in ["fast", "powerful", "reasoning"]:
        for model_string, display_name in available[group]:
            agents.append({
                "value": model_string,
                "label": display_name,
                "group": group,
            })

    return agents


def pick_model_for_group(group, available=None):
    """
    Pick the first available model in the given group.
    Falls back through GROUP_FALLBACK_ORDER if group is empty.
    Returns model_string or None.
    """
    if available is None:
        available = discover_available_models()

    fallback_chain = GROUP_FALLBACK_ORDER.get(group, [group])

    for fallback_group in fallback_chain:
        models = available.get(fallback_group, [])
        if models:
            return models[0][0]  # first model's string

    return None


def pick_specific_model(model_string):
    """
    Validate that a specific model string's provider key is available.
    Returns the model_string if valid, None otherwise.
    """
    for env_var, reg_model, _group, _name in PROVIDER_REGISTRY:
        if reg_model == model_string:
            key = os.environ.get(env_var, "")
            if key and "your-" not in key:
                return model_string
            return None
    # Unknown model string — let litellm try it anyway
    return model_string


def pick_model_for_group_excluding(group, exclude_models, available=None):
    """
    Pick the first available model in the given group, skipping models in
    the exclude set. Falls back through GROUP_FALLBACK_ORDER.
    Returns model_string or None.
    """
    if available is None:
        available = discover_available_models()

    fallback_chain = GROUP_FALLBACK_ORDER.get(group, [group])

    for fallback_group in fallback_chain:
        models = available.get(fallback_group, [])
        for model_string, _name in models:
            if model_string not in exclude_models:
                return model_string

    return None
