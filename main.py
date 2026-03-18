#!/usr/bin/env python3
"""
Riichi Mahjong AI Trainer - Entry Point
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from terminal_ui import run_game

if __name__ == "__main__":
    run_game()
