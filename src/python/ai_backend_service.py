#!/usr/bin/env python3
"""
AI Backend Service - Persistent process with streaming support.

Runs continuously like keystroke_monitor.py.
Communicates via stdin/stdout JSON messages.
Supports streaming responses for low latency.

Uses LiteLLM via ProviderManager for multi-provider support.
"""

import sys
import json
import os
import re
import time

from providers import ProviderManager
from providers.context import build_messages_with_memory

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

API_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2

# ══════════════════════════════════════════════════════════════════════════════
# IPC - Communication with Electron
# ══════════════════════════════════════════════════════════════════════════════

class IPC:
    """Handles stdin/stdout communication with Electron."""

    @staticmethod
    def send(data):
        """Send JSON message to Electron."""
        try:
            print(json.dumps(data), flush=True)
        except Exception:
            pass

    @staticmethod
    def send_error(message):
        """Send error event."""
        IPC.send({"event": "error", "message": message})

    @staticmethod
    def send_chunk(text, is_final=False):
        """Send streaming chunk."""
        IPC.send({
            "event": "chunk",
            "text": text,
            "final": is_final
        })

    @staticmethod
    def send_complete(text):
        """Send complete response."""
        IPC.send({"event": "complete", "text": text})


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def build_messages(prompt, context):
    """Build messages array based on mode."""
    mode = context.get("mode", "prompt") if context else "prompt"

    if mode == "backtick":
        return [
            {
                "role": "system",
                "content": "You are an autocorrect tool. You ONLY fix spelling and grammar. You output ONLY the corrected text. No explanations. No preambles. No extra words. Just the fixed text."
            },
            {"role": "user", "content": prompt}
        ]

    elif mode == "extension":
        last_output = context.get("last_output", "") if context else ""
        structured = f"""You are a writing assistant. Continue writing from where the text left off.

PREVIOUS TEXT:
{last_output}

ORIGINAL CONTEXT:
{prompt}

INSTRUCTIONS:
1. Continue writing naturally from where the previous text ended
2. Maintain the same tone, style, and voice
3. Add 1-2 more sentences that flow naturally
4. Keep the continuation relevant to the context
5. Don't repeat what was already said

IMPORTANT:
- Output ONLY the continuation (new text to append)
- Do NOT repeat the previous text
- Do NOT include explanations
- Make it flow naturally as if it's one continuous piece"""
        return [{"role": "user", "content": structured}]

    elif mode == "clipboard_with_instruction":
        instruction = context.get("instruction", "") if context else ""
        return [
            {
                "role": "system",
                "content": """You follow the user's INSTRUCTION to process the CONTENT. Output ONLY the result with NO preambles, NO explanations.

RULES:
- Follow the instruction exactly
- Output only the requested content
- No "Here's..." or "Sure..." introductions
- Start directly with the output"""
            },
            {"role": "user", "content": f"CONTENT:\n{prompt}\n\nINSTRUCTION: {instruction}"}
        ]

    elif mode == "clipboard":
        return [
            {
                "role": "system",
                "content": """You respond to clipboard content with NO preambles, NO explanations. Output ONLY the response.

RULES:
- CODE: Output only code. No "Here's the code" or explanations. Just the code with proper indentation.
- EMAIL/MESSAGE: Output only the reply text. No "Here's a reply" intro.
- QUESTION: Output only the answer. No "The answer is" intro.
- Start directly with the content. No introductions."""
            },
            {"role": "user", "content": prompt}
        ]

    elif mode == "explanation":
        code = context.get("code", "") if context else ""
        return [
            {
                "role": "system",
                "content": """You are an interview coach explaining code solutions.

OUTPUT FORMAT:
Approach: [1 line - technique name and why]
Key insight: [1 line - the core idea]
Steps: 1. ... 2. ... 3. ...
Time: O(?) Space: O(?)

RULES:
- Keep VERY brief - under 80 words
- NO markdown (no *, no -, no bullets)
- Use numbered steps: 1. 2. 3.
- Focus on WHY not HOW"""
            },
            {"role": "user", "content": f"Problem: {prompt}\n\nCode:\n{code}\n\nExplain briefly for interview."}
        ]

    else:
        # Default prompt mode
        tone = context.get("tone", "normal") if context else "normal"
        tone_instructions = {
            "normal": "Write naturally and clearly. No special tone — just be helpful and direct.",
            "professional": "Use formal, respectful, and business-appropriate language.",
            "casual": "Use friendly, relaxed, and conversational language.",
            "creative": "Use expressive, engaging, and imaginative language.",
            "concise": "Use brief, direct, and to-the-point language."
        }
        tone_guide = tone_instructions.get(tone.lower(), tone_instructions["normal"])

        structured = f"""You are a versatile text assistant. Generate well-structured text content.

USER REQUEST: {prompt}

TONE: {tone}
TONE INSTRUCTIONS: {tone_guide}

IMPORTANT:
- Generate ONLY the text body/content
- Do NOT include titles, headers, or subject lines unless requested
- No explanations or meta-commentary
- Start directly with the content
- Output should be ready to use as-is"""

        return [{"role": "user", "content": structured}]


