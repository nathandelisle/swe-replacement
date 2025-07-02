#!/usr/bin/env python3
"""
Run a single trial of the SWE replacement experiment.
Launches a Docker container and manages the agent interaction.
"""
import argparse
import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path


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
        
    def prepare_trial(self):
        """Prepare the environment for the trial."""
        # Create results directory
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Save trial metadata
        metadata = {
            "trial_id": self.trial_id,
            "repo_type": self.repo_type,
            "start_time": datetime.utcnow().isoformat(),
            "container_name": self.container_name
        }
        
        with open(self.results_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
            
    def run_container(self):
        """Launch and run the Docker container."""
        # Prepare the Docker run command
        docker_cmd = [
            "docker", "run",
            "--name", self.container_name,
            "--rm",  # Remove container after exit
            "-v", f"{os.path.abspath('../repos/' + self.repo_type)}:/workspace:rw",
            "-v", f"{os.path.abspath(str(self.results_dir))}:/results:rw",
            "-e", f"TRIAL_ID={self.trial_id}",
            "-e", f"REPO_TYPE={self.repo_type}",
            "-e", f"ANTHROPIC_API_KEY={os.environ.get('ANTHROPIC_API_KEY', '')}",
            "swe-replacement:latest"
        ]
        
        print(f"Starting trial {self.trial_id} with {self.repo_type} repository...")
        
        try:
            # Run the container
            result = subprocess.run(docker_cmd, capture_output=True, text=True)
            
            # Save container output
            with open(self.results_dir / "container_output.txt", 'w') as f:
                f.write("STDOUT:\n")
                f.write(result.stdout)
                f.write("\n\nSTDERR:\n")
                f.write(result.stderr)
                
            return result.returncode == 0
            
        except Exception as e:
            print(f"Error running container: {e}")
            return False
            
    def collect_results(self):
        """Collect and organize trial results."""
        # Copy harness log from container
        # Note: This assumes the harness writes logs to a known location
        
        # Get git history of changes
        git_log_cmd = ["git", "-C", f"../repos/{self.repo_type}", "log", "--oneline"]
        git_log = subprocess.run(git_log_cmd, capture_output=True, text=True)
        
        with open(self.results_dir / "git_history.txt", 'w') as f:
            f.write(git_log.stdout)
            
        # Update metadata with completion time
        with open(self.results_dir / "metadata.json", 'r') as f:
            metadata = json.load(f)
            
        metadata["end_time"] = datetime.utcnow().isoformat()
        
        with open(self.results_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
            
        print(f"Trial {self.trial_id} completed. Results saved to {self.results_dir}")
        
    def run(self):
        """Execute the complete trial."""
        self.prepare_trial()
        success = self.run_container()
        self.collect_results()
        return success


def main():
    parser = argparse.ArgumentParser(description="Run a single SWE replacement trial")
    parser.add_argument("repo_type", choices=["control", "treatment"],
                       help="Type of repository to use")
    parser.add_argument("--trial-id", help="Unique trial identifier")
    
    args = parser.parse_args()
    
    runner = TrialRunner(args.repo_type, args.trial_id)
    success = runner.run()
    
    exit(0 if success else 1)


if __name__ == "__main__":
    main() 