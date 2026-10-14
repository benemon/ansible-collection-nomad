#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_quota_info
short_description: Read Nomad quota specifications
description:
  - Return one quota specification by name, or every quota specification the token can see. Enterprise.
options:
  name:
    description: Name of a single quota specification to return. One that does not exist returns an empty list.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every quota specification
  benemon.nomad.nomad_quota_info:
  register: result

- name: Read one quota specification
  benemon.nomad.nomad_quota_info:
    name: web
  register: result
"""

RETURN = r"""
quotas:
  description: Quota specifications as the Nomad API returns them, with the API's field names.
  returned: always
  type: list
  elements: dict
  sample:
    - Name: web
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

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors, read_or_none


def main():
    module = AnsibleModule(argument_spec=dict(NOMAD_ARGUMENT_SPEC, name=dict(type="str")), supports_check_mode=True)
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        if name:
            quota = read_or_none(lambda: client.quotas.info(name))
            quotas = [quota] if quota else []
        else:
            quotas = client.quotas.list()[0]
    module.exit_json(changed=False, quotas=[q.to_json() for q in quotas])


if __name__ == "__main__":
    main()
