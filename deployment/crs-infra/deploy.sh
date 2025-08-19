#!/bin/bash

# Function to display usage
usage() {
    echo "Usage: $0 <environment> [options]"
    echo "Options:"
    echo "  -p, --plan-only    Only show the terraform plan without applying"
    echo "  -a, --auto-apply   Apply terraform changes without confirmation"
    echo "  -d, --destroy      Destroy the infrastructure"
    echo "  -h, --help         Show this help message"
    exit 1
}

# Default values
PLAN_ONLY=false
AUTO_APPLY=false
DESTROY=false

# check if .rc exists, if not, exit. if so, source it.
if [ -f ".rc" ]; then
    source ".rc"
else
    echo "Error: .rc file not found."
    exit 1
fi

# Parse command line arguments
POSITIONAL_ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
    -p | --plan-only)
        PLAN_ONLY=true
        shift
        ;;
    -a | --auto-apply)
        AUTO_APPLY=true
        shift
        ;;
    -d | --destroy)
        DESTROY=true
        shift
        ;;
    -h | --help)
        usage
        ;;
    *)
        POSITIONAL_ARGS+=("$1")
        shift
        ;;
    esac
done

# Restore positional arguments
set -- "${POSITIONAL_ARGS[@]}"

# Check if environment is provided
if [ -z "$1" ]; then
    usage
fi

ENVIRONMENT=$1
TFVARS_FILE="environment/${ENVIRONMENT}/${ENVIRONMENT}.tfvars"
BACKEND_FILE="environment/${ENVIRONMENT}/backend.conf"

# Check if backend.conf exists
if [ ! -f "$BACKEND_FILE" ]; then
    echo "Error: $BACKEND_FILE not found."
    exit 1
fi

# Initialize Terraform
terraform init -backend-config=$BACKEND_FILE

# Select or create the workspace
terraform workspace select -or-create $ENVIRONMENT

# Prepare the plan command
if [ -f "$TFVARS_FILE" ]; then
    PLAN_CMD="terraform plan -var-file=\"$TFVARS_FILE\""
else
    echo "Warning: $TFVARS_FILE not found. Proceeding without it."
    PLAN_CMD="terraform plan"
fi

# Add destroy flag if destroy mode is enabled
if [ "$DESTROY" = true ]; then
    PLAN_CMD="$PLAN_CMD -destroy"
fi

# Add -out flag if we're not in plan-only mode
if [ "$PLAN_ONLY" = false ]; then
    PLAN_CMD="$PLAN_CMD -out=tfplan"
fi

# Execute the plan
eval $PLAN_CMD

# Exit if plan-only mode
if [ "$PLAN_ONLY" = true ]; then
    exit 0
fi

# Apply the changes if not in plan-only mode
if [ "$AUTO_APPLY" = true ]; then
    terraform apply -auto-approve tfplan
else
    terraform apply tfplan
fi

# Clean up the plan file
rm -f tfplan
