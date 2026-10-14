#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_sentinel_policy
short_description: Manage a Nomad Sentinel policy
version_added: 0.1.0
description:
  - Create, update or delete a Sentinel policy. Enterprise.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
  - Sentinel policies need ACLs enabled on the server.
options:
  name:
    description: Name of the policy.
    type: str
    required: true
  description:
    description: Description of the policy.
    type: str
  scope:
    description: Operation the policy applies to.
    type: str
    choices: [submit-job, submit-host-volume, submit-csi-volume]
  enforcement_level:
    description: What a failing policy does to the operation.
    type: str
    choices: [advisory, soft-mandatory, hard-mandatory]
  policy:
    description: The Sentinel policy source.
    type: str
  state:
    description: Whether the policy should exist.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Only allow jobs that use the docker driver
  benemon.nomad.nomad_sentinel_policy:
    name: docker-only
    description: Jobs must use the docker driver
    scope: submit-job
    enforcement_level: hard-mandatory
    policy: |
      main = rule { all_drivers_docker }
      all_drivers_docker = rule {
        all job.task_groups as tg {
          all tg.tasks as task {
            task.driver is "docker"
          }
        }
      }

- name: Delete the policy
  benemon.nomad.nomad_sentinel_policy:
    name: docker-only
    state: absent
"""

RETURN = r"""
sentinel_policy:
  description: The policy as the Nomad API returns it, with the API's field names.
  returned: when O(state=present)
  type: dict
  sample:
    Name: docker-only
    Description: Jobs must use the docker driver
    Scope: submit-job
    EnforcementLevel: hard-mandatory
    Policy: main = rule { true }
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
    from nomadpy import SentinelPolicy
except ImportError:
    pass

RESOURCE_SPEC = dict(
    name=dict(type="str", required=True),
    description=dict(type="str"),
    scope=dict(type="str", choices=["submit-job", "submit-host-volume", "submit-csi-volume"]),
    enforcement_level=dict(type="str", choices=["advisory", "soft-mandatory", "hard-mandatory"]),
    policy=dict(type="str"),
)


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, state=dict(type="str", choices=["present", "absent"], default="present"), **RESOURCE_SPEC),
        supports_check_mode=True,
    )
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        current = read_or_none(lambda: client.sentinel_policies.info(name))
        before = current.to_json() if current else {}

        if module.params["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.sentinel_policies.delete(name)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        wanted = apply_options(current, SentinelPolicy, {k: module.params[k] for k in RESOURCE_SPEC})
        changed = current is None or differs(current, wanted)
        if changed and not module.check_mode:
            client.sentinel_policies.upsert(wanted)
            wanted = client.sentinel_policies.info(name)[0]
        module.exit_json(changed=changed, sentinel_policy=wanted.to_json(), diff=dict(before=before, after=wanted.to_json()))


if __name__ == "__main__":
    main()
