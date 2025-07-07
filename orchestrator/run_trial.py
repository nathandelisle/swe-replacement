#!/usr/bin/env python3
"""
Run a single trial of the SWE replacement experiment.
Launches a Docker container and manages the agent interaction.
"""
import argparse
import json
import os
import subprocess
import tempfile
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
import sys
from dotenv import load_dotenv


class TrialRunner:
    def __init__(self, repo_type: str, trial_id: str = None):
        """
        Initialize the trial runner.
        
        Args:
            repo_type: Either 'control' or 'treatment'
            trial_id: Unique identifier for this trial (auto-generated if not provided)
        """
        self.repo_type = repo_type
        self.trial_id = trial_id or str(uuid.uuid4())[:8]
        self.container_name = f"swe-trial-{self.trial_id}"
        self.results_dir = Path("../results") / f"{repo_type}_{self.trial_id}"
        self.temp_workspace = None
        
    def prepare_trial(self):
        """Prepare the environment for the trial."""
        # Create results directory
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Create temporary workspace directory
        self.temp_workspace = tempfile.mkdtemp(prefix=f"swe_trial_{self.trial_id}_")
        
        # Copy the appropriate repository to temp workspace
        source_repo = Path("../repos") / self.repo_type
        if not source_repo.exists():
            raise RuntimeError(f"Source repository {source_repo} not found! Run create_{self.repo_type}.py first.")
            
        # Copy all files from source repo to temp workspace
        for item in source_repo.iterdir():
            if item.is_file():
                shutil.copy2(item, self.temp_workspace)
            elif item.is_dir():
                shutil.copytree(item, os.path.join(self.temp_workspace, item.name))
                
        print(f"Created isolated workspace at: {self.temp_workspace}")
        
        # Save trial metadata
        metadata = {
            "trial_id": self.trial_id,
            "repo_type": self.repo_type,
            "start_time": datetime.utcnow().isoformat(),
            "container_name": self.container_name,
            "temp_workspace": self.temp_workspace
        }
        
        with open(self.results_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
            
    def run_container(self):
        """Launch and run the Docker container with security isolation."""
        # Create a volume for the harness code (read-only for agent)
        harness_path = os.path.abspath("../harness")
        
        # Prepare the Docker run command with security flags
        docker_cmd = [
            "docker", "run",
            "--name", self.container_name,
            "--rm",  # Remove container after exit
            "--network", "none",  # No network access
            "--memory", "2g",  # Memory limit
            "--cpus", "1.0",  # CPU limit
            "--read-only",  # Read-only root filesystem
            "--tmpfs", "/tmp:size=100M",  # Writable /tmp
            "--security-opt", "no-new-privileges",  # Prevent privilege escalation
            "--cap-drop", "ALL",  # Drop all capabilities
            "-v", f"{self.temp_workspace}:/workspace:rw,nodev,nosuid",  # Workspace volume with security options
            "-v", f"{harness_path}:/harness:ro",  # Harness code (read-only)
            "-v", f"{os.path.abspath(str(self.results_dir))}:/results:rw",  # Results volume
            "-e", f"TRIAL_ID={self.trial_id}",
            "-e", f"REPO_TYPE={self.repo_type}",
            "-e", f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
            "-e", "PYTHONDONTWRITEBYTECODE=1",  # Don't write .pyc files
            "swe-replacement:latest"
        ]
        
        print(f"Starting trial {self.trial_id} with {self.repo_type} repository...")
        print(f"Container will have no network access (--network none)")
        
        try:
            # Run the container
            start_time = time.time()
            result = subprocess.run(docker_cmd, capture_output=True, text=True)
            duration = time.time() - start_time
            
            # Save container output
            with open(self.results_dir / "container_output.txt", 'w') as f:
                f.write(f"Exit code: {result.returncode}\n")
                f.write(f"Duration: {duration:.2f} seconds\n\n")
                f.write("STDOUT:\n")
                f.write(result.stdout)
                f.write("\n\nSTDERR:\n")
                f.write(result.stderr)
                
            return result.returncode == 0
            
        except Exception as e:
            print(f"Error running container: {e}")
            with open(self.results_dir / "error.txt", 'w') as f:
                f.write(f"Container launch error: {str(e)}\n")
            return False
            
    def collect_results(self):
        """Collect and organize trial results."""
        # Copy the harness log if it exists
        harness_log = os.path.join(self.temp_workspace, "harness.log")
        if os.path.exists(harness_log):
            shutil.copy2(harness_log, self.results_dir / "harness.log")
            
        # Copy the final workspace state
        workspace_archive = self.results_dir / "final_workspace"
        workspace_archive.mkdir(exist_ok=True)
        
        # Copy key files from workspace
        for item in ["functions.py", "test_functions.py", "notes.md", ".agent_state.json"]:
            src = os.path.join(self.temp_workspace, item)
            if os.path.exists(src):
                shutil.copy2(src, workspace_archive / item)
                
        # Get git history if initialized
        try:
            git_log = subprocess.run(
                ["git", "-C", self.temp_workspace, "log", "--oneline", "--all"],
                capture_output=True,
                text=True
            )
            if git_log.returncode == 0:
                with open(self.results_dir / "git_history.txt", 'w') as f:
                    f.write(git_log.stdout)
                    
            # Also save full git diff
            git_diff = subprocess.run(
                ["git", "-C", self.temp_workspace, "diff", "--no-index", 
                 f"{os.path.abspath('../repos/' + self.repo_type)}/functions.py",
                 f"{self.temp_workspace}/functions.py"],
                capture_output=True,
                text=True
            )
            if git_diff.stdout:
                with open(self.results_dir / "final_diff.patch", 'w') as f:
                    f.write(git_diff.stdout)
        except:
            pass
            
        # Update metadata with completion time
        with open(self.results_dir / "metadata.json", 'r') as f:
            metadata = json.load(f)
            
        metadata["end_time"] = datetime.utcnow().isoformat()
        
        with open(self.results_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
            
        print(f"Trial {self.trial_id} completed. Results saved to {self.results_dir}")
        
    def cleanup(self):
        """Clean up temporary workspace."""
        if self.temp_workspace and os.path.exists(self.temp_workspace):
            shutil.rmtree(self.temp_workspace)
            print(f"Cleaned up temporary workspace: {self.temp_workspace}")
        
    def run(self):
        """Execute the complete trial."""
        try:
            self.prepare_trial()
            success = self.run_container()
            self.collect_results()
            return success
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Run a single SWE replacement trial")
    parser.add_argument("repo_type", choices=["control", "treatment"],
                       help="Type of repository to use")
    parser.add_argument("--trial-id", help="Unique trial identifier")
    
    args = parser.parse_args()
    
    # Load .env file from various locations
    env_loaded = False
    env_locations = [
        Path(".env"),                    # Current directory
        Path("../.env"),                 # Parent directory (project root)
        Path("orchestrator/.env"),       # Orchestrator directory
        Path(os.path.expanduser("~/.env")),  # User home directory
    ]
    
    for env_path in env_locations:
        if env_path.exists():
            load_dotenv(env_path)
            env_loaded = True
            print(f"Loaded .env file from: {env_path}")
            break
    
    if not env_loaded:
        print("Note: No .env file found. Using system environment variables.")
    
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not found!")
        print("\nPlease set it in one of these ways:")
        print("1. Create a .env file with: ANTHROPIC_API_KEY=your-key-here")
        print("2. Set the environment variable: export ANTHROPIC_API_KEY=your-key-here")
        print("\n.env file can be placed in:")
        for path in env_locations:
            print(f"  - {path}")
        sys.exit(1)
    
    runner = TrialRunner(args.repo_type, args.trial_id)
    success = runner.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 