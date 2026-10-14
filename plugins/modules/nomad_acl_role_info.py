#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_acl_role_info
short_description: Read Nomad ACL roles
version_added: 0.1.0
description:
  - Return one ACL role by name or ID, or every role the token can see.
options:
  name:
    description: Name of a single role to return. A role that does not exist returns an empty list.
    type: str
  id:
    description: ID of a single role to return. A role that does not exist returns an empty list.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every role
  benemon.nomad.nomad_acl_role_info:
  register: result

- name: Read one role by name
  benemon.nomad.nomad_acl_role_info:
    name: readers
  register: result
"""

RETURN = r"""
roles:
  description: Roles as the Nomad API returns them, with the API's field names.
  returned: always
  type: list
  elements: dict
  sample:
    - ID: 2876d4b6-7302-c0fb-4bf7-66e339eaa337
      Name: readers
      Description: Read-only operators
      Policies:
        - Name: read-default
      CreateIndex: 12
      ModifyIndex: 12
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors, read_or_none


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, name=dict(type="str"), id=dict(type="str")),
        supports_check_mode=True,
        mutually_exclusive=[["name", "id"]],
    )
    p = module.params
    client = nomad_client(module)
    with nomad_errors(module):
        if p["name"] or p["id"]:
            role = read_or_none(lambda: client.acl_roles.get_by_name(p["name"]) if p["name"] else client.acl_roles.get(p["id"]))
            roles = [role] if role else []
        else:
            roles = client.acl_roles.list()[0]
    module.exit_json(changed=False, roles=[r.to_json() for r in roles])


if __name__ == "__main__":
    main()
