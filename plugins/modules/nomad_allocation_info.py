#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_allocation_info
short_description: Read Nomad allocations and their task logs
version_added: 0.2.0
description:
  - Return one allocation in full by ID, or the allocations of a namespace as the list endpoint returns them, narrowed
    by job or node.
  - With O(task) the stdout or stderr log of that task of the one allocation is returned as well.
options:
  alloc_id:
    description: ID of a single allocation to return in full. An allocation that does not exist returns an empty list.
    type: str
  job:
    description: Return only the allocations of this job.
    type: str
  node_id:
    description: Return only the allocations placed on this node.
    type: str
  task:
    description: Task of the allocation named by O(alloc_id) whose log is returned in RV(logs).
    type: str
  log_type:
    description: Which log of O(task) to return.
    type: str
    choices: [stdout, stderr]
    default: stdout
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Allocations of a job
  benemon.nomad.nomad_allocation_info:
    job: web
    namespace: web
  register: result

- name: One allocation with its task's stderr
  benemon.nomad.nomad_allocation_info:
    alloc_id: 8b5e7a4e-2b1d-6f0c-9a3e-0d1f2a3b4c5d
    task: web
    log_type: stderr
  register: result
"""

RETURN = r"""
allocations:
  description:
    - Allocations as the Nomad API returns them, with the API's field names.
    - With O(alloc_id) the one allocation is the full document; otherwise the list endpoint's stubs.
  returned: always
  type: list
  elements: dict
logs:
  description: The whole log of O(task), decoded as text.
  returned: when O(task) is set
  type: str
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    NOMAD_ARGUMENT_SPEC,
    NOMAD_NAMESPACE_ARGUMENT_SPEC,
    nomad_client,
    nomad_errors,
    read_or_none,
)

try:
    from nomadpy import QueryOptions
except ImportError:
    pass


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            **NOMAD_NAMESPACE_ARGUMENT_SPEC,
            alloc_id=dict(type="str"),
            job=dict(type="str"),
            node_id=dict(type="str"),
            task=dict(type="str"),
            log_type=dict(type="str", choices=["stdout", "stderr"], default="stdout"),
        ),
        supports_check_mode=True,
        mutually_exclusive=[["alloc_id", "job"], ["alloc_id", "node_id"]],
        required_by={"task": "alloc_id"},
    )
    p = module.params
    client = nomad_client(module)
    namespace = p["namespace"] or ""
    result = dict(changed=False)
    with nomad_errors(module):
        if p["alloc_id"]:
            alloc = read_or_none(lambda: client.allocations.info(p["alloc_id"], QueryOptions(namespace=namespace)))
            allocations = [alloc] if alloc else []
            if p["task"]:
                if alloc is None:
                    module.fail_json(msg="allocation %s not found" % p["alloc_id"])
                frames = client.alloc_fs.logs(p["alloc_id"], False, p["task"], p["log_type"], "start", 0, QueryOptions(namespace=namespace))
                result["logs"] = b"".join(f.data_bytes for f in frames).decode(errors="replace")
        else:
            filters = []
            if p["job"]:
                filters.append('JobID == "%s"' % p["job"])
            if p["node_id"]:
                filters.append('NodeID == "%s"' % p["node_id"])
            allocations = client.allocations.list(QueryOptions(namespace=namespace, filter=" and ".join(filters)))[0]
    module.exit_json(allocations=[a.to_json() for a in allocations], **result)


if __name__ == "__main__":
    main()
