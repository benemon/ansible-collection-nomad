#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_acl_policy
short_description: Manage a Nomad ACL policy
version_added: 0.1.0
description:
  - Create, update or delete an ACL policy.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
options:
  name:
    description: Name of the policy.
    type: str
    required: true
  description:
    description: Description of the policy.
    type: str
  rules:
    description: The policy rules, as HCL.
    type: str
  job_acl:
    description: Workload the policy is attached to, so its tasks receive it through workload identity.
    type: dict
    suboptions:
      namespace:
        description: Namespace of the job.
        type: str
      job_id:
        description: ID of the job.
        type: str
      group:
        description: Task group within the job.
        type: str
      task:
        description: Task within the group.
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
- name: Allow reading the default namespace
  benemon.nomad.nomad_acl_policy:
    name: read-default
    description: Read access to the default namespace
    rules: |
      namespace "default" {
        policy = "read"
      }

- name: Attach a policy to a job's workload identity
  benemon.nomad.nomad_acl_policy:
    name: web-self
    rules: |
      namespace "default" {
        policy = "read"
      }
    job_acl:
      namespace: default
      job_id: web

- name: Delete the policy
  benemon.nomad.nomad_acl_policy:
    name: read-default
    state: absent
"""

RETURN = r"""
policy:
  description: The policy as the Nomad API returns it, with the API's field names.
  returned: when O(state=present)
  type: dict
  sample:
    Name: read-default
    Description: Read access to the default namespace
    Rules: "namespace \"default\" { policy = \"read\" }"
    JobACL: null
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
    from nomadpy import ACLPolicy
except ImportError:
    pass

RESOURCE_SPEC = dict(
    name=dict(type="str", required=True),
    description=dict(type="str"),
    rules=dict(type="str"),
    job_acl=dict(
        type="dict",
        options=dict(
            namespace=dict(type="str"),
            job_id=dict(type="str"),
            group=dict(type="str"),
            task=dict(type="str"),
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
        current = read_or_none(lambda: client.acl_policies.info(name))
        before = current.to_json() if current else {}

        if module.params["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.acl_policies.delete(name)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        wanted = apply_options(current, ACLPolicy, {k: module.params[k] for k in RESOURCE_SPEC})
        changed = current is None or differs(current, wanted)
        if changed and not module.check_mode:
            client.acl_policies.upsert(wanted)
            wanted = client.acl_policies.info(name)[0]
        module.exit_json(changed=changed, policy=wanted.to_json(), diff=dict(before=before, after=wanted.to_json()))


if __name__ == "__main__":
    main()
