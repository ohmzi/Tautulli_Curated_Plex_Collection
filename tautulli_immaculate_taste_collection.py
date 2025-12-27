#!/usr/bin/env python3
"""
Backward-compatible entry point for Tautulli automation.

This script is a wrapper that calls the main module from the new package structure.
It maintains compatibility with existing Tautulli configurations.
"""

import sys
from pathlib import Path

# Add src to path so we can import the package
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))

# Import and run the main function
from tautulli_curated.main import main

if __name__ == "__main__":
    raise SystemExit(main())
