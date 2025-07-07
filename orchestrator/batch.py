#!/usr/bin/env python3
"""
Batch runner for the SWE replacement experiment.
Runs 30 trials each for control and treatment groups.
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv


class BatchRunner:
    def __init__(self, num_trials: int = 30, max_parallel: int = 5):
        """
        Initialize the batch runner.
        
        Args:
            num_trials: Number of trials per condition (default: 30)
            max_parallel: Maximum number of parallel trials (default: 5)
        """
        self.num_trials = num_trials
        self.max_parallel = max_parallel
        self.batch_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.results_dir = Path("../results") / f"batch_{self.batch_id}"
        
    def prepare_batch(self):
        """Prepare for the batch run."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Save batch metadata
        metadata = {
            "batch_id": self.batch_id,
            "num_trials_per_condition": self.num_trials,
            "max_parallel": self.max_parallel,
            "start_time": datetime.utcnow().isoformat(),
            "conditions": ["control", "treatment"]
        }
        
        with open(self.results_dir / "batch_metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
            
        print(f"Starting batch {self.batch_id}")
        print(f"Running {self.num_trials} trials each for control and treatment")
        
    def run_single_trial(self, repo_type: str, trial_num: int) -> dict:
        """Run a single trial and return results."""
        trial_id = f"{self.batch_id}_{repo_type}_{trial_num:02d}"
        
        print(f"Starting trial {trial_id}")
        
        cmd = ["python", "run_trial.py", repo_type, "--trial-id", trial_id]
        
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True)
        end_time = time.time()
        
        trial_result = {
            "trial_id": trial_id,
            "repo_type": repo_type,
            "trial_num": trial_num,
            "success": result.returncode == 0,
            "duration": end_time - start_time,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
        
        print(f"Completed trial {trial_id} in {trial_result['duration']:.2f}s")
        
        return trial_result
        
    def run_all_trials(self):
        """Run all trials using parallel execution."""
        all_results = []
        
        # Create list of all trials to run
        trials = []
        for repo_type in ["control", "treatment"]:
            for i in range(self.num_trials):
                trials.append((repo_type, i + 1))
                
        # Run trials in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            future_to_trial = {
                executor.submit(self.run_single_trial, repo_type, trial_num): (repo_type, trial_num)
                for repo_type, trial_num in trials
            }
            
            for future in concurrent.futures.as_completed(future_to_trial):
                repo_type, trial_num = future_to_trial[future]
                try:
                    result = future.result()
                    all_results.append(result)
                except Exception as e:
                    print(f"Trial {repo_type}_{trial_num} failed with error: {e}")
                    all_results.append({
                        "trial_id": f"{self.batch_id}_{repo_type}_{trial_num:02d}",
                        "repo_type": repo_type,
                        "trial_num": trial_num,
                        "success": False,
                        "error": str(e)
                    })
                    
        return all_results
        
    def save_summary(self, results):
        """Save summary of batch results."""
        # Calculate statistics
        control_results = [r for r in results if r["repo_type"] == "control"]
        treatment_results = [r for r in results if r["repo_type"] == "treatment"]
        
        summary = {
            "batch_id": self.batch_id,
            "total_trials": len(results),
            "control": {
                "total": len(control_results),
                "successful": sum(1 for r in control_results if r.get("success", False)),
                "failed": sum(1 for r in control_results if not r.get("success", False)),
                "avg_duration": sum(r.get("duration", 0) for r in control_results) / len(control_results) if control_results else 0
            },
            "treatment": {
                "total": len(treatment_results),
                "successful": sum(1 for r in treatment_results if r.get("success", False)),
                "failed": sum(1 for r in treatment_results if not r.get("success", False)),
                "avg_duration": sum(r.get("duration", 0) for r in treatment_results) / len(treatment_results) if treatment_results else 0
            }
        }
        
        # Save summary
        with open(self.results_dir / "batch_summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
            
        # Save detailed results
        with open(self.results_dir / "all_trial_results.json", 'w') as f:
            json.dump(results, f, indent=2)
            
        # Update metadata with end time
        with open(self.results_dir / "batch_metadata.json", 'r') as f:
            metadata = json.load(f)
            
        metadata["end_time"] = datetime.utcnow().isoformat()
        metadata["total_duration"] = time.time() - time.mktime(
            datetime.fromisoformat(metadata["start_time"]).timetuple()
        )
        
        with open(self.results_dir / "batch_metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
            
        print(f"\nBatch {self.batch_id} completed!")
        print(f"Control: {summary['control']['successful']}/{summary['control']['total']} successful")
        print(f"Treatment: {summary['treatment']['successful']}/{summary['treatment']['total']} successful")
        
    def run(self):
        """Execute the complete batch."""
        self.prepare_batch()
        results = self.run_all_trials()
        self.save_summary(results)


def main():
    parser = argparse.ArgumentParser(description="Run batch of SWE replacement trials")
    parser.add_argument("--num-trials", type=int, default=30,
                       help="Number of trials per condition (default: 30)")
    parser.add_argument("--max-parallel", type=int, default=5,
                       help="Maximum parallel trials (default: 5)")
    
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
        return
    
    runner = BatchRunner(args.num_trials, args.max_parallel)
    runner.run()


if __name__ == "__main__":
    main() 