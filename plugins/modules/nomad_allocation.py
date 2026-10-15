#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_allocation
short_description: Restart, signal or stop a Nomad allocation
version_added: 0.2.0
description:
  - Restart the tasks of a running allocation, send a signal to one of them, or stop the allocation, over the API and
    without connecting into the task.
  - A restart and a signal always act and always report a change. A stop acts only on an allocation that is still
    running; one that has finished, or does not exist, reports no change.
options:
  alloc_id:
    description: ID of the allocation, in full.
    type: str
    required: true
  restart:
    description: Restart the task named by O(task), or every task of the allocation without it.
    type: bool
    default: false
  signal:
    description: Signal to send to O(task), such as V(SIGHUP).
    type: str
  task:
    description: Task the restart or the signal applies to. Required with O(signal).
    type: str
  state:
    description: V(absent) stops the allocation; its job reschedules it unless the job is stopped too.
    type: str
    choices: [present, absent]
    default: present
  wait:
    description: Wait for the allocation to reach a terminal client status after a stop.
    type: bool
    default: true
  timeout:
    description: Seconds to wait before giving up when O(wait=true).
    type: int
    default: 300
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Restart every task of an allocation
  benemon.nomad.nomad_allocation:
    alloc_id: 8b5e7a4e-2b1d-6f0c-9a3e-0d1f2a3b4c5d
    restart: true

- name: Reload one task's configuration
  benemon.nomad.nomad_allocation:
    alloc_id: 8b5e7a4e-2b1d-6f0c-9a3e-0d1f2a3b4c5d
    task: web
    signal: SIGHUP

- name: Stop an allocation and wait for it to finish
  benemon.nomad.nomad_allocation:
    alloc_id: 8b5e7a4e-2b1d-6f0c-9a3e-0d1f2a3b4c5d
    state: absent
"""

RETURN = r"""
allocation:
  description: The allocation as the Nomad API returns it after the action, with the API's field names; absent when it does not exist.
  returned: always
  type: dict
eval_id:
  description: ID of the evaluation a stop created.
  returned: when the allocation was stopped
  type: str
"""

import time
from datetime import timedelta

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

WAIT = timedelta(seconds=10)


def wait_for_terminal(module, client, alloc_id, q, deadline):
    index = 0
    while time.monotonic() < deadline:
        alloc, qm = client.allocations.info(alloc_id, QueryOptions(namespace=q.namespace, wait_index=index, wait_time=WAIT))
        if alloc.client_terminal_status():
            return alloc
        index = qm.last_index
    module.fail_json(msg="allocation %s did not stop within %d seconds" % (alloc_id, module.params["timeout"]))


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            **NOMAD_NAMESPACE_ARGUMENT_SPEC,
            alloc_id=dict(type="str", required=True),
            restart=dict(type="bool", default=False),
            signal=dict(type="str"),
            task=dict(type="str"),
            state=dict(type="str", choices=["present", "absent"], default="present"),
            wait=dict(type="bool", default=True),
            timeout=dict(type="int", default=300),
        ),
        supports_check_mode=True,
        mutually_exclusive=[["restart", "signal"]],
        required_by={"signal": "task"},
    )
    p = module.params
    if p["state"] == "absent" and (p["restart"] or p["signal"]):
        module.fail_json(msg="state=absent cannot be combined with restart or signal")
    client = nomad_client(module)
    q = QueryOptions(namespace=p["namespace"] or "")
    alloc_id = p["alloc_id"]
    result = dict(changed=False)
    with nomad_errors(module):
        current = read_or_none(lambda: client.allocations.info(alloc_id, q))
        if p["state"] == "absent":
            if current is not None and not current.client_terminal_status():
                result["changed"] = True
                if not module.check_mode:
                    result["eval_id"] = client.allocations.stop(alloc_id, q)[0].eval_id
                    if p["wait"]:
                        current = wait_for_terminal(module, client, alloc_id, q, time.monotonic() + p["timeout"])
                    else:
                        current = client.allocations.info(alloc_id, q)[0]
        else:
            if current is None:
                module.fail_json(msg="allocation %s not found" % alloc_id)
            if p["restart"]:
                result["changed"] = True
                if not module.check_mode:
                    if p["task"]:
                        client.allocations.restart(alloc_id, p["task"], q)
                    else:
                        client.allocations.restart_all_tasks(alloc_id, q)
                    current = client.allocations.info(alloc_id, q)[0]
            if p["signal"]:
                result["changed"] = True
                if not module.check_mode:
                    client.allocations.signal(alloc_id, p["task"], p["signal"], q)
                    current = client.allocations.info(alloc_id, q)[0]
    module.exit_json(allocation=current.to_json() if current is not None else None, **result)


if __name__ == "__main__":
    main()
