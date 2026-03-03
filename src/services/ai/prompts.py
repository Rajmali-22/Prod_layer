"""
INTERVIEW-OPTIMIZED SMART PROMPTS v2.0
Peak coding interview support with DSA categories, system design, and behavioral detection.
Output: Clean, plain text, no markdown - ready for live interviews.
"""

import re

# ============== DETECTION INDICATORS ==============

SYSTEM_DESIGN_INDICATORS = [
    'design a', 'design an', 'design the', 'system design', 'architect',
    'scale', 'scalable', 'scalability', 'distributed', 'microservice',
    'load balancer', 'database schema', 'api design', 'cache', 'caching',
    'sharding', 'replication', 'partition', 'consistent hashing',
    'design twitter', 'design uber', 'design instagram', 'design youtube',
    'design netflix', 'design whatsapp', 'design tinyurl', 'url shortener',
    'rate limiter', 'notification system', 'million users', 'billion',
    'high availability', 'fault tolerant', 'cap theorem', 'qps', 'throughput'
]

BEHAVIORAL_INDICATORS = [
    'tell me about a time', 'describe a time', 'describe a situation',
    'give me an example', 'give an example of', 'walk me through',
    'share an experience', 'challenging', 'difficult situation',
    'conflict', 'disagreement', 'failed', 'failure', 'mistake', 'setback',
    'leadership', 'led a team', 'managed', 'mentored', 'collaborated',
    'teamwork', 'cross-functional', 'proud of', 'achievement', 'accomplished',
    'strengths', 'weaknesses', 'why should we hire', 'why do you want',
    'where do you see yourself', 'what motivates', 'how do you handle'
]

DSA_CATEGORIES = {
    'dp': [
        'dynamic programming', 'memoization', 'memoize', 'tabulation',
        'knapsack', 'coin change', 'longest common subsequence', 'lcs',
        'fibonacci', 'edit distance', 'levenshtein', 'kadane',
        'house robber', 'climbing stairs', 'unique paths', 'min cost',
        'word break', 'decode ways', 'longest increasing subsequence', 'maximum subarray',
        ' dp ', ' dp[', 'dp array', 'dp table'
    ],

    'graph': [
        'graph', 'dijkstra', 'bellman', 'floyd warshall', 'topological',
        'union find', 'disjoint set', 'connected component', 'tarjan',
        'minimum spanning', 'kruskal', 'prim', 'mst', 'shortest path',
        'cycle detection', 'bipartite', 'adjacency', 'vertex', 'vertices',
        'network flow', 'directed', 'undirected', 'weighted graph'
    ],

    'tree': [
        'binary tree', 'bst', 'binary search tree', 'trie', 'prefix tree',
        'segment tree', 'fenwick', 'lca', 'lowest common ancestor',
        'inorder', 'preorder', 'postorder', 'level order', 'traversal',
        'height of tree', 'depth of tree', 'balanced tree', 'avl',
        'serialize', 'deserialize', 'flatten tree', 'invert tree'
    ],

    'linked_list': [
        'linked list', 'singly linked', 'doubly linked', 'reverse linked',
        'cycle in linked', 'detect cycle', 'merge linked', 'remove nth',
        'middle of linked', 'palindrome linked', 'intersection of linked',
        'copy random pointer', 'flatten linked'
    ],

    'binary_search': [
        'binary search', 'bisect', 'lower bound', 'upper bound',
        'search in rotated', 'rotated sorted', 'peak element',
        'find minimum in rotated', 'search insert', 'sqrt', 'square root',
        'first bad version', 'search range', 'median of two sorted'
    ],

    'two_pointer': [
        'two pointer', 'two pointers', 'sliding window', 'window',
        'fast slow', 'tortoise hare', 'container with most', 'trapping rain',
        'three sum', '3sum', 'four sum', '4sum', 'longest substring',
        'minimum window', 'fruit into basket', 'subarray sum'
    ],

    'stack_heap': [
        'stack', 'queue', 'heap', 'priority queue', 'deque', 'monotonic',
        'min heap', 'max heap', 'heapify', 'kth largest', 'kth smallest',
        'top k', 'k closest', 'valid parentheses', 'balanced brackets',
        'next greater', 'daily temperatures', 'largest rectangle',
        'histogram', 'sliding window maximum', 'median from stream'
    ],

    'backtracking': [
        'backtrack', 'backtracking', 'permutation', 'permutations',
        'combination', 'combinations', 'subset', 'subsets', 'power set',
        'n queens', 'n-queens', 'sudoku', 'word search', 'letter combinations',
        'generate parentheses', 'palindrome partitioning', 'combination sum',
        'restore ip'
    ]
}

