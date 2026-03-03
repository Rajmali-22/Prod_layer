"""
Smart routing + memory-enhanced message builder.

resolve_model() — picks the right model based on agent selection, trigger mode, and prompt.
build_messages_with_memory() — prepends conversation history to the message list.
"""

from providers.router import pick_model_for_group, pick_specific_model, discover_available_models

# ══════════════════════════════════════════════════════════════════════════════
# SMART AUTO-ROUTING (when agent == "auto")
# ══════════════════════════════════════════════════════════════════════════════

# mode → model group mapping
MODE_TO_GROUP = {
    "backtick":                 "fast",
    "extension":                "fast",
    "live":                     "fast",
    "clipboard":                "fast",       # default for clipboard; overridden below for code
    "clipboard_with_instruction": "powerful",
    "explanation":              "reasoning",
    "prompt":                   "powerful",
    "chat":                     "powerful",
}


def _detect_clipboard_group(prompt):
    """
    For clipboard mode, classify content to pick fast vs powerful.
    Code content → powerful; plain text → fast.
    """
    if not prompt:
        return "fast"

    code_signals = [
        "def ", "class ", "function ", "import ", "from ", "#include",
        "public ", "private ", "const ", "let ", "var ",
        "->", "=>", "&&", "||", "!=", "==",
        "for (", "while (", "if (", "else {",
        "return ", "return[",
    ]
    text_lower = prompt[:2000].lower()
    code_count = sum(1 for sig in code_signals if sig.lower() in text_lower)

    # Also check for indented lines (common in code)
    lines = prompt[:2000].split("\n")
    indented_lines = sum(1 for line in lines if line.startswith("    ") or line.startswith("\t"))

    if code_count >= 2 or (code_count >= 1 and indented_lines >= 2):
        return "powerful"
    return "fast"


def resolve_model(agent, mode, prompt=""):
    """
    Determine the LiteLLM model string to use.

    Parameters:
        agent  — "auto" or a specific litellm model string (e.g. "groq/llama-3.3-70b-versatile")
        mode   — trigger mode: backtick, extension, live, clipboard, clipboard_with_instruction, explanation, prompt
        prompt — the user's text (used for clipboard content classification)

    Returns:
        model_string or None if no provider is available.
    """
    # Specific agent selected by user
    if agent and agent != "auto":
        return pick_specific_model(agent)

    # Auto mode — pick group based on trigger mode
    group = MODE_TO_GROUP.get(mode, "powerful")

    # Special case: clipboard mode depends on content type
    if mode == "clipboard":
        group = _detect_clipboard_group(prompt)

    return pick_model_for_group(group)


def build_messages_with_memory(messages, memory_messages=None):
    """
    Prepend conversation history after the system message, before the user message.
    memory_messages is a list of {"role": ..., "content": ...} dicts from MemoryManager.
    """
    if not memory_messages:
        return messages

    # Find system message (if any) and user messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    # Build: system + memory history + current user messages
    result = []
    result.extend(system_msgs)
    result.extend(memory_messages)
    result.extend(non_system)

    return result
