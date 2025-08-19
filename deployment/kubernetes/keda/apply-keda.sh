#!/bin/bash

helm repo add kedacore https://kedacore.github.io/charts  
helm repo update

echo -e "Installing KEDA"

helm upgrade \
    --install \
    keda \
    kedacore/keda \
    --namespace keda \
    --create-namespace \
    --wait

echo -e "KEDA installed successfully"

# Get started by deploying Scaled Objects to your cluster:
#     - Information about Scaled Objects : https://keda.sh/docs/latest/concepts/
#     - Samples: https://github.com/kedacore/samples

# Get information about the deployed ScaledObjects:
#   kubectl get scaledobject [--namespace <namespace>]

# Get details about a deployed ScaledObject:
#   kubectl describe scaledobject <scaled-object-name> [--namespace <namespace>]

# Get information about the deployed ScaledObjects:
#   kubectl get triggerauthentication [--namespace <namespace>]

# Get details about a deployed ScaledObject:
#   kubectl describe triggerauthentication <trigger-authentication-name> [--namespace <namespace>]

# Get an overview of the Horizontal Pod Autoscalers (HPA) that KEDA is using behind the scenes:
#   kubectl get hpa [--all-namespaces] [--namespace <namespace>]

# Learn more about KEDA:
# - Documentation: https://keda.sh/
# - Support: https://keda.sh/support/
# - File an issue: https://github.com/kedacore/keda/issues/new/choose