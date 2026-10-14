#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_namespace_info
short_description: Read Nomad namespaces
description:
  - Return one namespace by name, or every namespace the token can see.
options:
  name:
    description: Name of a single namespace to return. A namespace that does not exist returns an empty list.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every namespace
  benemon.nomad.nomad_namespace_info:
  register: result

- name: Read one namespace
  benemon.nomad.nomad_namespace_info:
    name: web
  register: result
"""

RETURN = r"""
namespaces:
  description: Namespaces as the Nomad API returns them, with the API's field names.
  returned: always
  type: list
  elements: dict
  sample:
    - Name: default
      Description: Default shared namespace
      CreateIndex: 1
      ModifyIndex: 1
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors, read_or_none


def main():
    module = AnsibleModule(argument_spec=dict(NOMAD_ARGUMENT_SPEC, name=dict(type="str")), supports_check_mode=True)
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        if name:
            namespace = read_or_none(lambda: client.namespaces.info(name))
            namespaces = [namespace] if namespace else []
        else:
            namespaces = client.namespaces.list()[0]
    module.exit_json(changed=False, namespaces=[n.to_json() for n in namespaces])


if __name__ == "__main__":
    main()
