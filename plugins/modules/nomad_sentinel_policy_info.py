#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_sentinel_policy_info
short_description: Read Nomad Sentinel policies
description:
  - Return one Sentinel policy by name, or every policy the token can see. Enterprise.
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
- name: List every Sentinel policy
  benemon.nomad.nomad_sentinel_policy_info:
  register: result

- name: Read one policy
  benemon.nomad.nomad_sentinel_policy_info:
    name: docker-only
  register: result
"""

RETURN = r"""
sentinel_policies:
  description:
    - Policies as the Nomad API returns them, with the API's field names.
    - Without O(name) the list endpoint answers with stubs, which carry no C(Policy) source.
  returned: always
  type: list
  elements: dict
  sample:
    - Name: docker-only
      Description: Jobs must use the docker driver
      Scope: submit-job
      EnforcementLevel: hard-mandatory
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
            policy = read_or_none(lambda: client.sentinel_policies.info(name))
            policies = [policy] if policy else []
        else:
            policies = client.sentinel_policies.list()[0]
    module.exit_json(changed=False, sentinel_policies=[p.to_json() for p in policies])


if __name__ == "__main__":
    main()
