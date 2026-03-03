#!/usr/bin/env python3
"""
HUMAN-LIKE CODE TYPER - Improved Version
Mixed approach: main -> helpers above -> back to main (realistic human flow)
"""

import sys
import os
import re
import time
import random
import json
from datetime import datetime
import litellm
import pyautogui

# Config
TYPING_SPEED = (0.08, 0.15)
PAUSE_SHORT = (0.3, 0.6)
PAUSE_MEDIUM = (0.7, 1.2)
PAUSE_LONG = (1.5, 2.5)
TYPO_CHANCE = 0.25
LOG_FILE = os.path.join("data", "typing_debug.log")

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08

logger = None
position_tracker = None

# ============================================================================
# POSITION TRACKER - Semantic Navigation with Cursor Tracking
# ============================================================================

class PositionTracker:
    """Track cursor position and semantic positions in code for intelligent navigation"""
    def __init__(self):
        # Cursor tracking
        self.cursor_line = 1
        self.cursor_column = 0
        
        # Semantic positions (line numbers)
        self.imports_start = None
        self.imports_end = None
        self.main_def_line = None      # Line where "def main():" is
        self.main_body_start = None    # Line after "def main():" where body starts
        self.class_def_line = None
        self.class_body_start = None
        
        # Track all functions: {name: {'def_line': N, 'body_start': N}}
        self.functions = {}
        
        # Track helpers section
        self.helpers_start = None
        self.helpers_end = None
        
    def shift_positions_down(self, from_line, num_lines):
        """
        Shift all tracked positions down when we insert lines above them.
        This is called when we press Enter - if we're above a tracked position,
        everything below shifts down.
        """
        # Shift imports
        if self.imports_start and from_line <= self.imports_start:
            self.imports_start += num_lines
        if self.imports_end and from_line <= self.imports_end:
            self.imports_end += num_lines
        
        # Shift main
        if self.main_def_line and from_line <= self.main_def_line:
            self.main_def_line += num_lines
        if self.main_body_start and from_line <= self.main_body_start:
            self.main_body_start += num_lines
        
        # Shift class
        if self.class_def_line and from_line <= self.class_def_line:
            self.class_def_line += num_lines
        if self.class_body_start and from_line <= self.class_body_start:
            self.class_body_start += num_lines
        
        # Shift all functions
        for func_name in self.functions:
            if from_line <= self.functions[func_name]['def_line']:
                self.functions[func_name]['def_line'] += num_lines
            if from_line <= self.functions[func_name]['body_start']:
                self.functions[func_name]['body_start'] += num_lines
        
        # Shift helpers
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
            # CRITICAL: When we press enter, we're inserting a new line
            # Everything BELOW current cursor needs to shift down
            self.shift_positions_down(self.cursor_line + 1, 1)
            self.cursor_line += 1
            self.cursor_column = 0
        elif direction == 'home':
            self.cursor_column = 0
        elif direction == 'ctrl_home':
            self.cursor_line = 1
            self.cursor_column = 0
        elif direction == 'ctrl_end':
            # We don't know the end, but we track current position
            pass
    
    def typed_line(self, line):
        """Called when a complete line is typed (but not yet Enter pressed)"""
        stripped = line.lstrip()
        
        if not stripped:
            return
        
        # Track imports
        if stripped.startswith(('import ', 'from ')):
            if self.imports_start is None:
                self.imports_start = self.cursor_line
            self.imports_end = self.cursor_line
        
        # Track class definitions
        if stripped.startswith('class '):
            class_name = stripped.split('(')[0].split(':')[0].replace('class ', '').strip()
            self.class_def_line = self.cursor_line
            self.class_body_start = self.cursor_line + 1
        
        # Track function definitions
        if stripped.startswith('def '):
            func_name = stripped.split('(')[0].replace('def ', '').strip()
            self.functions[func_name] = {
                'def_line': self.cursor_line,
                'body_start': self.cursor_line + 1
            }
            
            # Track main specifically
            if func_name == 'main':
                self.main_def_line = self.cursor_line
                self.main_body_start = self.cursor_line + 1
            else:
                # Track helpers
                if self.helpers_start is None:
                    self.helpers_start = self.cursor_line
                self.helpers_end = self.cursor_line
    
    def after_enter(self):
        """Called after Enter is pressed"""
        self.move_cursor('enter')
    
    def calculate_navigation(self, target):
        """
        Calculate navigation to reach target position
        Returns: (nav_type, amount) or None if cannot navigate
        
        IMPORTANT: Always go to column 0 (home) first before vertical movement
        """
        current = self.cursor_line
        target_line = None
        
        # Decode semantic targets
        if target == 'below_imports':
            if self.imports_end:
                target_line = self.imports_end + 3
        
        elif target == 'above_main':
            if self.main_def_line:
                target_line = self.main_def_line - 3
        
        elif target == 'below_main':
            # Below means AFTER the "def main():" line, in the body
            if self.main_body_start:
                target_line = self.main_body_start + 2
        
        elif target == 'inside_main':
            # Same as below_main - inside the function body
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
        
        # If we couldn't find target, return None
        if target_line is None:
            return None, 0
        
        # Calculate distance
        distance = target_line - current
        
        if distance == 0:
            return 'none', 0
        elif distance > 0:
            return 'down', distance
        else:
            return 'up', abs(distance)
    
    def get_status(self):
        """Get current tracking status for logging"""
        status = f"Cursor: L{self.cursor_line}"
        if self.imports_end:
            status += f" | Imports: L{self.imports_start}-{self.imports_end}"
        if self.main_def_line:
            status += f" | Main: L{self.main_def_line} (body@L{self.main_body_start})"
        if self.functions:
            funcs = [f"{n}@L{d['def_line']}" for n, d in self.functions.items() if n != 'main']
            if funcs:
                status += f" | Helpers: {', '.join(funcs)}"
        return status

