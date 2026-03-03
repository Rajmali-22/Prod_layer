#!/usr/bin/env python3
"""
Keyboard injection module using pynput - pure Python, no Rust.
Features:
- Direct (fast) typing mode - default
- Humanize typing mode - variable delays, occasional typos, natural pauses
- Pause/Continue with '.' key during injection
"""

import sys
import time
import random
import threading
from pynput.keyboard import Controller, Key

keyboard = Controller()

# Pause state
is_paused = False
pause_lock = threading.Lock()

# Try to import keyboard library for pause detection
try:
    import keyboard as kb
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False


def toggle_pause():
    """Toggle pause state."""
    global is_paused
    with pause_lock:
        is_paused = not is_paused


def check_pause():
    """Check if paused and wait until resumed."""
    while True:
        with pause_lock:
            if not is_paused:
                break
        time.sleep(0.05)  # Check every 50ms


def setup_pause_hotkey():
    """Setup 'Ctrl+.' as pause/continue toggle."""
    if HAS_KEYBOARD:
        kb.add_hotkey('ctrl+.', toggle_pause, suppress=True)


def cleanup_pause_hotkey():
    """Remove pause hotkey."""
    if HAS_KEYBOARD:
        try:
            kb.remove_hotkey('ctrl+.')
        except:
            pass

# Mapping for special characters that need shift
SHIFT_CHARS = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
    '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\',
    ':': ';', '"': "'", '<': ',', '>': '.', '?': '/',
    '~': '`'
}

# Special keys mapping
SPECIAL_KEYS = {
    '\n': Key.enter,
    '\r': Key.enter,
    '\t': Key.tab,
}

# Common typo patterns (adjacent keys on QWERTY)
TYPO_MAP = {
    'a': ['s', 'q', 'w'],
    'b': ['v', 'n', 'g'],
    'c': ['x', 'v', 'd'],
    'd': ['s', 'f', 'e'],
    'e': ['w', 'r', 'd'],
    'f': ['d', 'g', 'r'],
    'g': ['f', 'h', 't'],
    'h': ['g', 'j', 'y'],
    'i': ['u', 'o', 'k'],
    'j': ['h', 'k', 'u'],
    'k': ['j', 'l', 'i'],
    'l': ['k', 'o', 'p'],
    'm': ['n', 'j', 'k'],
    'n': ['b', 'm', 'h'],
    'o': ['i', 'p', 'l'],
    'p': ['o', 'l'],
    'q': ['w', 'a'],
    'r': ['e', 't', 'f'],
    's': ['a', 'd', 'w'],
    't': ['r', 'y', 'g'],
    'u': ['y', 'i', 'j'],
    'v': ['c', 'b', 'f'],
    'w': ['q', 'e', 's'],
    'x': ['z', 'c', 's'],
    'y': ['t', 'u', 'h'],
    'z': ['x', 'a'],
}


def unescape_text(text):
    """Convert escape sequences to actual characters."""
    return (text
            .replace('\\n', '\n')
            .replace('\\r', '\r')
            .replace('\\t', '    ')
            .replace('\t', '    '))


def get_typing_delay(humanize=False):
    """Get typing delay between characters."""
    if not humanize:
        return 0.001  # Fast direct typing (1ms)

    # Human typing speed: 40-80 WPM = variable delays
    base_delay = random.uniform(0.03, 0.12)  # 30-120ms

    # Occasional longer pauses (5% chance - thinking/hesitation)
    if random.random() < 0.05:
        base_delay += random.uniform(0.2, 0.5)

    return base_delay


def should_make_typo(humanize=False):
    """Decide if we should make a typo (2% chance when humanize is on)."""
    if not humanize:
        return False
    return random.random() < 0.02  # 2% typo rate


def get_typo_char(char):
    """Get a realistic typo for the given character."""
    char_lower = char.lower()

    if char_lower in TYPO_MAP and TYPO_MAP[char_lower]:
        typo = random.choice(TYPO_MAP[char_lower])
        return typo.upper() if char.isupper() else typo

    return char


