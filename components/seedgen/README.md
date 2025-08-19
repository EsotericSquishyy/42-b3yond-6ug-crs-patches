# SeedGen2 (Project Sunflower)

## Overview

SeedGen2 is a framework designed to generate initial seeds for OSS-Fuzz, enhancing the effectiveness of fuzzing. By leveraging the capabilities of large language models, SeedGen2 can create valid seeds and improve them using harness and coverage information.

## Agent

SeedGen2 utilizes a variety of agents to generate seeds by analyzing both static and dynamic project information. This includes:

- Project harnesses code
- Dictionaries (string literals within the program)
- Documentation
- Source code
- Dynamic code coverage
- Call relationships
- Predicates

These elements collectively aid in the seed generation process.

SeedGen2 is built to be flexible and extensible, enabling the integration of additional agents to further enhance its functionality.

## Architecture

SeedGen2 consists of two main components:
1. **Lightweight Runtime `SeedD`**: Runs the fuzzing harness within an OSS-Fuzz Docker container, collecting dynamic information.
2. **LLM Agents**: Capable of self-reflection and guided by a state machine to ensure tasks are managed effectively and LLM errors are preemptively fixed.

## Getting Started

### Prerequisites
- Docker
- Python 3.x

## Usage

1. **Build the Tool**
   ```shell
   make
   ```

2. **Run the Script**
   ```shell
   python3 oss-fuzz.py <project_name> <harness_name>
   ```
   - **Project Name**: Directory name in `oss-fuzz/projects/`, e.g., `libxml2`.
   - **Harness Name**: Executable file in the `/out` folder after building the project.

### Example
To run SeedGen2 for the `libxml2` project with the `xml` harness:
```shell
python3 oss-fuzz.py libxml2 xml
```

## Author

- [Wenxuan Shi](mailto:wenxuan.shi@northwestern.edu)

## Contributing

Contributions are welcome! Please open an issue or submit a pull request if you have any improvements or suggestions.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.