# PostgreSQL Database
locals {
  sku_name = {
    dev  = "B_Standard_B8ms"
    test = "GP_Standard_D16s_v3"
    prod = "GP_Standard_D64s_v3"
  }[var.environment]

  storage_mb = {
    dev  = 32768  # 32 GiB
    test = 131072 # 128 GiB
    prod = 262144 # 256 GiB
  }[var.environment]
}

locals {
  db_login = {
    dev  = "b3yonddev"
    test = "b3yondtest"
    prod = "b3yondprod"
  }[var.environment]
}

resource "random_password" "db_password" {
  length  = 16
  special = false
}

resource "random_pet" "db_name" {
  prefix = "b3yond-postgres-${var.environment}"
}

resource "azurerm_postgresql_flexible_server" "db" {
  name                = random_pet.db_name.id
  resource_group_name = var.resource_group_name
  location            = var.location

  administrator_login    = local.db_login
  administrator_password = random_password.db_password.result

  sku_name   = local.sku_name
  version    = "16"
  storage_mb = local.storage_mb

  lifecycle {
    ignore_changes = [
      zone
    ]
  }
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "db" {
  name             = "AllowAll"
  server_id        = azurerm_postgresql_flexible_server.db.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "255.255.255.255"
}

resource "azurerm_postgresql_flexible_server_database" "db" {
  name      = "b3yond-db-${var.environment}"
  server_id = azurerm_postgresql_flexible_server.db.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

resource "azurerm_postgresql_flexible_server_database" "litellm_db" {
  name      = "litellm-db-${var.environment}"
  server_id = azurerm_postgresql_flexible_server.db.id
  collation = "en_US.utf8"
  charset   = "UTF8"
}
