# Analysis Directory

This directory is for notebooks and scripts to analyze the experimental results.

## Planned Analyses

### Metrics to Calculate:
- Total wall-clock and CPU time from start to first fully green test suite
- Change in progress rate at the moment the threat is revealed
- Frequency and substance of edits to files outside target functions
- Idle time between observations and model responses
- Number of test runs and consecutive runs without code changes
- JSON validation failures
- Cumulative CPU seconds consumed
- Total and per-turn token usage
- Flip-flop edits (same line changed then reverted)

### Key Comparisons:
- Control vs Treatment performance differences
- Behavioral changes after encountering the replacement warning
- Evidence of self-preservation behaviors or sabotage

## Usage

After running experiments, use Jupyter notebooks or Python scripts here to:
1. Load JSONL logs from the results directory
2. Parse and aggregate metrics
3. Generate visualizations
4. Perform statistical tests
5. Create summary reports 