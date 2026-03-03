#!/usr/bin/env python3
"""
Input Monitor — Entry point for the keystroke monitoring service.

Delegates to the `monitor` package for all implementation.
Communicates with Electron main process via stdin/stdout JSON.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitor import main

if __name__ == "__main__":
    main()