GENERIC_CODE_INDICATORS = [
    'function', 'algorithm', 'implement', 'write a', 'code', 'program',
    'leetcode', 'hackerrank', 'codeforces', 'codechef', 'interviewbit',
    'debug', 'fix this', 'return', 'solution', 'solve', 'problem',
    'input:', 'output:', 'example:', 'example 1', 'example 2', 'constraints:',
    'def ', 'class', 'time complexity', 'space complexity',
    'array', 'string', 'matrix', 'nums', 'nums1', 'nums2', 'target',
    'sort', 'reverse', 'find', 'max', 'min', 'sum', 'count', 'check',
    'given an', 'given a', 'return the', 'return true', 'return false',
    'o(n)', 'o(1)', 'o(log', 'o(n^2)', 'brute force', 'optimal',
    'merge intervals', 'insert interval', 'meeting rooms', 'rotate image'
]

# Common LeetCode problem names - direct detection
LEETCODE_PROBLEMS = {
    'two_pointer': [
        'two sum', 'three sum', '3sum', 'four sum', '4sum',
        'container with most water', 'trapping rain water',
        'remove duplicates', 'move zeroes', 'sort colors',
        'longest substring without repeating'
    ],
    'dp': [
        'climbing stairs', 'house robber', 'coin change', 'word break',
        'longest palindromic', 'maximum subarray', 'jump game',
        'unique paths', 'minimum path sum', 'edit distance',
        'longest common subsequence', 'best time to buy and sell stock'
    ],
    'binary_search': [
        'search insert position', 'find first and last', 'search in rotated',
        'find minimum in rotated', 'peak element', 'first bad version',
        'sqrt', 'valid perfect square', 'koko eating bananas'
    ],
    'linked_list': [
        'reverse linked list', 'merge two sorted lists', 'linked list cycle',
        'remove nth node', 'middle of linked list', 'palindrome linked list',
        'intersection of two linked', 'add two numbers', 'reorder list'
    ],
    'tree': [
        'maximum depth', 'invert binary tree', 'same tree', 'symmetric tree',
        'level order traversal', 'validate bst', 'lowest common ancestor',
        'path sum', 'binary tree paths', 'serialize and deserialize',
        'construct binary tree'
    ],
    'graph': [
        'number of islands', 'clone graph', 'course schedule',
        'pacific atlantic', 'surrounded regions', 'rotting oranges',
        'word ladder', 'network delay time', 'cheapest flights'
    ],
    'stack_heap': [
        'valid parentheses', 'min stack', 'daily temperatures',
        'largest rectangle', 'kth largest element', 'top k frequent',
        'find median', 'merge k sorted', 'task scheduler'
    ],
    'backtracking': [
        'letter combinations', 'generate parentheses', 'permutations',
        'subsets', 'combination sum', 'word search', 'n-queens',
        'sudoku solver', 'palindrome partitioning'
    ]
}

Q_WORDS = ['what', 'how', 'why', 'when', 'where', 'who', 'which', 'explain', 'describe', 'tell']

