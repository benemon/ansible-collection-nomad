#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_node
short_description: Set the scheduling eligibility or drain of a Nomad node
version_added: 0.1.0
description:
  - Mark a client node eligible or ineligible for scheduling, start a drain, or stop one.
  - The node's current drain flag and eligibility are compared to the options; nothing is written when they already match.
  - A drain that has finished leaves the node ineligible with the drain flag off, so asking for O(drain=true) again starts
    a new drain.
options:
  node_id:
    description: ID of the node. One of O(node_id) and O(name) is required.
    type: str
  name:
    description: Name of the node. More than one node with the name is a failure.
    type: str
  eligibility:
    description: Whether the scheduler may place allocations on the node.
    type: str
    choices: [eligible, ineligible]
  drain:
    description: Whether the node should be draining. Starting a drain also marks the node ineligible.
    type: bool
  deadline:
    description:
      - Nomad duration after which the drain stops the remaining allocations, when O(drain=true).
      - V(0) means no deadline and a negative value forces an immediate drain.
    type: str
    default: 1h
  ignore_system_jobs:
    description: Leave system job allocations running when draining, when O(drain=true).
    type: bool
    default: false
  mark_eligible:
    description: Mark the node eligible again when stopping a drain, or after one has finished, when O(drain=false).
    type: bool
    default: false
  wait:
    description: Wait for the drain to finish, when O(drain=true).
    type: bool
    default: true
  timeout:
    description: Seconds to wait before giving up when O(wait=true).
    type: int
    default: 300
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Take a node out of scheduling
  benemon.nomad.nomad_node:
    name: worker-03
    eligibility: ineligible

- name: Drain a node, keeping system jobs, and wait for its allocations to move
  benemon.nomad.nomad_node:
    node_id: 7f3a9b2c-1d4e-5f6a-8b9c-0d1e2f3a4b5c
    drain: true
    ignore_system_jobs: true
    deadline: 30m

- name: Stop the drain and put the node back into scheduling
  benemon.nomad.nomad_node:
    name: worker-03
    drain: false
    mark_eligible: true
"""

RETURN = r"""
node:
  description: The node as the Nomad API returns it after the change, with the API's field names.
  returned: always
  type: dict
"""

import dataclasses
import time
from datetime import timedelta

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors

try:
    from nomadpy import DrainSpec, QueryOptions
    from nomadpy.models import parse_duration
except ImportError:
    pass

WAIT = timedelta(seconds=10)


def node_id_by_name(module, client, name):
    matches = [n for n in client.nodes.list()[0] if n.name == name]
    if len(matches) != 1:
        module.fail_json(msg="expected one node named %s, found %d" % (name, len(matches)))
    return matches[0].id


def wait_for_drain(module, client, node_id, deadline):
    index = 0
    while time.monotonic() < deadline:
        node, qm = client.nodes.info(node_id, QueryOptions(wait_index=index, wait_time=WAIT))
        if not node.drain:
            return node
        index = qm.last_index
    module.fail_json(msg="node %s did not finish draining within %d seconds" % (node_id, module.params["timeout"]))


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            node_id=dict(type="str"),
            name=dict(type="str"),
            eligibility=dict(type="str", choices=["eligible", "ineligible"]),
            drain=dict(type="bool"),
            deadline=dict(type="str", default="1h"),
            ignore_system_jobs=dict(type="bool", default=False),
            mark_eligible=dict(type="bool", default=False),
            wait=dict(type="bool", default=True),
            timeout=dict(type="int", default=300),
        ),
        supports_check_mode=True,
        required_one_of=[["node_id", "name"]],
        mutually_exclusive=[["node_id", "name"]],
    )
    p = module.params
    client = nomad_client(module)
    deadline = time.monotonic() + p["timeout"]
    with nomad_errors(module):
        node_id = p["node_id"] or node_id_by_name(module, client, p["name"])
        current = client.nodes.info(node_id)[0]
        before = current.to_json()
        changed = False
        eligibility = p["eligibility"]
        if p["drain"] is False and p["mark_eligible"]:
            eligibility = eligibility or "eligible"

        if p["drain"] is not None and p["drain"] != current.drain:
            changed = True
            if module.check_mode:
                current = dataclasses.replace(current, drain=p["drain"], scheduling_eligibility="ineligible" if p["drain"] else current.scheduling_eligibility)
            elif p["drain"]:
                client.nodes.update_drain(node_id, DrainSpec(deadline=parse_duration(p["deadline"]), ignore_system_jobs=p["ignore_system_jobs"]))
                current = wait_for_drain(module, client, node_id, deadline) if p["wait"] else client.nodes.info(node_id)[0]
            else:
                client.nodes.update_drain(node_id, None, mark_eligible=p["mark_eligible"])
                current = client.nodes.info(node_id)[0]

        if eligibility and eligibility != current.scheduling_eligibility:
            changed = True
            if module.check_mode:
                current = dataclasses.replace(current, scheduling_eligibility=eligibility)
            else:
                client.nodes.toggle_eligibility(node_id, eligibility == "eligible")
                current = client.nodes.info(node_id)[0]

        module.exit_json(changed=changed, node=current.to_json(), diff=dict(before=before, after=current.to_json()))


if __name__ == "__main__":
    main()
