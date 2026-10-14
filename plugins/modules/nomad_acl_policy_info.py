#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_acl_policy_info
short_description: Read Nomad ACL policies
version_added: 0.1.0
description:
  - Return one ACL policy by name, or every policy the token can see.
options:
  name:
    description: Name of a single policy to return. A policy that does not exist returns an empty list.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every policy
  benemon.nomad.nomad_acl_policy_info:
  register: result

- name: Read one policy
  benemon.nomad.nomad_acl_policy_info:
    name: read-default
  register: result
"""

RETURN = r"""
policies:
  description:
    - Policies as the Nomad API returns them, with the API's field names.
    - Without O(name) the list endpoint's stubs are returned, which carry no C(Rules).
  returned: always
  type: list
  elements: dict
  sample:
    - Name: read-default
      Description: Read access to the default namespace
      JobACL: null
      CreateIndex: 12
      ModifyIndex: 12
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors, read_or_none


def main():
    module = AnsibleModule(argument_spec=dict(NOMAD_ARGUMENT_SPEC, name=dict(type="str")), supports_check_mode=True)
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        if name:
            policy = read_or_none(lambda: client.acl_policies.info(name))
            policies = [policy] if policy else []
        else:
            policies = client.acl_policies.list()[0]
    module.exit_json(changed=False, policies=[p.to_json() for p in policies])


if __name__ == "__main__":
    main()