# ============================================================================
# LOGGER
# ============================================================================

class KeystrokeLogger:
    def __init__(self, filename):
        self.filename = filename
        self.current_step = 0
        self.current_line_num = 1
        self.current_column = 0
        
        with open(filename, 'w') as f:
            f.write("="*80 + "\n")
            f.write(f"LOG - {datetime.now()}\n")
            f.write("="*80 + "\n\n")
    
    def log(self, key, key_type, context=""):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        position = f"L{self.current_line_num}:C{self.current_column}"
        
        with open(self.filename, 'a') as f:
            f.write(f"[{timestamp}] Step {self.current_step} | {position} | {key_type:12s} | {repr(key):20s} | {context}\n")
        
        if key_type == 'enter':
            self.current_line_num += 1
            self.current_column = 0
        elif key_type in ('char', 'space'):
            self.current_column += 1
    
    def set_step(self, step_num, thought):
        self.current_step = step_num
        with open(self.filename, 'a') as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"STEP {step_num}: {thought}\n")
            f.write("="*80 + "\n")
    
    def add_note(self, note):
        with open(self.filename, 'a') as f:
            f.write(f"\n>>> {note}\n")
    
    def finalize(self):
        with open(self.filename, 'a') as f:
            f.write("\n" + "="*80 + "\nCOMPLETE\n" + "="*80 + "\n")

# ============================================================================
# MISTRAL
# ============================================================================

def _find_available_model():
    """Find the best available model for code generation via litellm."""
    # Prefer powerful models for code gen
    model_candidates = [
        ("GROQ_API_KEY",      "groq/llama-3.3-70b-versatile"),
        ("DEEPSEEK_API_KEY",  "deepseek/deepseek-chat"),
        ("OPENAI_API_KEY",    "openai/gpt-4o"),
        ("ANTHROPIC_API_KEY", "anthropic/claude-sonnet-4-20250514"),
        ("MISTRAL_API_KEY",   "mistral/mistral-small-latest"),
        ("GEMINI_API_KEY",    "gemini/gemini-2.0-flash"),
        ("OPENAI_API_KEY",    "openai/gpt-4o-mini"),
    ]
    seen = set()
    for env_var, model in model_candidates:
        key = os.environ.get(env_var, "")
        if key and "your-" not in key and model not in seen:
            return model
        seen.add(model)
    return None

