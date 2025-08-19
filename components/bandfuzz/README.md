# BandFuzz

[![Go version](https://img.shields.io/badge/go-1.23%2B-blue)]
[![License](https://img.shields.io/badge/license-MIT-blue)]

**BandFuzz** is a collaborative fuzzing framework for large-scale parallel
fuzzing campaigns. It dynamically schedules fuzzing strategies using
reinforcement learning, enabling adaptive and efficient fuzzing of real-world
targets.

## Features

- Dynamic scheduling of fuzzing strategies using reinforcement learning
- Orchestration of large-scale parallel fuzzing campaigns
- Support for real-world targets (e.g., Google OSS-Fuzz)
- Integrations: PostgreSQL, RabbitMQ, Redis, OpenTelemetry
- Docker and Docker Compose support

## Project History

- **2022**: Project initiated at Northwestern University
- **2023**: First place at SBFT Fuzzing Competition (ICSE 2023)
- **2024**: Optimizations for DARPA AIxCC competition
- **2025**: Refinements for AIxCC finals; production-ready framework

## Getting Started

### Prerequisites

- Go 1.23 or later
- Make
- Docker & Docker Compose (optional)
- PostgreSQL, RabbitMQ, Redis (if not using Docker)

### Installation

```bash
cd BandFuzz
make
deps make build
```

## Usage

### Command-Line

```bash
./bin/b3fuzz
```

Compile targets:

```bash
./bin/b3compile
```

### Docker Compose

```bash
docker-compose up --build
docker-compose down
```

## Contributing

Contributions are welcome! Please open issues and submit pull requests. Ensure
code is formatted (`go fmt`), add tests for new features, and update
documentation.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file
for details.

## Citation

If you use BandFuzz in your research, please cite:

```bibtex
@inproceedings{10.1145/3643659.3648563,
author = {Shi, Wenxuan and Li, Hongwei and Yu, Jiahao and Guo, Wenbo and Xing, Xinyu},
title = {BandFuzz: A Practical Framework for Collaborative Fuzzing with Reinforcement Learning},
year = {2024},
isbn = {9798400705625},
publisher = {Association for Computing Machinery},
address = {New York, NY, USA},
url = {https://doi.org/10.1145/3643659.3648563},
doi = {10.1145/3643659.3648563},
abstract = {In recent years, the technique of collaborative fuzzing has gained prominence as an efficient method for identifying software vulnerabilities. This paper introduces BandFuzz, a distinctive collaborative fuzzing framework designed to intelligently coordinate the use of multiple fuzzers. Unlike previous tools, our approach employs reinforcement learning to enhance both the efficiency and effectiveness of fuzz testing.},
booktitle = {Proceedings of the 17th ACM/IEEE International Workshop on Search-Based and Fuzz Testing},
pages = {55–56},
numpages = {2},
location = {Lisbon, Portugal},
series = {SBFT '24}
}
```

## Contact

Maintainers:

- Wenxuan Shi (<wenxuan.shi@northwestern.edu>)
