terraform {
  required_providers {
    azapi = {
      source = "azure/azapi"
    }
    azurerm = {
      source = "hashicorp/azurerm"
    }
    cloudflare = {
      source = "cloudflare/cloudflare"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "cloudflare" {
}
