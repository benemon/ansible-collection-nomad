#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_job_info
short_description: Read Nomad jobs
description:
  - Return one job in full by ID, or the list of jobs in the namespace as the API's job list stubs.
options:
  name:
    description: ID of a single job to return in full. A job that does not exist returns an empty list.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List the jobs in a namespace
  benemon.nomad.nomad_job_info:
    namespace: web
  register: result

- name: Read one job in full
  benemon.nomad.nomad_job_info:
    name: web
  register: result
"""

RETURN = r"""
jobs:
  description:
    - Jobs as the Nomad API returns them, with the API's field names.
    - With O(name), the one full job document; without it, the job list stubs the list endpoint returns.
  returned: always
  type: list
  elements: dict
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    NOMAD_ARGUMENT_SPEC,
    NOMAD_NAMESPACE_ARGUMENT_SPEC,
    nomad_client,
    nomad_errors,
    read_or_none,
)


def main():
    module = AnsibleModule(argument_spec=dict(NOMAD_ARGUMENT_SPEC, **NOMAD_NAMESPACE_ARGUMENT_SPEC, name=dict(type="str")), supports_check_mode=True)
    client = nomad_client(module)
    name = module.params["name"]
    with nomad_errors(module):
        if name:
            job = read_or_none(lambda: client.jobs.info(name))
            jobs = [job] if job else []
        else:
            jobs = client.jobs.list()[0]
    module.exit_json(changed=False, jobs=[j.to_json() for j in jobs])


if __name__ == "__main__":
    main()