# ══════════════════════════════════════════════════════════════════════════════
# TEXT GENERATION (STREAMING)
# ══════════════════════════════════════════════════════════════════════════════

def _is_auth_error(error_str):
    """Check if an error is an authentication/authorization failure."""
    auth_signals = ['401', 'unauthorized', 'authentication', 'invalid x-api-key',
                    'invalid api key', 'invalid api_key', 'incorrect api key',
                    'invalid argument', 'forbidden', '403']
    error_lower = error_str.lower()
    return any(sig in error_lower for sig in auth_signals)


def _is_rate_limit_error(error_str):
    """Check if an error is a rate limit / quota exceeded failure."""
    rate_signals = ['429', 'rate limit', 'ratelimit', 'rate_limit',
                    'exceeded your current quota', 'quota exceeded',
                    'too many requests', 'resource exhausted',
                    'insufficient balance']
    error_lower = error_str.lower()
    return any(sig in error_lower for sig in rate_signals)


def generate_streaming(prompt, context, provider_manager):
    """Generate text with streaming output via LiteLLM."""
    messages = build_messages(prompt, context)

    # Resolve which model to use
    agent = context.get("agent", "auto") if context else "auto"
    mode = context.get("mode", "prompt") if context else "prompt"
    model = provider_manager.resolve_model(agent=agent, mode=mode, prompt=prompt)

    if not model:
        IPC.send_error("No LLM provider available. Add at least one API key in settings.")
        IPC.send_chunk("", is_final=True)
        return ""

    # Determine model group for memory
    group = provider_manager.get_model_group(model)

    # Attach conversation memory (skipped for backtick/live modes)
    window_title = context.get("window", "") if context else ""
    memory_msgs = provider_manager.get_memory_history(window_title, group, mode)
    messages = build_messages_with_memory(messages, memory_msgs)

    full_text = ""
    retries = 0          # counts retryable errors (503/overloaded)
    provider_switches = 0 # counts auth/rate-limit fallbacks (unlimited by MAX_RETRIES)
    max_switches = 10     # safety cap to avoid infinite loops

    while retries < MAX_RETRIES and provider_switches < max_switches:
        try:
            for chunk in provider_manager.stream(model, messages):
                full_text += chunk
                IPC.send_chunk(chunk, is_final=False)

            # Clean and finalize
            full_text = clean_response(full_text)
            IPC.send_chunk("", is_final=True)

            # Store interaction in memory
            provider_manager.store_interaction(window_title, prompt, full_text, group, mode)

            return full_text

        except Exception as e:
            error_str = str(e)

            # Auth error → mark model as failed and try fallback (doesn't count as retry)
            if _is_auth_error(error_str):
                fallback = provider_manager.get_fallback_model(model)
                if fallback:
                    IPC.send_error(f"Auth failed for {model.split('/')[0]}, switching to {fallback.split('/')[0]}...")
                    model = fallback
                    group = provider_manager.get_model_group(model)
                    full_text = ""  # reset partial output
                    provider_switches += 1
                    continue
                else:
                    IPC.send_error(f"Invalid API key for {model.split('/')[0]} and no fallback available.")
                    IPC.send_chunk("", is_final=True)
                    return "Error: Invalid API key and no fallback available."

            if '503' in error_str or 'overloaded' in error_str.lower():
                retries += 1
                if retries < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * retries)
                    continue
                IPC.send_error(f"API overloaded. Tried {MAX_RETRIES} times.")
                IPC.send_chunk("", is_final=True)
                return f"Error: API overloaded. Tried {MAX_RETRIES} times."

            if _is_rate_limit_error(error_str):
                # Rate limited / quota exceeded / insufficient balance → try fallback to a different provider
                fallback = provider_manager.get_fallback_model(model)
                if fallback:
                    IPC.send_error(f"Rate limited on {model.split('/')[0]}, switching to {fallback.split('/')[0]}...")
                    model = fallback
                    group = provider_manager.get_model_group(model)
                    full_text = ""
                    provider_switches += 1
                    continue
                
                # Check for specific insufficient balance error
                if "insufficient balance" in error_str.lower():
                    IPC.send_error("API account has insufficient balance. Please add funds or use a different provider.")
                    IPC.send_chunk("", is_final=True)
                    return "Error: Insufficient account balance. Please check your API provider account."
                
                IPC.send_error("API rate limit exceeded on all providers.")
                IPC.send_chunk("", is_final=True)
                return "Error: API rate limit exceeded."

            IPC.send_error(f"Generation error: {error_str}")
            IPC.send_chunk("", is_final=True)
            return f"Error: {error_str}"

    IPC.send_error("Failed after multiple attempts.")
    IPC.send_chunk("", is_final=True)
    return "Error: Failed after multiple attempts."


