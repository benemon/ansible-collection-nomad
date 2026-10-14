#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_node_pool
short_description: Manage a Nomad node pool
description:
  - Create, update or delete a node pool.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
  - The built-in pools V(default) and V(all) cannot be deleted.
options:
  name:
    description: Name of the node pool.
    type: str
    required: true
  description:
    description: Description of the node pool.
    type: str
  meta:
    description: Arbitrary key-value metadata.
    type: dict
  node_identity_ttl:
    description: Lifetime of the identities issued to nodes in the pool, as a Nomad duration such as V(24h) or V(30m).
    type: str
  scheduler_configuration:
    description: Scheduler settings for the pool. Enterprise.
    type: dict
    suboptions:
      scheduler_algorithm:
        description: Algorithm used to place allocations on nodes in the pool.
        type: str
        choices: [binpack, spread]
      memory_oversubscription_enabled:
        description: Allow tasks to use more memory than they reserve.
        type: bool
  state:
    description: Whether the node pool should exist.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Create a node pool
  benemon.nomad.nomad_node_pool:
    name: gpu
    description: GPU nodes
    meta:
      tier: compute
    node_identity_ttl: 12h

- name: Spread allocations across the pool (Enterprise)
  benemon.nomad.nomad_node_pool:
    name: gpu
    scheduler_configuration:
      scheduler_algorithm: spread

- name: Delete the node pool
  benemon.nomad.nomad_node_pool:
    name: gpu
    state: absent
"""

RETURN = r"""
node_pool:
  description: The node pool as the Nomad API returns it, with the API's field names.
  returned: when O(state=present)
  type: dict
  sample:
    Name: gpu
    Description: GPU nodes
    Meta:
      tier: compute
    NodeIdentityTTL: 12h0m0s
    SchedulerConfiguration: null
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
    from nomadpy import NodePool
    from nomadpy.models import parse_duration
except ImportError:
    pass

RESOURCE_SPEC = dict(
    name=dict(type="str", required=True),
    description=dict(type="str"),
    meta=dict(type="dict"),
    node_identity_ttl=dict(type="str"),
    scheduler_configuration=dict(
        type="dict",
        options=dict(
            scheduler_algorithm=dict(type="str", choices=["binpack", "spread"]),
            memory_oversubscription_enabled=dict(type="bool"),
        ),
    ),
)


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, state=dict(type="str", choices=["present", "absent"], default="present"), **RESOURCE_SPEC),
        supports_check_mode=True,
    )
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        current = read_or_none(lambda: client.node_pools.info(name))
        before = current.to_json() if current else {}

        if module.params["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.node_pools.delete(name)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        options = {k: module.params[k] for k in RESOURCE_SPEC}
        if options["node_identity_ttl"] is not None:
            options["node_identity_ttl"] = parse_duration(options["node_identity_ttl"])
        wanted = apply_options(current, NodePool, options)
        changed = current is None or differs(current, wanted)
        if changed and not module.check_mode:
            client.node_pools.register(wanted)
            wanted = client.node_pools.info(name)[0]
        module.exit_json(changed=changed, node_pool=wanted.to_json(), diff=dict(before=before, after=wanted.to_json()))


if __name__ == "__main__":
    main()
