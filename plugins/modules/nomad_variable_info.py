#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_variable_info
short_description: Read Nomad variables
description:
  - Return one variable by path with its items, or the metadata of every variable the token can see.
options:
  path:
    description: Path of a single variable to return. A variable that does not exist returns an empty list.
    type: str
  prefix:
    description: Return only the variables whose path starts with this prefix. Mutually exclusive with O(path).
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
notes:
  - With O(path) the returned document carries the item values.
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every variable
  benemon.nomad.nomad_variable_info:
  register: result
  no_log: true

- name: List the variables under a prefix
  benemon.nomad.nomad_variable_info:
    prefix: db/
  register: result
  no_log: true

- name: Read one variable with its items
  benemon.nomad.nomad_variable_info:
    path: db/credentials
    namespace: web
  register: result
  no_log: true
"""

RETURN = r"""
variables:
  description:
    - Variables as the Nomad API returns them, with the API's field names.
    - With O(path) the one variable carries C(Items); the list endpoint returns metadata stubs without C(Items).
  returned: always
  type: list
  elements: dict
  sample:
    - Namespace: web
      Path: db/credentials
      CreateIndex: 12
      ModifyIndex: 12
      CreateTime: 1760000000000000000
      ModifyTime: 1760000000000000000
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    NOMAD_ARGUMENT_SPEC,
    NOMAD_NAMESPACE_ARGUMENT_SPEC,
    nomad_client,
    nomad_errors,
)


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, **NOMAD_NAMESPACE_ARGUMENT_SPEC, path=dict(type="str"), prefix=dict(type="str")),
        supports_check_mode=True,
        mutually_exclusive=[["path", "prefix"]],
    )
    client = nomad_client(module)
    path = module.params["path"]
    prefix = module.params["prefix"]
    with nomad_errors(module):
        if path:
            variable = client.variables.peek(path)[0]
            variables = [variable] if variable else []
        elif prefix:
            variables = client.variables.prefix_list(prefix)[0]
        else:
            variables = client.variables.list()[0]
    module.exit_json(changed=False, variables=[v.to_json() for v in variables])


if __name__ == "__main__":
    main()