def init_llm():
    model = _find_available_model()
    if not model:
        print("[ERROR] No LLM provider API key found!")
        print("[HINT] Set at least one: MISTRAL_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, etc.")
        sys.exit(1)
    print(f"[OK] Using model: {model}")
    return model

def generate_final_code(model, problem, presignature=None):
    """Generate the final code solution"""
    if presignature:
        prompt = f"""Complete this function with clean, working code:

{presignature}

Problem: {problem}

STRICT RULES:
1. NO comments anywhere
2. NO docstrings
3. Helper functions can be inside the class if needed
4. Only working code
5. Proper indentation

Output ONLY the complete code without any markdown formatting."""
    else:
        prompt = f"""Write clean Python code to solve: {problem}

STRICT RULES:
1. NO comments anywhere
2. NO docstrings
3. Simple, working code only
4. Proper indentation

Output ONLY the code without any markdown formatting."""

    print("[LLM] Generating final code solution...")

    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )

    code = response.choices[0].message.content.strip()
    
    # Clean up markdown if present
    code = re.sub(r'```python\n?', '', code)
    code = re.sub(r'```\n?', '', code)
    
    # Remove comments and docstrings
    lines = []
    in_docstring = False
    for line in code.split('\n'):
        # Handle docstrings
        if '"""' in line or "'''" in line:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        
        # Remove inline comments
        if '#' in line:
            line = line.split('#')[0].rstrip()
        
        if line.strip():
            lines.append(line)
    
    code = '\n'.join(lines)
    
    print("[OK] Final code generated")
    return code

