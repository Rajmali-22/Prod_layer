#!/usr/bin/env python3
"""
ULTRA-HUMAN CODE TYPER - Chain-of-Thought Typing for Coding Mode

Simulates realistic human typing with:
- Skeleton-first approach (main -> helpers -> back to main)
- Semantic navigation (above_main, below_imports, etc.)
- Random typos with corrections
- Variable pauses between sections

Usage:
    python ultra_human_typer.py <code> [sequence_json] [--backspace N]

Args:
    code: The complete code to type
    sequence_json: Optional JSON typing sequence (if not provided, uses fallback)
    --backspace N: Number of backspaces to send before typing
"""

import sys
import os
import re
import time
import random
import json
import pyautogui

# Config
TYPING_SPEED = (0.06, 0.12)
PAUSE_SHORT = (0.2, 0.4)
PAUSE_MEDIUM = (0.5, 0.9)
PAUSE_LONG = (1.0, 1.8)
TYPO_CHANCE = 0.20

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# Global tracker
position_tracker = None


# ============================================================================
# POSITION TRACKER - Semantic Navigation with Cursor Tracking
# ============================================================================

class PositionTracker:
    """Track cursor position and semantic positions in code for intelligent navigation"""
    def __init__(self):
        self.cursor_line = 1
        self.cursor_column = 0

        self.imports_start = None
        self.imports_end = None
        self.main_def_line = None
        self.main_body_start = None
        self.class_def_line = None
        self.class_body_start = None

        self.functions = {}
        self.helpers_start = None
        self.helpers_end = None

    def shift_positions_down(self, from_line, num_lines):
        """Shift all tracked positions down when we insert lines above them."""
        if self.imports_start and from_line <= self.imports_start:
            self.imports_start += num_lines
        if self.imports_end and from_line <= self.imports_end:
            self.imports_end += num_lines

        if self.main_def_line and from_line <= self.main_def_line:
            self.main_def_line += num_lines
        if self.main_body_start and from_line <= self.main_body_start:
            self.main_body_start += num_lines

        if self.class_def_line and from_line <= self.class_def_line:
            self.class_def_line += num_lines
        if self.class_body_start and from_line <= self.class_body_start:
            self.class_body_start += num_lines

        for func_name in self.functions:
            if from_line <= self.functions[func_name]['def_line']:
                self.functions[func_name]['def_line'] += num_lines
            if from_line <= self.functions[func_name]['body_start']:
                self.functions[func_name]['body_start'] += num_lines

        if self.helpers_start and from_line <= self.helpers_start:
            self.helpers_start += num_lines
        if self.helpers_end and from_line <= self.helpers_end:
            self.helpers_end += num_lines

    def move_cursor(self, direction, amount=1):
        """Update cursor position after movement"""
        if direction == 'up':
            self.cursor_line = max(1, self.cursor_line - amount)
        elif direction == 'down':
            self.cursor_line += amount
        elif direction == 'enter':
            self.shift_positions_down(self.cursor_line + 1, 1)
            self.cursor_line += 1
            self.cursor_column = 0
        elif direction == 'home':
            self.cursor_column = 0
        elif direction == 'ctrl_home':
            self.cursor_line = 1
            self.cursor_column = 0

    def typed_line(self, line):
        """Called when a complete line is typed (but not yet Enter pressed)"""
        stripped = line.lstrip()

        if not stripped:
            return

        if stripped.startswith(('import ', 'from ')):
            if self.imports_start is None:
                self.imports_start = self.cursor_line
            self.imports_end = self.cursor_line

        if stripped.startswith('class '):
            self.class_def_line = self.cursor_line
            self.class_body_start = self.cursor_line + 1

        if stripped.startswith('def '):
            func_name = stripped.split('(')[0].replace('def ', '').strip()
            self.functions[func_name] = {
                'def_line': self.cursor_line,
                'body_start': self.cursor_line + 1
            }

            if func_name == 'main':
                self.main_def_line = self.cursor_line
                self.main_body_start = self.cursor_line + 1
            else:
                if self.helpers_start is None:
                    self.helpers_start = self.cursor_line
                self.helpers_end = self.cursor_line

    def after_enter(self):
        """Called after Enter is pressed"""
        self.move_cursor('enter')

    def calculate_navigation(self, target):
        """Calculate navigation to reach target position"""
        current = self.cursor_line
        target_line = None

        if target == 'below_imports':
            if self.imports_end:
                target_line = self.imports_end + 3

        elif target == 'above_main':
            if self.main_def_line:
                target_line = self.main_def_line - 3

        elif target == 'below_main':
            if self.main_body_start:
                target_line = self.main_body_start + 2

        elif target == 'inside_main':
            if self.main_body_start:
                target_line = self.main_body_start + 1

        elif target == 'before_helpers':
            if self.helpers_start:
                target_line = self.helpers_start - 1

        elif target == 'after_helpers':
            if self.helpers_end:
                target_line = self.helpers_end + 1

        elif target == 'inside_class':
            if self.class_body_start:
                target_line = self.class_body_start

        elif target == 'below_class':
            if self.class_def_line:
                target_line = self.class_def_line + 1

        elif target.startswith('below_function_'):
            func_name = target.replace('below_function_', '')
            if func_name in self.functions:
                target_line = self.functions[func_name]['body_start']

        elif target.startswith('above_function_'):
            func_name = target.replace('above_function_', '')
            if func_name in self.functions:
                target_line = self.functions[func_name]['def_line'] - 1

        if target_line is None:
            return None, 0

        distance = target_line - current

        if distance == 0:
            return 'none', 0
        elif distance > 0:
            return 'down', distance
        else:
            return 'up', abs(distance)


