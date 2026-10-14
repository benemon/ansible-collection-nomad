#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_node_info
short_description: Read Nomad client nodes
version_added: 0.1.0
description:
  - Return one node by ID or name, or every node the token can see.
options:
  node_id:
    description: ID of a single node to return. A node that does not exist returns an empty list.
    type: str
  name:
    description: Name of a single node to return. No node with the name returns an empty list; more than one is a failure.
    type: str
  prefix:
    description: Return only the nodes whose ID starts with this prefix.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every node
  benemon.nomad.nomad_node_info:
  register: result

- name: Read one node by name
  benemon.nomad.nomad_node_info:
    name: worker-03
  register: result
"""

RETURN = r"""
nodes:
  description:
    - Nodes as the Nomad API returns them, with the API's field names.
    - With O(node_id) or O(name) the one node is the full document; the list endpoint returns stubs.
  returned: always
  type: list
  elements: dict
  sample:
    - ID: 7f3a9b2c-1d4e-5f6a-8b9c-0d1e2f3a4b5c
      Name: worker-03
      Datacenter: dc1
      NodePool: default
      Status: ready
      SchedulingEligibility: eligible
      Drain: false
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors, read_or_none


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, node_id=dict(type="str"), name=dict(type="str"), prefix=dict(type="str")),
        supports_check_mode=True,
        mutually_exclusive=[["node_id", "name", "prefix"]],
    )
    p = module.params
    client = nomad_client(module)
    with nomad_errors(module):
        if p["name"]:
            nodes = [n for n in client.nodes.list()[0] if n.name == p["name"]]
            if len(nodes) > 1:
                module.fail_json(msg="expected one node named %s, found %d" % (p["name"], len(nodes)))
            if nodes:
                nodes = [client.nodes.info(nodes[0].id)[0]]
        elif p["node_id"]:
            node = read_or_none(lambda: client.nodes.info(p["node_id"]))
            nodes = [node] if node else []
        elif p["prefix"]:
            nodes = client.nodes.prefix_list(p["prefix"])[0]
        else:
            nodes = client.nodes.list()[0]
    module.exit_json(changed=False, nodes=[n.to_json() for n in nodes])


if __name__ == "__main__":
    main()
