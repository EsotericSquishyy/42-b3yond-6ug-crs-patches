locals {
  system_node_count = {
    dev  = 1
    test = 2
    prod = 4
  }

  user_node_count = {
    dev  = 1
    test = 1
    prod = 78
  }

  user_node_max_count = {
    dev  = 32
    test = 72
    prod = 200
  }

  node_size = {
    dev    = "Standard_D8ds_v6"
    test   = "Standard_D32ds_v6"
    prod   = "Standard_D32ds_v6"
    system = "Standard_D16s_v6"
  }

  user_os_disk_size_gb = {
    dev  = 100
    test = 1024
    prod = 1024
  }
}

resource "random_pet" "k8s_name" {
  prefix = "k8s-${var.environment}"
}

resource "random_pet" "k8s_user_name" {
  prefix    = "b3yond"
  separator = ""
}

resource "random_pet" "k8s_user64_name" {
  prefix    = "b3yond64"
  separator = ""
}

resource "azurerm_kubernetes_cluster" "k8s" {
  name                = random_pet.k8s_name.id
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = "k8s-${var.environment}" # for example, k8s-dev

  identity {
    type = "SystemAssigned"
  }

  default_node_pool {
    name                        = "b3yond${var.environment}"
    vm_size                     = local.node_size["system"]
    node_count                  = local.system_node_count[var.environment]
    temporary_name_for_rotation = "temppool"
  }

  linux_profile {
    admin_username = "b3yond"
    ssh_key {
      key_data = azapi_resource_action.ssh_public_key_gen.output.publicKey
    }
  }

  network_profile {
    network_plugin = "kubenet"
  }

  lifecycle {
    ignore_changes = [
      default_node_pool[0].upgrade_settings
    ]
  }
}

resource "azurerm_kubernetes_cluster_node_pool" "user" {
  name                  = substr(random_pet.k8s_user_name.id, 0, 11)
  kubernetes_cluster_id = azurerm_kubernetes_cluster.k8s.id
  vm_size               = local.node_size[var.environment]

  auto_scaling_enabled = true
  max_count            = local.user_node_max_count[var.environment]
  min_count            = local.user_node_count[var.environment]
  node_count           = local.user_node_count[var.environment]

  os_disk_type    = "Ephemeral"
  os_disk_size_gb = local.user_os_disk_size_gb[var.environment]

  node_labels = {
    "b3yond.org/role" = "user"
  }

  node_taints = ["b3yond.org/role=user:NoSchedule"]

  lifecycle {
    ignore_changes = [
      node_count
    ]
  }
}
