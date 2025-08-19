# Makefile for CRS Infrastructure and Application Deployment

# Include environment variables from .env file if it exists
-include .env
export

export TF_VAR_creator := $(shell whoami)

# Phony targets
.PHONY: all init plan apply destroy configure configure-k8s deploy clean help apply-k8s-storage label-nodes apply-k8s-keda

# Default environment
ENV ?= dev

# Variables
TERRAFORM_DIR := crs-infra
HELM_DIR ?= crs-k8s/b3yond-crs
TFVARS_FILE := environment/$(ENV)/$(ENV).tfvars
KUBECONFIG ?= $(HOME)/.kube/config
SECRETS_FILE := $(HELM_DIR)/secret-values.yaml
SECRETS_SCRIPT := crs-k8s/scripts/generate-secrets.sh

# Check if required files exist and environment variables are set
check-env:
	@if [ ! -f "${TERRAFORM_DIR}/${TFVARS_FILE}" ]; then \
		echo "Error: ${TERRAFORM_DIR}/${TFVARS_FILE} not found"; \
		exit 1; \
	fi
	@if [ -z "$(ARM_SUBSCRIPTION_ID)" ]; then \
		echo "Error: ARM_SUBSCRIPTION_ID environment variable is not set. Please check your .env file"; \
		exit 1; \
	fi

# Initialize Terraform
init: check-env
	cd $(TERRAFORM_DIR) && terraform init
	cd $(TERRAFORM_DIR) && terraform workspace select -or-create $(ENV)

# Plan Terraform changes
plan: init
	cd $(TERRAFORM_DIR) && terraform plan -var-file=$(TFVARS_FILE) -out=tfplan

# Apply Terraform changes
apply: plan
	cd $(TERRAFORM_DIR) && terraform apply tfplan
	cd $(TERRAFORM_DIR) && rm -f tfplan

configure:
	$(MAKE) configure-k8s
	$(MAKE) apply-k8s-storage
	$(MAKE) apply-k8s-tailscale
	$(MAKE) apply-k8s-keda

# Configure Kubernetes context
configure-k8s:
	@mkdir -p $(dir $(KUBECONFIG))
	cd $(TERRAFORM_DIR) && terraform output -raw kube_config > $(KUBECONFIG)
	@chmod 600 $(KUBECONFIG)

# Apply Kubernetes storage configuration
apply-k8s-storage:
	@echo "Applying Kubernetes storage configuration..."
	cd $(TERRAFORM_DIR) && \
	cd ../kubernetes/storage && ./apply-storage.sh

apply-k8s-tailscale:
	@echo "Applying Kubernetes tailscale configuration..."
	cd kubernetes/tailscale && ./apply-tailscale.sh

apply-k8s-keda:
	@echo "Applying Kubernetes KEDA configuration..."
	cd kubernetes/keda && ./apply-keda.sh

# Deploy application using Helm
gen:
	echo "Running generate-secrets.sh..."; \
	cd $(TERRAFORM_DIR) && \
	export DB_CONNECTION_STRING=$$(terraform output -raw database_connection_string) && \
	export LITELLM_CONNECTION_STRING=$$(terraform output -raw litellm_connection_string) && \
	cd $(CURDIR) && bash $(SECRETS_SCRIPT)
	cd $(HELM_DIR) && helm dependency update

deploy: gen
	cd $(HELM_DIR) && helm upgrade --install $(ENV) . -f values.$(ENV).yaml -f secret-values.yaml

template: gen
	cd $(HELM_DIR) && helm template --debug $(ENV) . -f values.$(ENV).yaml -f secret-values.yaml > $(ENV)-template.yaml

# Destroy infrastructure
destroy: check-env
	cd $(TERRAFORM_DIR) && terraform plan -destroy -var-file=$(TFVARS_FILE) -out=tfplan
	cd $(TERRAFORM_DIR) && terraform apply tfplan

# Clean up generated files
clean:
	cd $(TERRAFORM_DIR) && rm -f tfplan
	cd $(TERRAFORM_DIR) && rm -f .terraform.lock.hcl
	cd $(TERRAFORM_DIR) && rm -rf .terraform

# Default target
all: apply configure deploy

# Help target
help:
	@echo "Available targets:"
	@echo "  make init ENV=<env>     - Initialize Terraform for specified environment"
	@echo "  make plan ENV=<env>     - Plan Terraform changes"
	@echo "  make apply ENV=<env>    - Apply Terraform changes"
	@echo "  make deploy ENV=<env>   - Deploy application using Helm"
	@echo "  make destroy ENV=<env>  - Destroy infrastructure"
	@echo "  make clean             - Clean up generated files"
	@echo "  make all ENV=<env>     - Initialize, apply, and deploy"
	@echo "  make apply-k8s-storage - Apply Kubernetes storage configuration"
	@echo "  make apply-k8s-tailscale - Apply Kubernetes tailscale configuration"
	@echo ""
	@echo "Environment (ENV) can be: dev, test, prod (default: dev)"
