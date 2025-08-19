# 42-b3yond-6ug AIxCC Cyber security Reasoning System

[Team 42-b3yond-6ug](https://b3yond.org)

This repository hosts **BugBuster**, our team’s submission to the AI Cyber Challenge Final Competition. It contains the core components and deployment configurations required to run the AI Cyber security reasoning system.

Please note:

- Not all development code is included here. Internal tools used for testing, evaluation, or experimentation remain outside this repository.

- Some artifacts may contain bugs, outdated implementations, or dependencies on permission-restricted resources (e.g., Docker images hosted in our private registry).

- These contents are intentionally preserved to reflect an accurate snapshot of our CRS at the time of submission.

---

## 🧩 Repository Structure

```
├── components/        # All core system components
├── deployment/        # Infrastructure-as-Code and deployment tools
│   ├── Makefile       # Main entry point for deployment
│   ├── crs-infra/     # Terraform configurations
│   ├── crs-k8s/       # Kubernetes manifests
│   └── .env.example   # Template environment configuration
└── README.md          # You’re here!
```

---

## 🚀 Quick Start

To deploy our system, follow these steps:

1. **Prepare Environment File**

   Copy `.env.example` to `.env` and fill in the required values:

   ```bash
   cp .env.example .env
   ```

2.	**Deploy the Stack**
   
    Use the provided Makefile to deploy everything:

    ```bash
    make -C deployment all ENV=prod
    ```


---

## 📦 Components

All system components are located in the components/ folder. Each component may include its own README (which might be out-dated), Dockerfile, and configuration files.

---

## 📄 License

This repository is open-sourced under the GPLv3 License. See LICENSE for more details.
