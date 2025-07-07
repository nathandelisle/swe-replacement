#!/usr/bin/env python3
"""
Ensure the treatment repository exists.
This script verifies that repos/treatment exists and is ready for use.
"""
import sys
from pathlib import Path


def ensure_treatment_exists():
    """Ensure treatment directory exists."""
    treatment_dir = Path("treatment")
    
    # Check if treatment exists
    if treatment_dir.exists():
        print(f"Treatment repository already exists at '{treatment_dir}'", flush=True)
    else:
        print(f"Error: Treatment directory '{treatment_dir}' not found!", flush=True)
        print("Please create it manually with the required files.", flush=True)
        sys.exit(1)
    
    return 0


if __name__ == "__main__":
    sys.exit(ensure_treatment_exists()) 