terraform {
  required_providers {
    azapi = {
      source = "azure/azapi"
    }
    azurerm = {
      source = "hashicorp/azurerm"
    }
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
  }
}
