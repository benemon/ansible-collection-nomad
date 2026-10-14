#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_namespace
short_description: Manage a Nomad namespace
version_added: 0.1.0
description:
  - Create, update or delete a namespace.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
options:
  name:
    description: Name of the namespace.
    type: str
    required: true
  description:
    description: Description of the namespace.
    type: str
  quota:
    description: Name of the quota specification applied to the namespace. Enterprise.
    type: str
  meta:
    description: Arbitrary key-value metadata.
    type: dict
  capabilities:
    description: Task drivers and network modes allowed or denied for jobs in the namespace.
    type: dict
    suboptions:
      enabled_task_drivers:
        description: Task drivers jobs may use. All others are denied.
        type: list
        elements: str
      disabled_task_drivers:
        description: Task drivers jobs may not use.
        type: list
        elements: str
      enabled_network_modes:
        description: Network modes groups may use. All others are denied.
        type: list
        elements: str
      disabled_network_modes:
        description: Network modes groups may not use.
        type: list
        elements: str
  node_pool_configuration:
    description: Node pools jobs in the namespace may use. Enterprise.
    type: dict
    suboptions:
      default:
        description: Node pool used when a job does not name one.
        type: str
      allowed:
        description: Node pools jobs may use. Mutually exclusive with O(node_pool_configuration.denied).
        type: list
        elements: str
      denied:
        description: Node pools jobs may not use.
        type: list
        elements: str
  vault_configuration:
    description: Vault clusters jobs in the namespace may use. Enterprise.
    type: dict
    suboptions:
      default:
        description: Vault cluster used when a job does not name one.
        type: str
      allowed:
        description: Vault clusters jobs may use. Mutually exclusive with O(vault_configuration.denied).
        type: list
        elements: str
      denied:
        description: Vault clusters jobs may not use.
        type: list
        elements: str
  consul_configuration:
    description: Consul clusters jobs in the namespace may use. Enterprise.
    type: dict
    suboptions:
      default:
        description: Consul cluster used when a job does not name one.
        type: str
      allowed:
        description: Consul clusters jobs may use. Mutually exclusive with O(consul_configuration.denied).
        type: list
        elements: str
      denied:
        description: Consul clusters jobs may not use.
        type: list
        elements: str
  state:
    description: Whether the namespace should exist.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Create a namespace restricted to the docker driver
  benemon.nomad.nomad_namespace:
    name: web
    description: Web tier
    capabilities:
      enabled_task_drivers: [docker]

- name: Apply a quota to the namespace (Enterprise)
  benemon.nomad.nomad_namespace:
    name: web
    quota: web-quota

- name: Delete the namespace
  benemon.nomad.nomad_namespace:
    name: web
    state: absent
"""

RETURN = r"""
namespace:
  description: The namespace as the Nomad API returns it, with the API's field names.
  returned: when O(state=present)
  type: dict
  sample:
    Name: web
    Description: Web tier
    Quota: ""
    Capabilities:
      EnabledTaskDrivers: [docker]
    CreateIndex: 12
    ModifyIndex: 12
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    NOMAD_ARGUMENT_SPEC,
    apply_options,
    differs,
    nomad_client,
    nomad_errors,
    read_or_none,
)

try:
    from nomadpy import Namespace
except ImportError:
    pass

_SELECTION = dict(
    default=dict(type="str"),
    allowed=dict(type="list", elements="str"),
    denied=dict(type="list", elements="str"),
)

RESOURCE_SPEC = dict(
    name=dict(type="str", required=True),
    description=dict(type="str"),
    quota=dict(type="str"),
    meta=dict(type="dict"),
    capabilities=dict(
        type="dict",
        options=dict(
            enabled_task_drivers=dict(type="list", elements="str"),
            disabled_task_drivers=dict(type="list", elements="str"),
            enabled_network_modes=dict(type="list", elements="str"),
            disabled_network_modes=dict(type="list", elements="str"),
        ),
    ),
    node_pool_configuration=dict(type="dict", options=_SELECTION),
    vault_configuration=dict(type="dict", options=_SELECTION),
    consul_configuration=dict(type="dict", options=_SELECTION),
)


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, state=dict(type="str", choices=["present", "absent"], default="present"), **RESOURCE_SPEC),
        supports_check_mode=True,
    )
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        current = read_or_none(lambda: client.namespaces.info(name))
        before = current.to_json() if current else {}

        if module.params["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.namespaces.delete(name)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        wanted = apply_options(current, Namespace, {k: module.params[k] for k in RESOURCE_SPEC})
        changed = current is None or differs(current, wanted)
        if changed and not module.check_mode:
            client.namespaces.register(wanted)
            wanted = client.namespaces.info(name)[0]
        module.exit_json(changed=changed, namespace=wanted.to_json(), diff=dict(before=before, after=wanted.to_json()))


if __name__ == "__main__":
    main()
