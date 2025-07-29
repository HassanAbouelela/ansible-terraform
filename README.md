# Ansible Terraform Inventory Plugin

A simple inventory plugin to integrate terraform-generated hosts with ansible playbook.
This uses the resources (hosts/groups) defined using
the [Ansible terraform provider](https://registry.terraform.io/providers/ansible/ansible/latest/docs).

Unlike the Ansible provider, this plugin is able to use dynamically created terraform resources to define
dynamic in-memory inventories, allowing you to use your terraform as your inventory.

The plugin is fully compatible with the [
`ansible_group`](https://registry.terraform.io/providers/ansible/ansible/latest/docs/resources/group)
and [`ansible_host`](https://registry.terraform.io/providers/ansible/ansible/latest/docs/resources/host) resource types,
including complete resolution of host-group connections, and passing variables through.

## Usage

Download the content of the src directory (`ansible-terraform.py`, `inventory.tf.yml`) and place them
somewhere in your ansible path, or your current project.

1. Add the plugin path to the ansible config (`ansible.cfg`):

```ini
[defaults]
inventory_plugins = /path/to/plugin
```

2. Define your Terraform resources:

```hcl
terraform {
  required_providers {
    ansible = {
      source  = "ansible/ansible"
      version = "1.3.0"
    }

    ...
  }
}

resource "cloud_virtual_machine" "echo_server" {
  ...
}

resource "ansible_host" "echo" {
  depends_on = [cloud_virtual_machine.echo_server]
  name = "echo" # Host name in ansible playbooks
  groups = ["production"] # Optional list of ansible groups

  # Set the desired access credentials, and any custom variables.
  # https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html#connecting-to-hosts-behavioral-inventory-parameters
  variables = {
    ansible_host     = cloud_virtual_machine.echo_server.public_ip_address
    ansible_user     = cloud_virtual_machine.echo_server.username
    ansible_password = cloud_virtual_machine.echo_server.password
  }
}

# Use the ansible "all" group to define a variable for all hosts
resource "ansible_group" "all" {
  name = "all"
  variables = {
    VERSION = "1.0"
  }
}
```

3. Run your playbook in terraform

```hcl
# This is just an example of one possible way to do it, using a local-exec provisioner
resource "null_resource" "configure-server" {
  depends_on = [ansible_host.echo_server]

  provisioner "local-exec" {
    command = "ansible-playbook ${path.module}/ansible/playbooks/echo.yml"
    environment = {
      "ANSIBLE_CONFIG" = "${path.module}/ansible/ansible.cfg"
    }
  }
}
```