# ============================================================================
# KEYBOARD FUNCTIONS - PyAutoGUI
# ============================================================================

def type_char(char):
    pyautogui.write(char, interval=random.uniform(*TYPING_SPEED))

def type_text(text):
    for char in text:
        type_char(char)

def press_enter():
    global position_tracker
    pyautogui.press('enter')
    if position_tracker:
        position_tracker.after_enter()
    time.sleep(0.05)

def press_home():
    global position_tracker
    pyautogui.press('home')
    if position_tracker:
        position_tracker.move_cursor('home')
    time.sleep(0.05)

def press_space():
    pyautogui.press('space')
    time.sleep(0.05)

def press_up(n=1):
    global position_tracker
    for _ in range(n):
        pyautogui.press('up')
        if position_tracker:
            position_tracker.move_cursor('up', 1)
        time.sleep(0.05)

def press_down(n=1):
    global position_tracker
    for _ in range(n):
        pyautogui.press('down')
        if position_tracker:
            position_tracker.move_cursor('down', 1)
        time.sleep(0.05)

def press_backspace(n=1):
    for _ in range(n):
        pyautogui.press('backspace')
        time.sleep(0.02)

def ctrl_home():
    global position_tracker
    pyautogui.hotkey('ctrl', 'home')
    if position_tracker:
        position_tracker.move_cursor('ctrl_home')
    time.sleep(0.05)

def ctrl_end():
    pyautogui.hotkey('ctrl', 'end')
    time.sleep(0.05)

def delete_line():
    pyautogui.press('home')
    pyautogui.hotkey('shift', 'end')
    pyautogui.press('backspace')
    time.sleep(0.05)


def execute_navigation(nav):
    """Execute navigation command - supports both raw and semantic navigation"""
    global position_tracker

    if nav == "none":
        return

    semantic_commands = [
        'below_imports', 'below_main', 'above_main', 'inside_main',
        'after_helpers', 'before_helpers', 'inside_class', 'below_class'
    ]

    is_semantic = any(nav.startswith(cmd) for cmd in semantic_commands) or \
                  nav.startswith('below_function_') or nav.startswith('above_function_')

    if is_semantic and position_tracker:
        direction, distance = position_tracker.calculate_navigation(nav)

        if direction == 'none':
            return
        elif direction is None:
            ctrl_home()
            press_home()
            return

        press_home()

        if direction == 'up':
            press_up(distance)
        else:
            press_down(distance)

        press_home()
        return

    parts = nav.split('_')

    if parts[0] == "ctrl" and parts[1] == "home":
        ctrl_home()
        if len(parts) > 2 and parts[2] == "home":
            press_home()

    elif parts[0] == "ctrl" and parts[1] == "end":
        ctrl_end()
        if len(parts) > 2 and parts[2] == "home":
            press_home()
        if len(parts) > 3 and parts[3] == "delete" and parts[4] == "line":
            delete_line()

    elif parts[0] == "up":
        press_home()
        n = int(parts[1])
        press_up(n)
        press_home()

    elif parts[0] == "down":
        press_home()
        n = int(parts[1])
        press_down(n)
        press_home()