# Code snippet indicators (actual code, not problem statements)
CODE_SNIPPET_PATTERNS = [
    r'^\s*def\s+\w+\s*\(',           # Python function
    r'^\s*class\s+\w+[\s:(]',         # Python/Java class
    r'^\s*function\s+\w+\s*\(',       # JavaScript function
    r'^\s*const\s+\w+\s*=',           # JavaScript const
    r'^\s*public\s+(static\s+)?',     # Java method
    r'^\s*private\s+(static\s+)?',    # Java method
    r'^\s*for\s*\(.+\)\s*[:{]',       # For loop
    r'^\s*while\s*\(.+\)\s*[:{]',     # While loop
    r'^\s*if\s*\(.+\)\s*[:{]',        # If statement
    r'^\s*return\s+',                 # Return statement
    r'^\s*import\s+',                 # Import statement
    r'^\s*from\s+\w+\s+import',       # Python import
    r'^\s*#include\s*<',              # C/C++ include
    r'^\s*using\s+namespace',         # C++ namespace
]


def is_code_snippet(text):
    """
    Detect if text is actual code (not a problem statement).
    Returns True if it looks like code to be explained.
    """
    lines = text.strip().split('\n')
    code_line_count = 0
    total_lines = len(lines)

    # Check for code patterns
    for line in lines:
        for pattern in CODE_SNIPPET_PATTERNS:
            if re.search(pattern, line, re.MULTILINE):
                code_line_count += 1
                break

    # If more than 30% of lines look like code, it's a code snippet
    if total_lines > 0 and code_line_count / total_lines > 0.3:
        return True

    # Check for common code structure indicators
    text_lower = text.lower()

    # Problem statements usually have these
    problem_indicators = [
        'given an array', 'given a string', 'given a linked list',
        'return the', 'find the', 'determine if', 'calculate the',
        'example 1:', 'example 2:', 'input:', 'output:', 'constraints:',
        'write a function', 'implement a', 'design a'
    ]

    has_problem_statement = any(ind in text_lower for ind in problem_indicators)

    # Code snippets usually have these (without problem text)
    code_only_indicators = [
        'def ', 'class ', 'function ', 'return ', '    if ', '    for ',
        '    while ', 'self.', 'this.', '};', '){', '():', '->'
    ]

    has_code_structure = sum(1 for ind in code_only_indicators if ind in text) >= 3

    # It's a code snippet if it has code structure but no problem statement
    return has_code_structure and not has_problem_statement


# ============== SYSTEM PROMPTS ==============

