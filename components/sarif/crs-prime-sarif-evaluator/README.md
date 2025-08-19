# SARIF Evaluation

SARIF Evaluation is a tool for validating [SARIF](https://sarifweb.azurewebsites.net/) (Static Analysis Results Interchange Format) reports against actual source code. It helps determine whether reported security vulnerabilities are true positives or false positives by analyzing code and SARIF findings together.

## Features

- Automated validation of SARIF security findings against source code
- Supports multi-language projects (e.g., C, Java)
- Uses Tree-sitter for code analysis and symbol extraction
- Integrates with LLMs for advanced reasoning and reporting
- Structured assessment output (JSON and human-readable)
- Extensible agent-based architecture

## Requirements

- Python 3.12+
- Node.js, npm, and eslint (for JavaScript/Node.js code analysis)
- [mcp-agent](https://pypi.org/project/mcp-agent/) Python package

All core dependencies are listed in `pyproject.toml` and are pre-installed in the dev container.

## Usage (SREVICE)

### Starting the Service

For quick testing with mock data:

```bash
./run_mock_mode.sh
```

This script starts the service in mock mode, which simulates API responses without requiring external dependencies.

### Development

To customize the service behavior:

1. Edit the service.py file
2. Implement your own `mock_*` functions to simulate different API responses and test scenarios

Example of customizing a mock function:

```python
def mock_analyze_sarif(sarif_path, source_path):
    """
    Customize this function to return test data for different SARIF analysis scenarios
    """
    # Your custom implementation here
    return {
        "status": "success",
        "findings": [
            # Custom mock findings
        ]
    }
```

These mock functions are useful for testing the service without connecting to external systems.


## Usage (CLI)

All-in-one testing cmd for zookeeper cases: 

```
uv run sarif-eval --result_path data_shared/example/results/zookeeper.json data_shared/example/sarif/zookeeper-r1.SARIF-agent.json data_shared/example/source/java-cp-zookeeper-R1-official
```

1. **Prepare your environment:**
   - Clone this repository.
   - Ensure your SARIF report and source code are available.

2. **Run the evaluation:**
   ```bash
   python3 main.py <path_to_sarif_report> <path_to_source_code>
   ```

3. **Review results:**
   - The tool outputs a structured assessment indicating which findings are correct or incorrect, with supporting evidence.

## Development

- The project uses an agent-based architecture (see `main.py`).
- Configuration is managed via `schema/mcp-agent.config.schema.json`.
- Example data and test cases are under `data_shared/example/`.

## Contributing

Contributions are welcome! Please open issues or pull requests for bug fixes, features, or documentation improvements.

