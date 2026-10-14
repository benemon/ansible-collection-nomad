#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_acl_role
short_description: Manage a Nomad ACL role
version_added: 0.1.0
description:
  - Create, update or delete an ACL role. Roles are selected by name; the server assigns the ID.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
options:
  name:
    description: Name of the role.
    type: str
    required: true
  description:
    description: Description of the role.
    type: str
  policies:
    description: Names of the ACL policies the role grants. Every policy must exist.
    type: list
    elements: str
  state:
    description: Whether the role should exist.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Create a role granting two policies
  benemon.nomad.nomad_acl_role:
    name: readers
    description: Read-only operators
    policies: [read-default, read-nodes]

- name: Delete the role
  benemon.nomad.nomad_acl_role:
    name: readers
    state: absent
"""

RETURN = r"""
role:
  description: The role as the Nomad API returns it, with the API's field names.
  returned: when O(state=present)
  type: dict
  sample:
    ID: 2876d4b6-7302-c0fb-4bf7-66e339eaa337
    Name: readers
    Description: Read-only operators
    Policies:
      - Name: read-default
      - Name: read-nodes
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
    from nomadpy import ACLRole
except ImportError:
    pass


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            name=dict(type="str", required=True),
            description=dict(type="str"),
            policies=dict(type="list", elements="str"),
            state=dict(type="str", choices=["present", "absent"], default="present"),
        ),
        supports_check_mode=True,
    )
    p = module.params
    client = nomad_client(module)
    with nomad_errors(module):
        current = read_or_none(lambda: client.acl_roles.get_by_name(p["name"]))
        before = current.to_json() if current else {}

        if p["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.acl_roles.delete(current.id)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        policies = None if p["policies"] is None else [dict(name=n) for n in p["policies"]]
        wanted = apply_options(current, ACLRole, dict(name=p["name"], description=p["description"], policies=policies))
        changed = current is None or differs(current, wanted)
        if changed and not module.check_mode:
            wanted = (client.acl_roles.create if current is None else client.acl_roles.update)(wanted)[0]
        module.exit_json(changed=changed, role=wanted.to_json(), diff=dict(before=before, after=wanted.to_json()))


if __name__ == "__main__":
    main()