def send_char(char):
    """Send a single character using keyboard simulation."""
    # Handle special keys
    if char in SPECIAL_KEYS:
        keyboard.press(SPECIAL_KEYS[char])
        keyboard.release(SPECIAL_KEYS[char])
        return

    # Handle shifted characters
    if char in SHIFT_CHARS:
        keyboard.press(Key.shift)
        keyboard.press(SHIFT_CHARS[char])
        keyboard.release(SHIFT_CHARS[char])
        keyboard.release(Key.shift)
        return

    # Handle uppercase letters
    if char.isupper():
        keyboard.press(Key.shift)
        keyboard.press(char.lower())
        keyboard.release(char.lower())
        keyboard.release(Key.shift)
        return

    # Regular character
    try:
        keyboard.press(char)
        keyboard.release(char)
    except Exception:
        keyboard.type(char)


def send_backspace():
    """Send a single backspace."""
    keyboard.press(Key.backspace)
    keyboard.release(Key.backspace)


def send_text(text, humanize=False):
    """Send text character by character."""
    time.sleep(0.05)

    i = 0
    while i < len(text):
        # Check for pause before each character
        check_pause()

        char = text[i]

        # Humanize: occasional typos with quick correction
        if humanize and should_make_typo() and char.isalpha():
            typo_char = get_typo_char(char)

            if typo_char != char:
                # Type wrong character
                send_char(typo_char)
                time.sleep(get_typing_delay(humanize))

                # Brief pause before correction
                time.sleep(random.uniform(0.1, 0.25))
                send_backspace()
                time.sleep(0.02)

                # Type correct character
                send_char(char)
        else:
            # Normal typing
            send_char(char)

        # Delay between characters
        time.sleep(get_typing_delay(humanize))

        # Humanize: longer pause after punctuation
        if humanize and char in '.!?,;:':
            time.sleep(random.uniform(0.1, 0.3))

        i += 1


def send_backspaces(count, humanize=False):
    """Send backspace key presses to delete text."""
    if count <= 0:
        return

    time.sleep(0.05)

    for _ in range(count):
        send_backspace()

        if humanize:
            time.sleep(random.uniform(0.02, 0.05))
        else:
            time.sleep(0.002)

    time.sleep(0.05)


def main():
    if len(sys.argv) < 2:
        print("Usage: python keyboard_inject.py <text> [--backspace N] [--humanize]", file=sys.stderr)
        sys.exit(1)

    # Parse arguments
    text = sys.argv[1]
    backspace_count = 0
    humanize = False  # Default: direct (fast) typing

    # Parse flags
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--backspace' and i + 1 < len(sys.argv):
            try:
                backspace_count = int(sys.argv[i + 1])
            except ValueError:
                print("Invalid backspace count", file=sys.stderr)
            i += 2
        elif sys.argv[i] == '--humanize':
            humanize = True
            i += 1
        else:
            i += 1

    # Unescape text
    text = unescape_text(text)

    # Setup pause hotkey ('.' to pause/continue)
    setup_pause_hotkey()

    try:
        # Send backspaces first
        if backspace_count > 0:
            send_backspaces(backspace_count, humanize)

        # Split by newlines and send
        lines = text.split('\n')

        for idx, line in enumerate(lines):
            # Check pause before each line
            check_pause()

            if line:
                send_text(line, humanize)

            # Press Enter after each line except last; then Home so cursor is at start of line (code mode)
            if idx < len(lines) - 1:
                check_pause()
                keyboard.press(Key.enter)
                keyboard.release(Key.enter)
                time.sleep(0.02 if humanize else 0.01)
                keyboard.press(Key.home)
                keyboard.release(Key.home)
                time.sleep(0.01)
    finally:
        # Cleanup pause hotkey
        cleanup_pause_hotkey()


if __name__ == '__main__':
    main()
