# Re-export outputs from k8s module

output "key_data" {
  value = module.k8s.key_data
}

output "client_certificate" {
  value     = module.k8s.client_certificate
  sensitive = true
}

output "client_key" {
  value     = module.k8s.client_key
  sensitive = true
}

output "cluster_ca_certificate" {
  value     = module.k8s.cluster_ca_certificate
  sensitive = true
}

output "cluster_password" {
  value     = module.k8s.cluster_password
  sensitive = true
}

output "cluster_username" {
  value     = module.k8s.cluster_username
  sensitive = true
}

output "host" {
  value     = module.k8s.host
  sensitive = true
}

output "kube_config" {
  value     = module.k8s.kube_config
  sensitive = true
}

output "database_connection_string" {
  value     = module.database.database_connection_string
  sensitive = true
}

output "litellm_connection_string" {
  value     = module.database.litellm_connection_string
  sensitive = true
}

