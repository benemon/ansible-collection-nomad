#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_volume_info
short_description: Read Nomad dynamic host volumes
version_added: 0.4.0
description:
  - Return one full dynamic host volume by ID, or list volume stubs.
options:
  id:
    description:
      - ID of one volume to return. A volume that does not exist returns an empty list.
      - The request must use the volume's own O(namespace); V(*) works only when listing volumes.
    type: str
  name:
    description: Return only volume stubs whose name exactly matches this value.
    type: str
  node_pool:
    description: Return only volume stubs in this node pool.
    type: str
  node_id:
    description: Return only volume stubs on this node.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every dynamic host volume
  benemon.nomad.nomad_volume_info:
  register: result

- name: List volumes named data in a node pool
  benemon.nomad.nomad_volume_info:
    name: data
    node_pool: default
  register: result

- name: Read one volume
  benemon.nomad.nomad_volume_info:
    id: 3735cc2c-cc64-11ef-89ed-bfb5b3bc38ea
    namespace: web
  register: result
"""

RETURN = r"""
volumes:
  description:
    - Volumes as the Nomad API returns them, with the API's field names.
    - With O(id) the one volume is the full document; the list endpoint returns stubs.
  returned: always
  type: list
  elements: dict
  sample:
    - Namespace: web
      ID: 3735cc2c-cc64-11ef-89ed-bfb5b3bc38ea
      Name: data
      PluginID: mkdir
      NodePool: default
      NodeID: 5c5830d0-cc64-11ef-a293-4f03e55969ea
      State: ready
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    NOMAD_ARGUMENT_SPEC,
    NOMAD_NAMESPACE_ARGUMENT_SPEC,
    nomad_client,
    nomad_errors,
    read_or_none,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            **NOMAD_NAMESPACE_ARGUMENT_SPEC,
            id=dict(type="str"),
            name=dict(type="str"),
            node_pool=dict(type="str"),
            node_id=dict(type="str"),
        ),
        supports_check_mode=True,
        mutually_exclusive=[["id", "name"], ["id", "node_pool"], ["id", "node_id"]],
    )
    p = module.params
    client = nomad_client(module)
    with nomad_errors(module):
        if p["id"]:
            volume = read_or_none(lambda: client.host_volumes.get(p["id"]))
            volumes = [volume] if volume else []
        else:
            volumes = client.host_volumes.list(node_pool=p["node_pool"] or "", node_id=p["node_id"] or "")[0]
            if p["name"]:
                volumes = [volume for volume in volumes if volume.name == p["name"]]
    module.exit_json(changed=False, volumes=[volume.to_json() for volume in volumes])


if __name__ == "__main__":
    main()
