#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_quota
short_description: Manage a Nomad quota specification
description:
  - Create, update or delete a quota specification. Enterprise.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
    O(limits) is written as a whole.
options:
  name:
    description: Name of the quota specification.
    type: str
    required: true
  description:
    description: Description of the quota specification.
    type: str
  limits:
    description: Resource limits, one per region.
    type: list
    elements: dict
    suboptions:
      region:
        description: Region the limit applies to.
        type: str
        required: true
      region_limit:
        description: Resources the region may use in total. A limit of V(0) is unlimited and a negative limit allows nothing.
        type: dict
        suboptions:
          cpu:
            description: CPU in MHz.
            type: int
            default: 0
          cores:
            description: Reserved CPU cores.
            type: int
            default: 0
          memory_mb:
            description: Memory in MiB.
            type: int
            default: 0
          memory_max_mb:
            description: Maximum memory in MiB tasks may use beyond their reservation.
            type: int
            default: 0
          secrets_mb:
            description: Secrets directory space in MiB.
            type: int
            default: 0
          storage:
            description: Storage limits.
            type: dict
            suboptions:
              variables_mb:
                description: Nomad variables in MiB.
                type: int
              host_volumes_mb:
                description: Dynamic host volumes in MiB.
                type: int
          node_pools:
            description: Limits for single node pools, each within the region limit.
            type: list
            elements: dict
            suboptions:
              node_pool:
                description: Name of the node pool.
                type: str
                required: true
              cpu:
                description: CPU in MHz.
                type: int
                default: 0
              cores:
                description: Reserved CPU cores.
                type: int
                default: 0
              memory_mb:
                description: Memory in MiB.
                type: int
                default: 0
              memory_max_mb:
                description: Maximum memory in MiB tasks may use beyond their reservation.
                type: int
                default: 0
              secrets_mb:
                description: Secrets directory space in MiB.
                type: int
                default: 0
              storage:
                description: Storage limits.
                type: dict
                suboptions:
                  variables_mb:
                    description: Nomad variables in MiB.
                    type: int
                  host_volumes_mb:
                    description: Dynamic host volumes in MiB.
                    type: int
      variables_limit:
        description: Nomad variables in MiB. Superseded by O(limits[].region_limit.storage.variables_mb).
        type: int
        default: 0
  state:
    description: Whether the quota specification should exist.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Limit the web tier
  benemon.nomad.nomad_quota:
    name: web
    description: Web tier
    limits:
      - region: global
        region_limit:
          cpu: 2500
          memory_mb: 1000
          storage:
            variables_mb: 100

- name: Apply it to a namespace
  benemon.nomad.nomad_namespace:
    name: web
    quota: web

- name: Delete the quota specification
  benemon.nomad.nomad_quota:
    name: web
    state: absent
"""

RETURN = r"""
quota:
  description: The quota specification as the Nomad API returns it, with the API's field names.
  returned: when O(state=present)
  type: dict
  sample:
    Name: web
    Description: Web tier
    Limits:
      - Region: global
        RegionLimit:
          CPU: 2500
          Cores: 0
          MemoryMB: 1000
          MemoryMaxMB: 0
          SecretsMB: 0
          Storage:
            VariablesMB: 100
            HostVolumesMB: 0
        VariablesLimit: 100
        Hash: GQg+FpBgGHHLxkGyg5Z3SjZephv8EvVR28M1VT7eZSo=
    CreateIndex: 12
    ModifyIndex: 12
"""

import dataclasses

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
    from nomadpy import QuotaSpec
except ImportError:
    pass

# The server stores an unset limit as 0, so the options default to it and compare equal to what it answers.
_RESOURCES = dict(
    cpu=dict(type="int", default=0),
    cores=dict(type="int", default=0),
    memory_mb=dict(type="int", default=0),
    memory_max_mb=dict(type="int", default=0),
    secrets_mb=dict(type="int", default=0, no_log=False),
    storage=dict(type="dict", options=dict(variables_mb=dict(type="int"), host_volumes_mb=dict(type="int"))),
)

RESOURCE_SPEC = dict(
    name=dict(type="str", required=True),
    description=dict(type="str"),
    limits=dict(
        type="list",
        elements="dict",
        options=dict(
            region=dict(type="str", required=True),
            region_limit=dict(
                type="dict",
                options=dict(
                    _RESOURCES,
                    node_pools=dict(type="list", elements="dict", options=dict(_RESOURCES, node_pool=dict(type="str", required=True))),
                ),
            ),
            variables_limit=dict(type="int", default=0),
        ),
    ),
)


def without_hashes(spec):
    """without_hashes drops the Hash the server computes for each limit, which no option expresses."""
    return dataclasses.replace(spec, limits=[dataclasses.replace(limit, hash=None) for limit in spec.limits or []])


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, state=dict(type="str", choices=["present", "absent"], default="present"), **RESOURCE_SPEC),
        supports_check_mode=True,
    )
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        current = read_or_none(lambda: client.quotas.info(name))
        before = current.to_json() if current else {}

        if module.params["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.quotas.delete(name)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        wanted = apply_options(current, QuotaSpec, {k: module.params[k] for k in RESOURCE_SPEC})
        changed = current is None or differs(without_hashes(current), without_hashes(wanted))
        if changed and not module.check_mode:
            client.quotas.register(wanted)
            wanted = client.quotas.info(name)[0]
        module.exit_json(changed=changed, quota=wanted.to_json(), diff=dict(before=before, after=wanted.to_json()))


if __name__ == "__main__":
    main()