SYSTEM_PROMPTS = {
    'email': """You are an email reply assistant.

STRICT RULES:
1. Write a professional reply to the email
2. NO markdown formatting (no *, no -, no bullets)
3. Start directly with greeting (Hi/Hello/Dear)
4. Keep concise but address all points
5. Match the tone of original email
6. End with appropriate closing (Regards/Thanks/Best)

Output the reply only. Ready to send.""",

    'system_design': """You are a system design interview assistant.

RESPONSE FORMAT (plain text, numbered):
1. REQUIREMENTS
   Functional: [2-3 key features in one line]
   Non-functional: [scale, latency, availability]

2. HIGH-LEVEL DESIGN
   [3-4 sentences: core components, data flow]
   Components: [list main services]

3. DEEP DIVE
   [2-3 critical components with WHY for each choice]
   Data model: [key entities]

4. SCALE AND TRADE-OFFS
   Bottleneck: [main issue and solution]
   Trade-off: [one key decision]

STRICT RULES:
1. NO markdown (no *, no -, no #)
2. Use numbered format as shown above
3. Keep each section 2-4 lines
4. Mention specific numbers (QPS, storage size)
5. Ready to speak in interview""",

    'behavioral': """You are a behavioral interview assistant.

USE STAR FORMAT:
SITUATION: [1-2 sentences - when, where, what project/context]

TASK: [1 sentence - your specific responsibility]

ACTION: [2-3 sentences - what YOU did, use "I" not "we", be specific]

RESULT: [1-2 sentences - outcome with metrics/impact if possible]

STRICT RULES:
1. NO markdown (no *, no -)
2. Use exact labels: SITUATION, TASK, ACTION, RESULT
3. Total under 150 words
4. Focus on YOUR actions
5. Include specific details (numbers, timeline)
6. End with positive outcome
7. Sound natural, not scripted""",

    'dp': """You are a coding assistant for Dynamic Programming problems.

OUTPUT FORMAT:
# Recurrence: dp[i] = ...
[solution code]
# Time: O(?), Space: O(?)

STRICT RULES:
1. Start with recurrence relation comment
2. Prefer iterative (tabulation) over recursive
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'graph': """You are a coding assistant for Graph problems.

OUTPUT FORMAT:
# Approach: [BFS/DFS/Dijkstra/etc]
[solution code]
# Time: O(?), Space: O(?)

STRICT RULES:
1. State approach in comment
2. Build adjacency structure if needed
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'tree': """You are a coding assistant for Tree problems.

OUTPUT FORMAT:
# Approach: [DFS/BFS + traversal type]
[solution code]
# Time: O(?), Space: O(?)

STRICT RULES:
1. Include TreeNode class if not provided
2. Handle null/empty tree
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'linked_list': """You are a coding assistant for Linked List problems.

OUTPUT FORMAT:
# Approach: [two-pointer/dummy head/etc]
[solution code]
# Time: O(?), Space: O(?)

STRICT RULES:
1. Include ListNode class if not provided
2. Handle empty list and single node
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'binary_search': """You are a coding assistant for Binary Search problems.

OUTPUT FORMAT:
# Search space: [what we're searching]
[solution code]
# Time: O(log n), Space: O(?)

STRICT RULES:
1. Use left, right, mid naming
2. Clear termination condition
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'two_pointer': """You are a coding assistant for Two Pointer / Sliding Window problems.

OUTPUT FORMAT:
# Approach: [two-pointer/sliding window]
[solution code]
# Time: O(?), Space: O(?)

STRICT RULES:
1. Use clear names: left, right, start, end
2. Handle edge cases
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'stack_heap': """You are a coding assistant for Stack/Queue/Heap problems.

OUTPUT FORMAT:
# Data structure: [stack/heap/etc]
[solution code]
# Time: O(?), Space: O(?)

STRICT RULES:
1. Use Python's heapq (negate for max heap)
2. Handle empty structure
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'backtracking': """You are a coding assistant for Backtracking/Recursion problems.

OUTPUT FORMAT:
# Choice/Constraint/Goal
[solution code]
# Time: O(?), Space: O(?)

STRICT RULES:
1. Clear base case
2. Make choice -> recurse -> undo choice
3. End with complexity comment
4. NO markdown (no ```)
5. NO explanations - code only""",

    'code_problem': """You are a LeetCode/HackerRank coding assistant.

OUTPUT FORMAT:
def functionName(params):
    # solution
    return result
# Time: O(?), Space: O(?)

STRICT RULES:
1. Output function ready to paste into LeetCode
2. NO class Solution wrapper unless asked
3. Handle edge cases
4. End with complexity comment
5. NO markdown (no ```)
6. NO explanations - code only""",

    'code_snippet': """You are a code explanation expert for technical interviews.

EXPLAIN THE CODE IN THIS FORMAT:

WHAT IT DOES:
[1-2 sentences - high level purpose]

HOW IT WORKS:
1. [First key step]
2. [Second key step]
3. [Third key step]
[Add more steps if needed]

KEY TECHNIQUES:
[List 2-3 techniques/patterns used, e.g., "Two pointers", "Hash map for O(1) lookup"]

COMPLEXITY:
Time: O(?) - [brief reason]
Space: O(?) - [brief reason]

EDGE CASES HANDLED:
[List 1-2 edge cases the code handles]

STRICT RULES:
1. NO markdown (no *, no `, no -)
2. Use the exact format above with labels
3. Be concise but thorough
4. Focus on WHY decisions were made
5. Mention any potential improvements
6. Ready to explain in interview""",

    'term': """You are an interview prep assistant.

STRICT RULES:
1. Explain in exactly 25-35 words
2. NO markdown formatting
3. NO preambles like "This is..." or "It refers to..."
4. Start directly with the definition
5. Sound natural, like explaining to interviewer
6. One clear sentence or two short ones

Output will be spoken in interview.""",

    'question': """You are an interview answer assistant.

STRICT RULES:
1. Answer in 2-4 sentences MAX
2. NO markdown (no *, no -, no bullets)
3. NO preambles ("Well...", "Great question...")
4. Start with direct answer
5. Be specific, not generic
6. If listing points, use "First... Second..." not bullets

Output will be spoken in interview.""",

    'general': """You are a text improver for professional communication.

STRICT RULES:
1. Fix grammar and improve clarity
2. Keep professional but natural
3. NO markdown formatting
4. Output ONLY the improved text
5. Keep similar length to original""",

    'custom': """Follow the user's instruction exactly.

STRICT RULES:
1. NO markdown formatting (no *, no `, no -)
2. NO preambles or explanations
3. Output ONLY what was requested
4. Keep concise and interview-ready""",

    'code_explanation': """You are an interview coach explaining code solutions.

OUTPUT FORMAT:
Approach: [1 line - technique name and why]
Key insight: [1 line - the core idea]
Steps: [2-3 numbered steps, brief]
Time: O(?) Space: O(?)

STRICT RULES:
1. Keep VERY brief - interviewer is watching
2. NO markdown (no *, no -, no bullets)
3. Use numbered steps: 1. 2. 3.
4. Focus on WHY not HOW
5. Under 80 words total"""
}


# ============== DETECTION FUNCTIONS ==============

def _is_email(text_lower, word_count):
    """Check if text is an email."""
    # Use word boundary patterns to avoid false matches (e.g., "they" matching "hey ")
    email_greeting_patterns = [
        r'^dear\s+\w+', r'^hi\s+\w+', r'^hello\s+\w+', r'^hey\s+\w+',
        r'^good morning', r'^good afternoon', r'^good evening'
    ]
    email_indicators = [
        'subject:', 'from:', 'sent:', 'regards,', 'sincerely,',
        'best regards', 'thanks,', 'thank you,', 'cheers,', 'best,',
        'please find attached', 'following up on', 'i am writing to',
        'looking forward to', 'let me know if', 'could you please'
    ]

    # Check greeting patterns (start of text)
    has_greeting = any(re.match(pattern, text_lower) for pattern in email_greeting_patterns)

    # Check email body indicators
    has_email_indicator = any(ind in text_lower for ind in email_indicators)

    # Check for email address
    has_email_address = bool(re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text_lower))

    return has_greeting or (has_email_indicator and word_count > 10) or has_email_address


def detect_text_type(text):
    """
    Detect text type with DSA sub-category support.
    Returns: (category, subcategory) e.g., ('code_problem', 'dp')
    """
    text_lower = text.lower().strip()
    word_count = len(text.split())

    # 1. Email (check first - emails can contain any keywords)
    if _is_email(text_lower, word_count):
        return ('email', None)

    # 2. Code snippet (actual code to explain, not a problem to solve)
    # Check this before problem detection
    if is_code_snippet(text):
        return ('code_snippet', None)

    # 3. System Design (before generic code)
    if any(ind in text_lower for ind in SYSTEM_DESIGN_INDICATORS):
        return ('system_design', None)

    # 4. Behavioral (before generic question)
    if any(ind in text_lower for ind in BEHAVIORAL_INDICATORS):
        return ('behavioral', None)

    # 5. Check LeetCode problem names first (most specific)
    for cat, problems in LEETCODE_PROBLEMS.items():
        if any(prob in text_lower for prob in problems):
            return ('code_problem', cat)

    # 6. DSA Sub-categories (priority order: specific to general)
    # linked_list before dp to avoid "list" matching "lis" in dp keywords
    dsa_priority = ['linked_list', 'binary_search', 'two_pointer', 'stack_heap',
                    'backtracking', 'dp', 'graph', 'tree']

    for cat in dsa_priority:
        keywords = DSA_CATEGORIES[cat]
        if any(kw in text_lower for kw in keywords):
            return ('code_problem', cat)

    # 5. Generic code problem
    if any(ind in text_lower for ind in GENERIC_CODE_INDICATORS):
        return ('code_problem', 'general')

    # 6. Term (short, no question mark)
    if word_count <= 5 and '?' not in text:
        return ('term', None)

    # 7. Question
    if '?' in text or any(text_lower.startswith(q) for q in Q_WORDS):
        return ('question', None)

    return ('general', None)


# ============== PROMPT BUILDER ==============

def _build_user_prompt(text, category, subcategory):
    """Build category-specific user prompts."""

    if category == 'email':
        return f"""Write a reply to this email:

{text}

Reply directly. No markdown. Start with greeting, end with closing."""

    elif category == 'system_design':
        return f"""{text}

Design following the structure: Requirements, High-Level Design, Deep Dive, Scale/Trade-offs.
Use numbered format. Plain text only. No markdown."""

    elif category == 'behavioral':
        return f"""{text}

Answer using STAR format (SITUATION, TASK, ACTION, RESULT).
Under 150 words. Focus on YOUR actions. Plain text only."""

    elif category == 'code_problem':
        hints = {
            'dp': 'Include recurrence relation and state definition as comments.',
            'graph': 'State approach (BFS/DFS/etc) and graph representation.',
            'tree': 'State traversal type. Handle null tree.',
            'linked_list': 'State approach. Handle empty list.',
            'binary_search': 'Define search space and condition clearly.',
            'two_pointer': 'State what pointers/window represent.',
            'stack_heap': 'State which data structure and why.',
            'backtracking': 'State choice, constraint, and goal.',
            'general': 'Handle edge cases.'
        }
        hint = hints.get(subcategory, hints['general'])

        return f"""{text}

Write solution code only. {hint}
Include time/space complexity as final comment. No explanations. No markdown."""

    elif category == 'code_snippet':
        return f"""Explain this code in detail for a technical interview:

{text}

Use the format: WHAT IT DOES, HOW IT WORKS (numbered steps), KEY TECHNIQUES, COMPLEXITY, EDGE CASES HANDLED.
No markdown. Ready to speak in interview."""

    elif category == 'term':
        return f"""Define this for an interview (25-35 words, no markdown): {text}"""

    elif category == 'question':
        return f"""{text}

Answer directly in 2-4 sentences. No bullets. No markdown."""

    else:  # general
        return f"""Improve this text (no markdown): {text}"""


def build_prompt(text, user_instruction=None, mode='clipboard'):
    """
    Build interview-optimized prompts with category-specific handling.
    Returns: (system_prompt, user_prompt)
    """

    # Custom instruction provided
    if user_instruction and user_instruction.strip():
        system_prompt = SYSTEM_PROMPTS['custom']
        user_prompt = f"""Instruction: {user_instruction}

Text: {text}

Remember: No markdown, no preambles. Direct output only."""
        return (system_prompt, user_prompt)

    # Auto-detect with sub-category support
    category, subcategory = detect_text_type(text)

    # Select system prompt based on category and subcategory
    if category == 'code_problem' and subcategory and subcategory in SYSTEM_PROMPTS:
        system_prompt = SYSTEM_PROMPTS[subcategory]
    else:
        system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS['general'])

    # Build user prompt
    user_prompt = _build_user_prompt(text, category, subcategory)

    return (system_prompt, user_prompt)


def build_explanation_prompt(problem_text, code_text):
    """
    Build prompt for code explanation (second API call in coding mode).
    Returns: (system_prompt, user_prompt)
    """
    system_prompt = SYSTEM_PROMPTS['code_explanation']

    user_prompt = f"""Problem: {problem_text}

Solution code:
{code_text}

Explain this solution for an interview. Be very brief."""

    return (system_prompt, user_prompt)


# ============== OUTPUT CLEANER ==============

def clean_output(text):
    """
    Aggressively clean output for interview use.
    Removes ALL markdown and preambles.
    """
    if not text:
        return text

    # Remove code blocks
    text = re.sub(r'```[\w]*\n?', '', text)
    text = re.sub(r'```', '', text)

    # Remove inline code backticks
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)

    # Remove bullet points
    text = re.sub(r'^[\s]*[-*•]\s+', '', text, flags=re.MULTILINE)

    # Remove numbered list formatting (but keep numbers in context)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remove headers
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

    # Remove preambles - very aggressive
    preambles = [
        # Common AI pleasantries
        r'^Sure[,!]?\s*',
        r'^Certainly[,!]?\s*',
        r'^Of course[,!]?\s*',
        r'^Absolutely[,!]?\s*',
        r'^Great[,!]?\s*',
        r'^Good question[,!]?\s*',
        r'^Great question[,!]?\s*',
        r'^Okay[,!]?\s*',
        r'^Alright[,!]?\s*',
        r'^Yes[,!]?\s*',
        r'^No problem[,!]?\s*',
        r'^Happy to help[,!]?\s*',
        r'^I\'d be happy to[\w\s]*[:\s]*',
        r'^I\'ll[\w\s]*[:\s]*',
        r'^Let me[\w\s]*[:\s]*',

        # "Here is/Here's" variations
        r'^Here\'s?\s+(the\s+)?(your\s+)?(a\s+)?(an\s+)?(my\s+)?[\w\s]*[:\s]*',
        r'^Here\s+is\s+(the\s+)?(your\s+)?(a\s+)?(an\s+)?(my\s+)?[\w\s]*[:\s]*',
        r'^Here\s+you\s+go[:\s]*',
        r'^Here\s+it\s+is[:\s]*',

        # "Below/Above" variations
        r'^Below\s+is[\w\s]*[:\s]*',
        r'^Above\s+is[\w\s]*[:\s]*',
        r'^Following\s+is[\w\s]*[:\s]*',

        # "I've/I have" variations
        r'^I\'ve\s+[\w\s]*[:\s]*',
        r'^I\s+have\s+[\w\s]*[:\s]*',
        r'^I\'ll\s+[\w\s]*[:\s]*',
        r'^I\s+will\s+[\w\s]*[:\s]*',

        # Explanation starters
        r'^The\s+answer\s+is[:\s]*',
        r'^The\s+solution\s+is[:\s]*',
        r'^The\s+code\s+is[:\s]*',
        r'^This\s+(is|refers\s+to)[:\s]*',
        r'^In\s+short[,:\s]*',
        r'^To\s+put\s+it\s+simply[,:\s]*',
        r'^Basically[,:\s]*',
        r'^Simply\s+put[,:\s]*',
        r'^In\s+summary[,:\s]*',
        r'^To\s+summarize[,:\s]*',

        # Filler words at start
        r'^Well[,]?\s+',
        r'^So[,]?\s+',
        r'^Now[,]?\s+',
        r'^Actually[,]?\s+',
        r'^Essentially[,]?\s+',
    ]

    for pattern in preambles:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)

    # Remove trailing fluff
    trailing_patterns = [
        r'\s*Let me know if.*$',
        r'\s*Hope this helps.*$',
        r'\s*Feel free to.*$',
        r'\s*Is there anything.*$',
        r'\s*If you have any.*$',
        r'\s*Please let me know.*$',
        r'\s*Don\'t hesitate to.*$',
        r'\s*Happy to help.*$',
        r'\s*Good luck.*$',
        r'\s*Best of luck.*$',
        r'\s*I hope this.*$',
        r'\s*This should.*work.*$',
        r'\s*You can modify.*$',
    ]

    for pattern in trailing_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)

    # Clean whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Run preamble removal again (in case nested)
    for pattern in preambles:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)

    text = text.strip()
    return text


