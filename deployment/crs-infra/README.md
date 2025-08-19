# CRS Azure Infrastructure

This repository contains the Terraform configurations for CRS Azure infrastructure.

The infrastructure is managed using a modular approach with separate configurations for different environments (dev, test, prod).

## Prerequisites

- Terraform >= 1.0.0
- Azure CLI
- Bash shell
- Azure subscription with appropriate permissions

## Configuration

1. Each environment (dev, test, prod) has its own:
   - Variable definitions file (`*.tfvars`)
   - Backend configuration (`backend.conf`)

2. Shared variables that apply to all environments are defined in `shared.auto.tfvars`

## Usage

The deployment script `deploy.sh` provides a convenient way to manage infrastructure deployments:

```bash
# Show help and available options
./deploy.sh --help

# Plan changes for dev environment (preview only)
./deploy.sh dev --plan-only

# Apply changes to dev environment (with confirmation)
./deploy.sh dev

# Apply changes to prod environment without confirmation
./deploy.sh prod --auto-apply
```

### Command Line Options

- `-p, --plan-only`: Only show the terraform plan without applying
- `-a, --auto-apply`: Apply terraform changes without confirmation
- `-h, --help`: Show help message

### Environment Setup

Before deploying, ensure you have:

1. Logged in to Azure CLI:

   ```bash
   az login
   ```

2. Proper backend configuration in `environment/<env>/backend.conf`

3. Environment-specific variables in `environment/<env>/<env>.tfvars`
