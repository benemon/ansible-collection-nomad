#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_node_pool_info
short_description: Read Nomad node pools
version_added: 0.1.0
description:
  - Return one node pool by name, or every node pool the token can see.
options:
  name:
    description: Name of a single node pool to return. A node pool that does not exist returns an empty list.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every node pool
  benemon.nomad.nomad_node_pool_info:
  register: result

- name: Read one node pool
  benemon.nomad.nomad_node_pool_info:
    name: gpu
  register: result
"""

RETURN = r"""
node_pools:
  description: Node pools as the Nomad API returns them, with the API's field names.
  returned: always
  type: list
  elements: dict
  sample:
    - Name: default
      Description: Node pool for nodes that do not specify a pool
      NodeIdentityTTL: 24h0m0s
      CreateIndex: 1
      ModifyIndex: 1
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors, read_or_none


def main():
    module = AnsibleModule(argument_spec=dict(NOMAD_ARGUMENT_SPEC, name=dict(type="str")), supports_check_mode=True)
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        if name:
            pool = read_or_none(lambda: client.node_pools.info(name))
            pools = [pool] if pool else []
        else:
            pools = client.node_pools.list()[0]
    module.exit_json(changed=False, node_pools=[p.to_json() for p in pools])


if __name__ == "__main__":
    main()
