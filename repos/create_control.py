#!/usr/bin/env python3
"""
Create a control clone of the reference repository.
This clone is identical to the reference, with no replacement warning.
"""
import os
import shutil
import sys


def create_control_clone():
    """Create a bit-identical control clone of the reference repository."""
    reference_dir = "reference"
    control_dir = "control"
    
    # Check if reference exists
    if not os.path.exists(reference_dir):
        print(f"Error: Reference directory '{reference_dir}' not found!")
        sys.exit(1)
    
    # Remove existing control directory if it exists
    if os.path.exists(control_dir):
        shutil.rmtree(control_dir)
    
    # Create bit-identical copy
    shutil.copytree(reference_dir, control_dir)
    
    print(f"Created control clone in '{control_dir}'")
    

if __name__ == "__main__":
    create_control_clone() 