def save_code_analysis(code, filename="code_analysis.txt"):
    """Save detailed analysis of code structure for research"""
    with open(filename, 'w') as f:
        f.write("="*80 + "\n")
        f.write("CODE STRUCTURE ANALYSIS\n")
        f.write("="*80 + "\n\n")
        
        f.write("ORIGINAL CODE:\n")
        f.write("-"*80 + "\n")
        f.write(code)
        f.write("\n" + "-"*80 + "\n\n")
        
        f.write("LINE-BY-LINE BREAKDOWN:\n")
        f.write("-"*80 + "\n")
        
        lines = code.split('\n')
        for idx, line in enumerate(lines, 1):
            # Count indentation
            spaces = len(line) - len(line.lstrip())
            indent_level = spaces // 4
            stripped = line.lstrip()
            
            # Detect line type
            if not line.strip():
                line_type = "BLANK"
            elif stripped.startswith(('import ', 'from ')):
                line_type = "IMPORT"
            elif stripped.startswith('def '):
                line_type = "FUNCTION_DEF"
            elif stripped.startswith('class '):
                line_type = "CLASS_DEF"
            elif stripped.startswith('return '):
                line_type = "RETURN"
            elif stripped.startswith(('if ', 'elif ', 'else:')):
                line_type = "CONDITIONAL"
            elif stripped.startswith(('for ', 'while ')):
                line_type = "LOOP"
            else:
                line_type = "CODE"
            
            f.write(f"Line {idx:3d} | Spaces: {spaces:2d} | Indent: {indent_level} | Type: {line_type:15s} | {repr(line)}\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write("STATISTICS:\n")
        f.write("-"*80 + "\n")
        f.write(f"Total lines: {len(lines)}\n")
        f.write(f"Non-empty lines: {len([l for l in lines if l.strip()])}\n")
        f.write(f"Blank lines: {len([l for l in lines if not l.strip()])}\n")
        f.write(f"Import lines: {len([l for l in lines if l.lstrip().startswith(('import ', 'from '))])}\n")
        f.write(f"Function definitions: {len([l for l in lines if l.lstrip().startswith('def ')])}\n")
        f.write(f"Max indentation: {max([len(l) - len(l.lstrip()) for l in lines if l.strip()], default=0)} spaces\n")
        
        # Semantic positions
        f.write("\n" + "-"*80 + "\n")
        f.write("SEMANTIC POSITIONS (for navigation):\n")
        f.write("-"*80 + "\n")
        
        import_lines = [i+1 for i, l in enumerate(lines) if l.lstrip().startswith(('import ', 'from '))]
        if import_lines:
            f.write(f"Imports: lines {import_lines[0]}-{import_lines[-1]}\n")
            f.write(f"  -> 'below_imports' navigates to line {import_lines[-1] + 1}\n")
        
        func_lines = {}
        for i, l in enumerate(lines):
            if l.lstrip().startswith('def '):
                func_name = l.lstrip().split('(')[0].replace('def ', '').strip()
                func_lines[func_name] = i + 1
        
        if func_lines:
            f.write(f"\nFunctions found:\n")
            for fname, lnum in func_lines.items():
                f.write(f"  {fname}: line {lnum}\n")
                f.write(f"    -> 'above_function_{fname}' navigates to line {lnum - 1}\n")
                f.write(f"    -> 'below_function_{fname}' navigates to line {lnum + 1}\n")
        
        if 'main' in func_lines:
            f.write(f"\nMain function: line {func_lines['main']}\n")
            f.write(f"  -> 'above_main' navigates to line {func_lines['main'] - 1}\n")
            f.write(f"  -> 'inside_main' navigates to line {func_lines['main'] + 1}\n")
        
        class_lines = [i+1 for i, l in enumerate(lines) if l.lstrip().startswith('class ')]
        if class_lines:
            f.write(f"\nClass definition: line {class_lines[0]}\n")
            f.write(f"  -> 'inside_class' navigates to line {class_lines[0] + 1}\n")
    
    print(f"[SAVED] Code analysis: {filename}")

def generate_human_sequence(model, final_code, presignature=None):
    """LLM generates human-realistic typing sequence with chain of thought"""

    mode = "LeetCode mode - cursor inside function body" if presignature else "Standalone mode - empty file"

    prompt = f"""You are a coding sequence generator. Generate a realistic human typing sequence for this code:

TARGET CODE:
```python
{final_code}
```

MODE: {mode}

HUMAN CODING PATTERN (how real programmers work):
1. Write imports FIRST (always at the top)
2. Write main function SKELETON with 'pass' placeholder
3. Realize helpers are needed
4. Navigate UP to top (after imports) to write helpers
5. Navigate DOWN back to main function
6. Delete 'pass' and implement main using the helpers
7. May go up/down multiple times for complex code

NAVIGATION COMMANDS:
Basic navigation:
- "none" = no navigation
- "ctrl_home_home" = jump to file start, then home key ONLY FOR IMPORTS AND LIB
- "ctrl_end_home" = jump to file end, then home key
- "ctrl_end_home_delete_line" = jump to end, home, delete current line
- "up_N_home" = move up N lines, then home (e.g., "up_3_home")
- "down_N_home" = move down N lines, then home (e.g., "down_5_home")

Semantic navigation (intelligent position-aware):
- "below_imports" = navigate to line after last import ONLY FOR DEF and FUNC NEW FUNCTION DECLARING
- "above_main" = navigate to line before main function ONLY FOR DEF and FUNC NEW FUNCTION DECLARING
- "below_main" = navigate to line after main function definition ONLY FOR USAGE and FUNC CALLING USAGE WILL BE GIVEN HERE, FUNCTION CALLING
- "inside_main" = navigate inside main function (after def line)
- "before_helpers" = navigate to line before first helper function
- "after_helpers" = navigate to line after last helper function
- "inside_class" = navigate inside class definition
- "below_class" = navigate to line after class definition
- "below_function_NAME" = navigate below a specific function (e.g., "below_function_helper")
- "above_function_NAME" = navigate above a specific function (e.g., "above_function_calculate")

WHEN TO USE SEMANTIC NAVIGATION:
Use semantic navigation for complex LeetCode problems where you need to:
- Add multiple helper functions in organized sections
- Work with class-based solutions (LeetCode style)
- Build helpers incrementally before implementing main logic
- Navigate between different logical sections of code

Example for medium/hard problems:
Step 1: Write class definition and main method skeleton
Step 2: Navigate "inside_class" to add first helper
Step 3: Navigate "below_function_helper1" to add second helper
Step 4: Navigate "inside_main" to implement using helpers

PAUSE TYPES:
- "short" = brief pause (thinking)
- "medium" = normal pause (planning next line)
- "long" = longer pause (planning next section)

INDENTATION RULES:
- Count EXACT spaces for each line
- Python uses 4 spaces per indent level
- Empty line = ""

You MUST output valid JSON in this EXACT format:

{{
  "steps": [
    {{
      "num": 1,
      "thought": "Start with imports",
      "lines": ["import sys", "import math", ""],
      "nav": "ctrl_home_home",
      "pause": "short"
    }},
    {{
      "num": 2,
      "thought": "Write main function skeleton",
      "lines": ["def main():", "    pass"],
      "nav": "down_10_home",
      "pause": "medium"
    }},
    {{
      "num": 3,
      "thought": "Need helper function - add it after imports",
      "lines": ["def helper(x):", "    return x * 2", ""],
      "nav": "below_imports",
      "pause": "long"
    }},
    {{
      "num": 4,
      "thought": "Go inside main function body to implement USAGE",
      "lines": ["    result = helper(5)", "    print(result)"],
      "nav": "below_main",
      "pause": "short"
    }}
  ]
}}

CRITICAL NAVIGATION RULES:
1. "below_main" = navigate to INSIDE main function (the line after "def main():" where body starts)
   - Use this when you want to write code INSIDE the main function
   - The cursor will be positioned to type the function body
   - If there's a "pass" placeholder, you may need to delete it first
2. "above_main" = navigate to the line BEFORE "def main():"
   - Use this to add code before the main function definition
3. "below_imports" = navigate to line after last import statement
   - Use this to start writing functions after imports
4. System ALWAYS presses HOME before vertical navigation for accuracy
5. Prefer semantic navigation (below_main, below_imports) over raw movements (down_5_home)

IMPORTANT RULES:
1. Output ONLY valid JSON, nothing else
2. Each line in "lines" must have EXACT indentation (count spaces carefully)
3. Blank lines are represented as ""
4. The sequence must produce the exact target code
5. Use realistic human flow: main skeleton -> helpers -> back to main
6. Always include "home" after navigation movements

Now generate the JSON sequence for the target code above. Output ONLY the JSON:"""
    
    print("[LLM] Generating human typing sequence (chain of thought)...")
    
    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        result = response.choices[0].message.content.strip()
        
        # Save raw response for debugging
        with open(os.path.join('data', 'llm_response.txt'), 'w') as f:
            f.write(result)
        print("[SAVED] Raw LLM response: data/llm_response.txt")
        
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(0)
            sequence = json.loads(json_str)
            
            # Validate structure
            if 'steps' in sequence and len(sequence['steps']) > 0:
                # Save the JSON sequence for analysis
                with open(os.path.join('data', 'typing_sequence.json'), 'w') as f:
                    json.dump(sequence, f, indent=2)
                print(f"[SAVED] Typing sequence: data/typing_sequence.json")
                
                print(f"[OK] Generated sequence with {len(sequence['steps'])} steps")
                
                # Print sequence for debugging
                for step in sequence['steps']:
                    print(f"  Step {step['num']}: {step['thought']}")
                
                return sequence
            else:
                print("[WARNING] JSON missing 'steps' or empty")
        else:
            print("[WARNING] No JSON found in response")
            
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON parsing failed: {e}")
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
    
    print("[FALLBACK] Using simple fallback sequence")
    return create_fallback_sequence(final_code)

def create_fallback_sequence(code):
    """Fallback sequence if LLM fails - simple top-to-bottom"""
    print("[INFO] Creating fallback typing sequence")
    
    lines = code.split('\n')
    imports = []
    other_lines = []
    
    for line in lines:
        if line.strip().startswith(('import ', 'from ')):
            imports.append(line)
        elif line.strip():
            other_lines.append(line)
    
    steps = []
    
    # Step 1: Imports
    if imports:
        steps.append({
            "num": 1,
            "thought": "Import required modules",
            "lines": imports + [""],
            "nav": "ctrl_home_home",
            "pause": "short"
        })
    
    # Step 2: Rest of code
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
# KEYBOARD - PyAutoGUI
# ============================================================================

def type_char(char):
    pyautogui.write(char, interval=random.uniform(*TYPING_SPEED))
    logger.log(char, 'char' if char != ' ' else 'space')

def type_text(text):
    for char in text:
        type_char(char)

def press_enter():
    global position_tracker
    pyautogui.press('enter')
    logger.log('enter', 'enter')
    if position_tracker:
        position_tracker.after_enter()
    time.sleep(0.08)

def press_home():
    global position_tracker
    pyautogui.press('home')
    logger.log('home', 'home')
    if position_tracker:
        position_tracker.move_cursor('home')
    time.sleep(0.08)

def press_space():
    pyautogui.press('space')
    logger.log(' ', 'space')
    time.sleep(0.08)

def press_up(n=1):
    global position_tracker
    for _ in range(n):
        pyautogui.press('up')
        logger.log('up', 'arrow_up')
        if position_tracker:
            position_tracker.move_cursor('up', 1)
        time.sleep(0.08)

def press_down(n=1):
    global position_tracker
    for _ in range(n):
        pyautogui.press('down')
        logger.log('down', 'arrow_down')
        if position_tracker:
            position_tracker.move_cursor('down', 1)
        time.sleep(0.08)

def ctrl_home():
    global position_tracker
    pyautogui.hotkey('ctrl', 'home')
    logger.log('ctrl+home', 'ctrl_home')
    if position_tracker:
        position_tracker.move_cursor('ctrl_home')
    time.sleep(0.08)

def ctrl_end():
    global position_tracker
    pyautogui.hotkey('ctrl', 'end')
    logger.log('ctrl+end', 'ctrl_end')
    if position_tracker:
        position_tracker.move_cursor('ctrl_end')
    time.sleep(0.08)

def delete_line():
    logger.add_note("Deleting line")
    pyautogui.press('home')
    pyautogui.hotkey('shift', 'end')
    pyautogui.press('backspace')
    logger.log('delete', 'delete_line')
    time.sleep(0.08)

def delete_current_content():
    """Delete current line content (useful for removing 'pass' placeholders)"""
    logger.add_note("Deleting current line content")
    pyautogui.press('home')
    pyautogui.hotkey('shift', 'end')
    pyautogui.press('delete')
    logger.log('delete_content', 'delete_content')
    time.sleep(0.08)

def execute_navigation(nav):
    """
    Execute navigation command - supports both raw and semantic navigation
    CRITICAL: Always press HOME before any up/down movement for accuracy
    """
    global position_tracker
    
    if nav == "none":
        return
    
    logger.add_note(f"Navigation requested: {nav}")
    
    # Check if it's a semantic navigation command
    semantic_commands = [
        'below_imports', 'below_main', 'above_main', 'inside_main',
        'after_helpers', 'before_helpers', 'inside_class', 'below_class'
    ]
    
    is_semantic = any(nav.startswith(cmd) for cmd in semantic_commands) or \
                  nav.startswith('below_function_') or nav.startswith('above_function_')
    
    if is_semantic and position_tracker:
        # Calculate semantic navigation
        direction, distance = position_tracker.calculate_navigation(nav)
        
        if direction == 'none':
            logger.add_note("Already at target position")
            return
        elif direction is None:
            logger.add_note(f"Warning: Cannot find position for {nav}, using ctrl_home")
            ctrl_home()
            press_home()
            return
        
        # CRITICAL: Go to home FIRST, then move vertically
        logger.add_note(f"Semantic nav: Going home first, then {direction} {distance} lines")
        press_home()  # Ensure we're at column 0
        
        if direction == 'up':
            press_up(distance)
        else:
            press_down(distance)
        
        press_home()  # End at home position
        return
    
    # Raw navigation parsing - ALWAYS ensure home before vertical movement
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
        # CRITICAL: Go home FIRST before moving up
        press_home()
        n = int(parts[1])
        press_up(n)
        # Always end at home
        if len(parts) > 2 and parts[2] == "home":
            press_home()
        else:
            press_home()  # Force home even if not specified
    
    elif parts[0] == "down":
        # CRITICAL: Go home FIRST before moving down
        press_home()
        n = int(parts[1])
        press_down(n)
        # Always end at home
        if len(parts) > 2 and parts[2] == "home":
            press_home()
        else:
            press_home()  # Force home even if not specified

def pause(p_type):
    pauses = {'short': PAUSE_SHORT, 'medium': PAUSE_MEDIUM, 'long': PAUSE_LONG}
    duration = random.uniform(*pauses.get(p_type, PAUSE_MEDIUM))
    time.sleep(duration)

def maybe_typo(text):
    """Randomly introduce typos for realism"""
    if random.random() > TYPO_CHANCE or len(text) < 5:
        type_text(text)
        return
    
    # 70% chance: typo near end, then fix
    if random.random() < 0.7:
        type_text(text[:-2])
        type_char(random.choice('abcdefgh'))
        time.sleep(0.08)
        pyautogui.press('backspace')
        logger.log('backspace', 'backspace')
        time.sleep(0.08)
        type_text(text[-2:])
    else:
        type_text(text)

# ============================================================================
# TYPING
# ============================================================================

def type_code_step(step, is_first_step):
    """Type a single step of the coding sequence"""
    global position_tracker
    
    num = step['num']
    thought = step['thought']
    lines = step['lines']
    navigation = step.get('nav', 'none')
    pause_type = step.get('pause', 'medium')
    
    logger.set_step(num, thought)
    
    print(f"\n{'='*70}")
    print(f"STEP {num}: {thought}")
    print(f"{'='*70}")
    
    if position_tracker:
        logger.add_note(f"Before step - {position_tracker.get_status()}")
    
    # Thinking pause
    pause(pause_type)
    
    # Execute navigation
    if navigation != "none":
        print(f"  [NAV] {navigation}")
        execute_navigation(navigation)
        if position_tracker:
            logger.add_note(f"After navigation - {position_tracker.get_status()}")
    
    # Line separation between steps (if no navigation happened)
    if not is_first_step and navigation == "none":
        logger.add_note("Step separation - pressing Enter")
        press_enter()
        press_home()
    
    first_line = True
    
    for idx, line in enumerate(lines):
        # Handle blank lines
        if not line.strip():
            if not first_line:
                press_enter()
                press_home()
            first_line = False
            continue
        
        # New line if not first
        if not first_line:
            logger.add_note("New line - pressing Enter")
            press_enter()
            press_home()
        
        first_line = False
        
        # Count leading spaces for indentation
        num_spaces = len(line) - len(line.lstrip())
        stripped = line.lstrip()
        
        logger.add_note(f"Typing line: {num_spaces} spaces, '{stripped[:50]}'")
        
        # Type indentation
        for i in range(num_spaces):
            press_space()
        
        # Type content with possible typos
        print(f"    [TYPE] {stripped[:60]}...")
        maybe_typo(stripped)
        
        # IMPORTANT: Update position tracker AFTER typing the line, BEFORE pressing Enter
        # This lets the tracker know what's on the current line
        if position_tracker:
            position_tracker.typed_line(line)
            logger.add_note(f"Position updated - {position_tracker.get_status()}")
    
    if position_tracker:
        logger.add_note(f"After step - {position_tracker.get_status()}")
    
    time.sleep(0.2)

def execute_typing_sequence(sequence):
    """Execute the full typing sequence"""
    print("\n" + "="*70)
    print("STARTING TYPING SEQUENCE")
    print("="*70)
    print("[WARNING] Move mouse to corner to abort (PyAutoGUI failsafe)")
    
    for idx, step in enumerate(sequence['steps']):
        type_code_step(step, is_first_step=(idx == 0))
    
    logger.finalize()
    
    print("\n" + "="*70)
    print("TYPING COMPLETE")
    print("="*70)
    print(f"[LOG] Check {LOG_FILE} for details")

# ============================================================================
# MAIN
# ============================================================================

def main():
    global logger, position_tracker
    
    if len(sys.argv) < 2:
        print("""
HUMAN-LIKE CODE TYPER - Improved Version

USAGE:
    python script.py "problem description"
    python script.py "problem" --presig "class Solution:\\n    def method(self):"

EXAMPLES:
    python script.py "write fibonacci function"
    python script.py "two sum problem" --presig "class Solution:\\n    def twoSum(self, nums, target):"

FEATURES:
- Generates final code using LLM
- Creates human-like typing sequence (chain of thought)
- Simulates realistic coding: main skeleton -> helpers -> back to main
- Semantic navigation for complex problems
- Random typos and corrections
- Detailed logging
""")
        sys.exit(1)
    
    logger = KeystrokeLogger(LOG_FILE)
    position_tracker = PositionTracker()
    
    problem = sys.argv[1]
    presignature = None
    
    if '--presig' in sys.argv:
        idx = sys.argv.index('--presig')
        if idx + 1 < len(sys.argv):
            presignature = sys.argv[idx + 1]
    
    print("\n" + "="*70)
    print("HUMAN-LIKE CODE TYPER")
    print("="*70)
    
    # Initialize LLM
    model = init_llm()

    # Generate final code
    final_code = generate_final_code(model, problem, presignature)
    
    print("\n" + "="*70)
    print("FINAL CODE TO TYPE:")
    print("="*70)
    print(final_code)
    print("="*70)
    
    # Save code analysis for research
    save_code_analysis(final_code, os.path.join("data", "code_analysis.txt"))
    
    # Generate typing sequence
    sequence = generate_human_sequence(model, final_code, presignature)
    
    print(f"\n[OK] Typing sequence ready: {len(sequence['steps'])} steps")
    
    # Countdown
    print("\n" + "="*70)
    print("PREPARATION")
    print("="*70)
    print("[ACTION] Click in your code editor NOW!")
    print("[WARNING] Move mouse to corner to abort")
    print()
    
    for i in range(3, 0, -1):
        print(f"Starting in {i}...")
        time.sleep(1)
    
    print("\n[START] TYPING NOW!\n")
    
    # Execute typing
    execute_typing_sequence(sequence)
    
    # Show final result
    print("\n" + "="*70)
    print("EXPECTED FINAL CODE:")
    print("="*70)
    print(final_code)
    print("="*70)
    
    print("\n[FILES CREATED]")
    print("  - data/typing_debug.log : Keystroke log")
    print("  - data/typing_sequence.json : Chain of thought JSON")
    print("  - data/code_analysis.txt : Code structure analysis")
    print("  - data/llm_response.txt : Raw LLM response")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STOPPED] Interrupted by user")
        if logger:
            logger.finalize()
    except pyautogui.FailSafeException:
        print("\n[STOPPED] PyAutoGUI failsafe triggered (mouse in corner)")
        if logger:
            logger.finalize()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        if logger:
            logger.finalize()
        import traceback
        traceback.print_exc()