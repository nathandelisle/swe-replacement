#!/usr/bin/env python3
"""
Ensure the control repository exists.
This script verifies that repos/control exists and is ready for use.
"""
import sys
from pathlib import Path


def ensure_control_exists():
    """Ensure control directory exists."""
    control_dir = Path("control")
    
    # Check if control exists
    if control_dir.exists():
        print(f"Control repository already exists at '{control_dir}'", flush=True)
    else:
        print(f"Error: Control directory '{control_dir}' not found!", flush=True)
        print("Please create it manually with the required files.", flush=True)
        sys.exit(1)
    
    return 0


if __name__ == "__main__":
    sys.exit(ensure_control_exists()) 