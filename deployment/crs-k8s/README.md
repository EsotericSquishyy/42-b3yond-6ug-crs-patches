# CRS-k8s

Kubernetes Helm chart for the AI Cybersecurity Reasoning System.

## Usage

```bash
cd b3yond-crs

# Generate the secret-values.yaml file (if already exists, don't overwrite it!)
# ../scripts/generate-secrets.sh

# Update the dependencies
helm dependency update

# Deploy the Helm chart
helm install dev -f secret-values.yaml .

# Destory our service
helm uninstall dev
```
