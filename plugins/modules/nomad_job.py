#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_job
short_description: Register or stop a Nomad job
version_added: 0.1.0
description:
  - Register a job from its specification, or stop it.
  - Whether a registration changes anything is decided by the server's plan endpoint, so an unchanged job reports no change.
  - The diff shows the job on the server before and the submitted document after.
  - By default the module waits for the evaluation and, for service jobs, for the deployment to finish, and fails when
    allocations cannot be placed or the deployment fails.
options:
  jobspec:
    description:
      - The job specification as HCL text, as a JSON document in text, or as the document itself.
      - HCL is converted by the server, so it must be valid for the server's version. The document is the shape
        C(nomad job run -output) prints and the API documents.
      - Required when O(state=present).
    type: raw
  name:
    description:
      - The job ID.
      - Required when O(state=absent). When set with O(jobspec) it must match the ID in the specification.
    type: str
  state:
    description: Whether the job should be registered or stopped.
    type: str
    choices: [present, absent]
    default: present
  purge:
    description: With O(state=absent), remove the job from the server rather than leaving it stopped.
    type: bool
    default: false
  policy_override:
    description: Override soft-mandatory Sentinel policies. Enterprise.
    type: bool
    default: false
  wait:
    description:
      - Wait for the evaluation to complete and, for service jobs, for the latest deployment to reach a terminal status.
      - Failed placements and failed deployments fail the task.
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
- name: Register a job from an HCL file and wait for its deployment
  benemon.nomad.nomad_job:
    jobspec: "{{ lookup('ansible.builtin.file', 'web.nomad.hcl') }}"

- name: Register a job from an HCL template
  benemon.nomad.nomad_job:
    jobspec: "{{ lookup('ansible.builtin.template', 'web.nomad.hcl.j2') }}"
    namespace: web

- name: Register a job from its JSON document
  benemon.nomad.nomad_job:
    jobspec: "{{ lookup('ansible.builtin.file', 'web.json') }}"

- name: Stop and purge a job
  benemon.nomad.nomad_job:
    name: web
    state: absent
    purge: true
"""

RETURN = r"""
job:
  description:
    - The job as the Nomad API returns it, with the API's field names, after a write or when nothing changed.
    - In check mode, the submitted document.
  returned: when O(state=present)
  type: dict
eval_id:
  description: ID of the evaluation the change created.
  returned: when a write was made
  type: str
deployment:
  description: The latest deployment of the job after waiting, as the API returns it.
  returned: when O(wait=true) and the job has a deployment
  type: dict
"""

import json
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
EVAL_DONE = ("complete", "failed", "canceled")
DEPLOYMENT_RUNNING = ("running", "pending", "blocked", "unblocking", "paused")


def wait_for_eval(module, client, eval_id, deadline):
    index = 0
    while time.monotonic() < deadline:
        ev, qm = client.evaluations.info(eval_id, QueryOptions(wait_index=index, wait_time=WAIT))
        if ev.status in EVAL_DONE:
            if ev.status != "complete":
                module.fail_json(msg="evaluation %s %s: %s" % (eval_id, ev.status, ev.status_description))
            if ev.failed_tg_allocs:
                module.fail_json(msg="evaluation %s could not place every allocation" % eval_id, failed_tg_allocs=ev.failed_tg_allocs)
            return ev
        index = qm.last_index
    module.fail_json(msg="evaluation %s did not complete within %d seconds" % (eval_id, module.params["timeout"]))


def wait_for_deployment(module, client, job_id, deadline):
    dep = read_or_none(lambda: client.jobs.latest_deployment(job_id))
    if dep is None:
        return None
    index = 0
    while time.monotonic() < deadline:
        dep, qm = client.deployments.info(dep.id, QueryOptions(wait_index=index, wait_time=WAIT))
        if dep.status not in DEPLOYMENT_RUNNING:
            if dep.status != "successful":
                module.fail_json(msg="deployment %s %s: %s" % (dep.id, dep.status, dep.status_description), deployment=dep.to_json())
            return dep
        index = qm.last_index
    module.fail_json(msg="deployment %s did not finish within %d seconds" % (dep.id, module.params["timeout"]), deployment=dep.to_json())


def document(module, client, jobspec):
    if isinstance(jobspec, dict):
        return jobspec
    if not isinstance(jobspec, str):
        module.fail_json(msg="jobspec must be HCL text, a JSON document as text, or the document itself")
    try:
        doc = json.loads(jobspec)
    except ValueError:
        return client.jobs.parse_hcl(jobspec).to_json()
    if not isinstance(doc, dict):
        module.fail_json(msg="jobspec is JSON but not a job document")
    return doc


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            **NOMAD_NAMESPACE_ARGUMENT_SPEC,
            jobspec=dict(type="raw"),
            name=dict(type="str"),
            state=dict(type="str", choices=["present", "absent"], default="present"),
            purge=dict(type="bool", default=False),
            policy_override=dict(type="bool", default=False),
            wait=dict(type="bool", default=True),
            timeout=dict(type="int", default=300),
        ),
        supports_check_mode=True,
        required_if=[["state", "absent", ["name"]], ["state", "present", ["jobspec"]]],
    )
    p = module.params
    client = nomad_client(module)
    deadline = time.monotonic() + p["timeout"]
    with nomad_errors(module):
        if p["state"] == "absent":
            current = read_or_none(lambda: client.jobs.info(p["name"]))
            if current is None or (current.stop and not p["purge"]):
                module.exit_json(changed=False)
            diff = dict(before=current.to_json(), after={})
            if module.check_mode:
                module.exit_json(changed=True, diff=diff)
            eval_id = client.jobs.deregister(p["name"], purge=p["purge"])[0]
            if p["wait"] and eval_id:
                wait_for_eval(module, client, eval_id, deadline)
            module.exit_json(changed=True, eval_id=eval_id, diff=diff)

        job = document(module, client, p["jobspec"])
        job_id = job.get("ID")
        if not job_id:
            module.fail_json(msg="the job specification has no ID")
        if p["name"] and p["name"] != job_id:
            module.fail_json(msg="name is %s but the job specification's ID is %s" % (p["name"], job_id))

        current = read_or_none(lambda: client.jobs.info(job_id))
        plan = client.jobs.plan(job, diff=True, policy_override=p["policy_override"])[0]
        changed = plan.diff is None or plan.diff.type != "None"
        result = dict(changed=changed, diff=dict(before=current.to_json() if current else {}, after=job))
        if not changed or module.check_mode:
            module.exit_json(job=current.to_json() if current else job, **result)

        resp = client.jobs.register(job, policy_override=p["policy_override"])[0]
        result["eval_id"] = resp.eval_id
        if p["wait"]:
            wait_for_eval(module, client, resp.eval_id, deadline)
            dep = wait_for_deployment(module, client, job_id, deadline)
            if dep is not None:
                result["deployment"] = dep.to_json()
        current = client.jobs.info(job_id)[0]
        module.exit_json(job=current.to_json(), **result)


if __name__ == "__main__":
    main()