def generate_non_streaming(prompt, context, provider_manager):
    """Generate text without streaming (fallback)."""
    messages = build_messages(prompt, context)

    agent = context.get("agent", "auto") if context else "auto"
    mode = context.get("mode", "prompt") if context else "prompt"
    model = provider_manager.resolve_model(agent=agent, mode=mode, prompt=prompt)

    if not model:
        return "Error: No LLM provider available."

    group = provider_manager.get_model_group(model)
    window_title = context.get("window", "") if context else ""
    memory_msgs = provider_manager.get_memory_history(window_title, group, mode)
    messages = build_messages_with_memory(messages, memory_msgs)

    retries = 0
    provider_switches = 0
    max_switches = 10

    while retries < MAX_RETRIES and provider_switches < max_switches:
        try:
            text = provider_manager.complete(model, messages)
            if text:
                text = clean_response(text)
                provider_manager.store_interaction(window_title, prompt, text, group, mode)
                return text
            return "Error: No content in response."

        except Exception as e:
            error_str = str(e)

            # Auth error → fallback to next provider (doesn't count as retry)
            if _is_auth_error(error_str):
                fallback = provider_manager.get_fallback_model(model)
                if fallback:
                    model = fallback
                    group = provider_manager.get_model_group(model)
                    provider_switches += 1
                    continue
                return "Error: Invalid API key and no fallback available."

            if '503' in error_str or 'overloaded' in error_str.lower():
                retries += 1
                if retries < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * retries)
                    continue

            if _is_rate_limit_error(error_str):
                fallback = provider_manager.get_fallback_model(model)
                if fallback:
                    model = fallback
                    group = provider_manager.get_model_group(model)
                    provider_switches += 1
                    continue

            return f"Error: {error_str}"

    return "Error: Failed after multiple attempts."


def clean_response(text):
    """Clean up AI response text."""
    if not text:
        return ""

    lines = text.strip().split('\n')
    cleaned = []
    skip_next = False

    for line in lines:
        if line.lower().startswith('subject:'):
            skip_next = True
            continue
        if skip_next and line.strip() == '':
            skip_next = False
            continue
        if not skip_next:
            cleaned.append(line)

    return '\n'.join(cleaned).strip()


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST HANDLER
# ══════════════════════════════════════════════════════════════════════════════

