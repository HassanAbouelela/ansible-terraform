"""Generate an ansible in-memory inventory from a terraform state file."""

import json
from collections import defaultdict
from pathlib import Path

from ansible.errors import AnsiblePluginError
from ansible.inventory.data import InventoryData
from ansible.module_utils.common.text.converters import to_native
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.inventory import BaseInventoryPlugin


class InventoryModule(BaseInventoryPlugin):
    """Ansible plugin to dynamically load terraform hosts."""

    NAME = "ansible-terraform"

    def verify_file(self, path: str) -> bool:
        """Check if an inventory file should be managed by our plugin."""
        if super().verify_file(path):
            if path.endswith(("tf.yml", "tf.yaml")):
                return True
        return False

    @staticmethod
    def get_tf_state() -> dict:
        """Locate and read the correct terraform state file."""
        # We can just use the terraform show command to get the active terraform state, however,
        # there is a flat, long startup delay to run any terraform command, so this removes some overhead
        env = Path.cwd() / ".terraform" / "environment"
        state_file = Path.cwd() / "terraform.tfstate"
        env_name = None

        if env.exists():
            # We might be in a workspace, check the environment file
            env_name = env.read_text("utf-8")
            if env_name != "default":
                state_file = Path.cwd() / "terraform.tfstate.d" / env_name / "terraform.tfstate"

        # The tfstate does not exist where we expect it
        if not state_file.exists():
            env_string = f" for workspace {env_name}" if env_name else ""
            path = state_file.absolute().as_posix()
            raise AnsiblePluginError(f"Could not locate the terraform state file{env_string}. Expected at: {path}")

        try:
            return json.loads(state_file.read_text("utf-8"))
        except Exception as e:
            raise AnsiblePluginError("Failed to load the state file due to:\n" + to_native(e))

    def parse(self, inventory: InventoryData, loader: DataLoader, path, cache=False) -> None:
        """Read the terraform state, and load the data."""
        # call base method to ensure properties are available for use with other helper methods
        super().parse(inventory, loader, path, cache)
        resources = self.get_tf_state()["resources"]

        delayed = defaultdict(list)

        for resource in resources:
            if resource.get("provider", "") != 'provider["registry.terraform.io/ansible/ansible"]':
                continue

            for instance in resource["instances"]:
                data = instance["attributes"]
                name = data["name"]

                if resource["type"] == "ansible_group":
                    group = inventory.add_group(name)

                    # Group child registration is delayed, as we need to automatically create the subgroups
                    # but can't differentiate between them and hosts
                    if data["children"] is not None:
                        for child in data["children"]:
                            delayed[group].append(child)

                elif resource["type"] == "ansible_host":
                    host = inventory.add_host(name)
                    if data["groups"] is not None:
                        for group in data["groups"]:
                            group_name = inventory.add_group(group)

                            if host in inventory.get_groups_dict():
                                raise AnsiblePluginError(f"Found conflict between group name and host name: {host}")

                            inventory.add_child(group_name, host)

                else:
                    continue

                if data["variables"] is not None:
                    for var_name, value in data["variables"].items():
                        inventory.set_variable(name, var_name, value)

        # Handle registration for delayed groups. Anything that hasn't registered as a host by now must be a group
        for group, children in delayed.items():
            for child in children:
                if child not in inventory.hosts and child not in inventory.get_groups_dict():
                    inventory.add_group(child)

                inventory.add_child(group, child)