def pause(p_type):
    pauses = {'short': PAUSE_SHORT, 'medium': PAUSE_MEDIUM, 'long': PAUSE_LONG}
    duration = random.uniform(*pauses.get(p_type, PAUSE_MEDIUM))
    time.sleep(duration)


def maybe_typo(text):
    """Randomly introduce typos for realism"""
    if random.random() > TYPO_CHANCE or len(text) < 5:
        type_text(text)
        return

    if random.random() < 0.7:
        type_text(text[:-2])
        type_char(random.choice('abcdefgh'))
        time.sleep(0.06)
        pyautogui.press('backspace')
        time.sleep(0.06)
        type_text(text[-2:])
    else:
        type_text(text)


# ============================================================================
# TYPING LOGIC
# ============================================================================

def type_code_step(step, is_first_step):
    """Type a single step of the coding sequence"""
    global position_tracker

    lines = step['lines']
    navigation = step.get('nav', 'none')
    pause_type = step.get('pause', 'medium')

    # Thinking pause
    pause(pause_type)

    # Execute navigation
    if navigation != "none":
        execute_navigation(navigation)

    # Line separation between steps (if no navigation happened)
    if not is_first_step and navigation == "none":
        press_enter()
        press_home()

    first_line = True

    for line in lines:
        # Handle blank lines
        if not line.strip():
            if not first_line:
                press_enter()
                press_home()
            first_line = False
            continue

        # New line if not first
        if not first_line:
            press_enter()
            press_home()

        first_line = False

        # Count leading spaces for indentation
        num_spaces = len(line) - len(line.lstrip())
        stripped = line.lstrip()

        # Type indentation
        for _ in range(num_spaces):
            press_space()

        # Type content with possible typos
        maybe_typo(stripped)

        # Update position tracker
        if position_tracker:
            position_tracker.typed_line(line)

    time.sleep(0.15)


def execute_typing_sequence(sequence):
    """Execute the full typing sequence"""
    for idx, step in enumerate(sequence['steps']):
        type_code_step(step, is_first_step=(idx == 0))


def create_fallback_sequence(code):
    """Fallback sequence if no sequence provided - simple top-to-bottom"""
    lines = code.split('\n')
    imports = []
    other_lines = []

    for line in lines:
        if line.strip().startswith(('import ', 'from ')):
            imports.append(line)
        elif line.strip():
            other_lines.append(line)

    steps = []

    if imports:
        steps.append({
            "num": 1,
            "thought": "Import required modules",
            "lines": imports + [""],
            "nav": "ctrl_home_home",
            "pause": "short"
        })

    if other_lines:
        steps.append({
            "num": len(steps) + 1,
            "thought": "Write the main code",
            "lines": other_lines,
            "nav": "none",
            "pause": "medium"
        })

    return {"steps": steps}


# ============================================================================
# MAIN
# ============================================================================

def main():
    global position_tracker

    if len(sys.argv) < 2:
        print("Usage: python ultra_human_typer.py <code> [sequence_json] [--backspace N]")
        sys.exit(1)

    # Parse arguments
    code = sys.argv[1]

    # Unescape the code (same as keyboard_inject.py)
    code = code.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t').replace('\\\\', '\\')

    sequence_json = None
    backspace_count = 0

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == '--backspace' and i + 1 < len(sys.argv):
            backspace_count = int(sys.argv[i + 1])
            i += 2
        else:
            sequence_json = sys.argv[i]
            i += 1

    # Initialize position tracker
    position_tracker = PositionTracker()

    # Small delay for focus
    time.sleep(0.1)

    # Send backspaces first if needed
    if backspace_count > 0:
        press_backspace(backspace_count)
        time.sleep(0.1)

    # Parse or create sequence
    if sequence_json:
        try:
            sequence = json.loads(sequence_json)
        except json.JSONDecodeError:
            sequence = create_fallback_sequence(code)
    else:
        sequence = create_fallback_sequence(code)

    # Execute typing
    execute_typing_sequence(sequence)

    # Output success
    print(json.dumps({"success": True}))


if __name__ == "__main__":
    try:
        main()
    except pyautogui.FailSafeException:
        print(json.dumps({"success": False, "error": "PyAutoGUI failsafe triggered"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)
