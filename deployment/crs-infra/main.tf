resource "random_pet" "rg_name" {
  prefix = "crs-full-${var.environment}-${var.creator}"
}

resource "azurerm_resource_group" "this" {
  name     = random_pet.rg_name.id
  location = var.location
  tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    CreatedBy   = var.creator
    CreatedOn   = formatdate("YYYY-MM-DD", timestamp())
  }
}

# Database
module "database" {
  source              = "./modules/database"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  environment         = var.environment
}

# Kubernetes
module "k8s" {
  source              = "./modules/k8s"
  resource_group_id   = azurerm_resource_group.this.id
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  environment         = var.environment
}

