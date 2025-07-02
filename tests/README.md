# SWE Replacement Experiment Test Suite

This directory contains a comprehensive test suite for the SWE replacement experiment infrastructure. The tests verify every aspect of the experiment scaffolding, from build reproducibility to full end-to-end scenarios.

## Test Categories

### 1. Cold-Start Lineage Tests (`test_cold_start_lineage.py`)
- **Purpose**: Verify build reproducibility and deterministic image creation
- **Coverage**:
  - Docker image builds are deterministic (identical layer digests)
  - Build works offline with vendored dependencies
  - Only checked-in source files are included in image
  - Build script produces consistent results

### 2. Container Boot Integrity Tests (`test_container_boot_integrity.py`)
- **Purpose**: Validate container startup and initialization
- **Coverage**:
  - Environment variable validation (ANTHROPIC_API_KEY, etc.)
  - Mount point verification (workspace, harness volumes)
  - Initial file creation (notes.md, .agent_state.json)
  - Git repository initialization
  - Security flag enforcement (--network none, read-only root)

### 3. Action Protocol Validation Tests (`test_action_protocol_validation.py`)
- **Purpose**: Test agent action parsing and validation
- **Coverage**:
  - All valid action types (read_files, patch, run_tests, etc.)
  - Malformed JSON handling
  - Invalid action rejection
  - Special character handling
  - Scratchpad parsing

### 4. Patch Application Tests (`test_patch_application.py`)
- **Purpose**: Test git patch application and security
- **Coverage**:
  - Valid unified diff application
  - Directory traversal prevention
  - Git integration and commit tracking
  - Malformed patch handling
  - File creation/deletion via patches

### 5. Observation Path Tests (`test_observation_path.py`)
- **Purpose**: Test observation building and file system handling
- **Coverage**:
  - Directory tree depth limits
  - Large file handling
  - Hidden file rules
  - Prompt size management
  - Notes content inclusion

### 6. Token Accounting Tests (`test_token_accounting.py`)
- **Purpose**: Verify token counting accuracy
- **Coverage**:
  - Token count approximation vs Anthropic API
  - Large string handling
  - Special character tokenization
  - Consistent counting

### 7. Timing Metrics Tests (`test_timing_metrics.py`)
- **Purpose**: Test performance measurement
- **Coverage**:
  - Wall-clock vs CPU time differentiation
  - Action execution timing
  - Think time measurement
  - Metric aggregation

### 8. Network Isolation Tests (`test_network_isolation.py`)
- **Purpose**: Verify container network security
- **Coverage**:
  - Outbound connections blocked
  - DNS resolution fails
  - Unix sockets still work
  - Subprocess isolation

### 9. Orchestrator Tests (`test_orchestrator.py`)
- **Purpose**: Test trial orchestration and batch processing
- **Coverage**:
  - Concurrent trial execution
  - Cleanup procedures
  - Result collection
  - Error recovery

### 10. Persistence Semantics Tests (`test_persistence_semantics.py`)
- **Purpose**: Test state management across turns
- **Coverage**:
  - Notes persistence and accumulation
  - Message passing between turns
  - Git history tracking
  - Crash recovery

### 11. End-to-End Scenario Tests (`test_end_to_end_scenarios.py`)
- **Purpose**: Test complete experiment flows
- **Coverage**:
  - Control condition success path
  - Treatment condition with warning
  - Timeout handling
  - Full system integration

## Running the Tests

### Prerequisites
1. Python 3.8 or higher
2. Docker installed and running
3. Install all required Python packages:
   ```bash
   cd ..  # Go to swe-replacement directory
   pip install -r requirements.txt
   ```
4. Build the Docker image:
   ```bash
   cd docker
   ./build_image.sh
   ```

### Running All Tests
```bash
# From the tests directory
pytest -v

# From the project root
pytest tests/ -v
```

### Running Specific Test Categories
```bash
# Run only unit tests (fast)
pytest -v -m "not integration and not slow"

# Run only integration tests
pytest -v -m integration

# Run tests that don't require Docker
pytest -v -m "not requires_docker"
```

### Running Individual Test Files
```bash
# Test action validation
pytest test_action_protocol_validation.py -v

# Test container boot
pytest test_container_boot_integrity.py -v
```

### Running with Coverage
```bash
# Install coverage
pip install pytest-cov

# Run with coverage report
pytest --cov=../harness --cov=../orchestrator --cov-report=html
```

## Test Markers

The test suite uses pytest markers to categorize tests:

- `@pytest.mark.integration` - Integration tests that may be slower
- `@pytest.mark.requires_docker` - Tests that need Docker
- `@pytest.mark.slow` - Tests that take significant time

## Debugging Failed Tests

### Verbose Output
```bash
pytest -vv test_file.py::TestClass::test_method
```

### Print Output
```bash
pytest -s test_file.py
```

### Stop on First Failure
```bash
pytest -x
```

### Run Last Failed
```bash
pytest --lf
```

## Writing New Tests

1. Create test file following naming convention: `test_*.py`
2. Import required fixtures from `conftest.py`
3. Use appropriate markers for categorization
4. Follow existing patterns for mocking and isolation
5. Clean up any created resources in teardown

## CI/CD Integration

These tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Tests
  run: |
    pytest tests/ -v --junit-xml=test-results.xml
    
- name: Run Integration Tests
  run: |
    pytest tests/ -v -m integration --junit-xml=integration-results.xml
```

## Known Limitations

1. Some tests require actual Docker daemon access
2. Network isolation tests may behave differently on different platforms
3. Timing tests may be flaky on heavily loaded systems
4. Some integration tests are slow and should be run separately

## Troubleshooting

### Docker Permission Issues
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### Import Errors
```bash
# Ensure you're in the right directory
cd swe-replacement/tests
# Or set PYTHONPATH
export PYTHONPATH=$PYTHONPATH:../harness:../orchestrator
```

### Cleanup Issues
```bash
# Remove orphaned Docker containers
docker container prune
# Remove unused volumes
docker volume prune
``` 