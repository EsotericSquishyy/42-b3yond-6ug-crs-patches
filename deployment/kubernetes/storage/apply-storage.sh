#!/bin/bash

# Exit on error
set -e

# Apply the configuration
kubectl apply -f storage.yaml

echo "Storage configuration applied successfully"