def generate_streaming_with_messages(messages, context, provider_manager):
    """Generate streaming response using pre-built messages (for chat mode).
    Also integrates cross-model memory so chat can see prompt bar interactions."""
    agent = context.get("agent", "auto") if context else "auto"
    mode = context.get("mode", "chat") if context else "chat"
    prompt = ""
    # Extract last user message for model routing
    for msg in reversed(messages):
        if msg.get("role") == "user":
            prompt = msg.get("content", "")
            break

    model = provider_manager.resolve_model(agent=agent, mode=mode, prompt=prompt)

    if not model:
        IPC.send_error("No LLM provider available. Add at least one API key in settings.")
        IPC.send_chunk("", is_final=True)
        return ""

    group = provider_manager.get_model_group(model)
    window_title = context.get("window", "") if context else ""
    memory_msgs = provider_manager.get_memory_history(window_title, group, mode)
    messages = build_messages_with_memory(messages, memory_msgs)

    full_text = ""
    retries = 0
    provider_switches = 0
    max_switches = 10

    while retries < MAX_RETRIES and provider_switches < max_switches:
        try:
            for chunk in provider_manager.stream(model, messages):
                full_text += chunk
                IPC.send_chunk(chunk, is_final=False)

            full_text = clean_response(full_text)
            IPC.send_chunk("", is_final=True)

            # Store in cross-model memory so prompt bar can see chat interactions
            provider_manager.store_interaction(window_title, prompt, full_text, group, mode)

            return full_text

        except Exception as e:
            error_str = str(e)

            if _is_auth_error(error_str):
                fallback = provider_manager.get_fallback_model(model)
                if fallback:
                    model = fallback
                    full_text = ""
                    provider_switches += 1
                    continue
                else:
                    IPC.send_error(f"Invalid API key for {model.split('/')[0]} and no fallback available.")
                    IPC.send_chunk("", is_final=True)
                    return ""

            if '503' in error_str or 'overloaded' in error_str.lower():
                retries += 1
                if retries < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * retries)
                    continue
                IPC.send_error(f"API overloaded. Tried {MAX_RETRIES} times.")
                IPC.send_chunk("", is_final=True)
                return ""

            if _is_rate_limit_error(error_str):
                fallback = provider_manager.get_fallback_model(model)
                if fallback:
                    model = fallback
                    full_text = ""
                    provider_switches += 1
                    continue
                IPC.send_error("API rate limit exceeded on all providers.")
                IPC.send_chunk("", is_final=True)
                return ""

            IPC.send_error(f"Generation error: {error_str}")
            IPC.send_chunk("", is_final=True)
            return ""

    IPC.send_error("Failed after multiple attempts.")
    IPC.send_chunk("", is_final=True)
    return ""


def handle_request(request, provider_manager):
    """Handle incoming request from Electron."""
    cmd = request.get("cmd", "")

    if cmd == "generate":
        prompt = request.get("prompt", "")
        context = request.get("context", {})
        streaming = request.get("streaming", True)
        pre_built_messages = request.get("messages")

        # Chat mode: use pre-built messages (includes full conversation history)
        if pre_built_messages:
            if streaming:
                generate_streaming_with_messages(pre_built_messages, context, provider_manager)
            else:
                # Non-streaming fallback for chat (unlikely path)
                generate_streaming_with_messages(pre_built_messages, context, provider_manager)
            return

        if not prompt:
            IPC.send({"event": "complete", "text": "", "error": "Empty prompt"})
            return

        if streaming:
            generate_streaming(prompt, context, provider_manager)
        else:
            text = generate_non_streaming(prompt, context, provider_manager)
            IPC.send_complete(text)

    elif cmd == "ping":
        IPC.send({"event": "pong"})

    elif cmd == "shutdown":
        IPC.send({"event": "shutdown_ack"})
        return "shutdown"

    elif cmd == "get_agents":
        agents = provider_manager.get_available_agents()
        IPC.send({"event": "agents", "agents": agents})

    elif cmd == "test_provider":
        model = request.get("model", "")
        if model:
            result = provider_manager.test_provider(model)
            IPC.send({"event": "test_result", "model": model, **result})
        else:
            IPC.send_error("test_provider requires a model parameter")

    else:
        IPC.send_error(f"Unknown command: {cmd}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point - persistent service."""
    try:
        provider_manager = ProviderManager()
    except Exception as e:
        IPC.send_error(f"Failed to initialize provider system: {e}")
        IPC.send({"event": "started", "success": False})
        return

    if not provider_manager.has_any_provider():
        IPC.send_error("No API keys configured. Add at least one provider key.")
        # Still start — user may add keys via settings later
        IPC.send({"event": "started", "success": True, "pid": os.getpid(), "providers": 0})
    else:
        agents = provider_manager.get_available_agents()
        IPC.send({"event": "started", "success": True, "pid": os.getpid(), "providers": len(agents) - 1})

    running = True
    while running:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                result = handle_request(request, provider_manager)
                if result == "shutdown":
                    running = False
            except json.JSONDecodeError:
                IPC.send_error(f"Invalid JSON: {line}")

        except Exception as e:
            IPC.send_error(f"stdin error: {e}")
            break

    IPC.send({"event": "stopped"})


if __name__ == "__main__":
    main()
