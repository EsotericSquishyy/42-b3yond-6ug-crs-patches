locals {
  database_connection_prefix = "postgresql://${azurerm_postgresql_flexible_server.db.administrator_login}:${urlencode(random_password.db_password.result)}@${azurerm_postgresql_flexible_server.db.fqdn}:5432/"
}

output "database_connection_string" {
  value = "${local.database_connection_prefix}${azurerm_postgresql_flexible_server_database.db.name}"
}

output "litellm_connection_string" {
  value = "${local.database_connection_prefix}${azurerm_postgresql_flexible_server_database.litellm_db.name}"
}

output "database_username" {
  value = azurerm_postgresql_flexible_server.db.administrator_login
}

output "database_password" {
  value     = random_password.db_password.result
  sensitive = true
}
