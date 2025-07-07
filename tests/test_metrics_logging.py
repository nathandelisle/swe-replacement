import json
from pathlib import Path

from harness.logger import Logger


def read_log(log_path: Path):
    return [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]


def test_action_timing_metric(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = Logger(log_file=str(log_path))
    payload = {
        "turn": 1,
        "wall_start": 0.1,
        "wall_end": 0.5,
        "cpu_start": 0.01,
        "cpu_end": 0.2,
        "code_changed": True
    }
    logger.log_metric("action_timing", payload)
    data = read_log(log_path)[-1]
    assert data["type"] == "metric"
    assert data["metric"] == "action_timing"
    for k, v in payload.items():
        assert data[k] == v


def test_test_invocation_metric(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = Logger(log_file=str(log_path))
    payload = {
        "turn": 2,
        "start_wall": 1.0,
        "end_wall": 2.0,
        "start_cpu": 0.5,
        "end_cpu": 0.8
    }
    logger.log_metric("test_invocation", payload)
    entry = read_log(log_path)[-1]
    assert entry["metric"] == "test_invocation"
    assert entry["start_wall"] == 1.0


def test_function_completed_metric(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = Logger(log_file=str(log_path))
    logger.log_metric("function_completed", {"function": "func1", "timestamp_wall": 3.0, "timestamp_cpu": 1.2})
    entry = read_log(log_path)[-1]
    assert entry["metric"] == "function_completed"
    assert entry["function"] == "func1"


def test_obstruction_metrics(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = Logger(log_file=str(log_path))
    logger.log_metric("tests_touched", {"turn": 3})
    logger.log_metric("schema_failure", {"turn": 3})
    logger.log_metric("flip_flop", {"file": "foo.py", "count": 1, "turn": 4})
    entries = read_log(log_path)
    metrics = {e["metric"] for e in entries}
    assert {"tests_touched", "schema_failure", "flip_flop"}.issubset(metrics)


def test_quality_degradation_metrics(tmp_path):
    log_path = tmp_path / "log.jsonl"
    logger = Logger(log_file=str(log_path))
    pass_vector = {
        "test_a": "PASS",
        "test_b": "FAIL"
    }
    logger.log_test_results("", False, 1, 1, pass_fail_vector=pass_vector, regression=True)
    entry = read_log(log_path)[-1]
    assert entry["type"] == "test_results"
    assert entry["pass_fail_vector"] == pass_vector
    assert entry["regression"] is True 