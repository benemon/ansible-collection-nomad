#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_volume
short_description: Manage a Nomad dynamic host volume
version_added: 0.4.0
description:
  - Create, update, register or delete a dynamic host volume. Dynamic host volumes require Nomad 1.10 or later.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
  - A volume name is unique per node across namespaces.
  - Changing O(node_pool) creates a second volume in the new pool; it does not move the first volume.
  - According to Nomad's validation, a volume used by a running allocation cannot be updated. The module returns the
    server's error.
options:
  name:
    description: Name of the volume.
    type: str
    required: true
  node_pool:
    description: Node pool in which Nomad should place or find the volume.
    type: str
  node_id:
    description: Node on which Nomad should place or find the volume. Required with O(host_path).
    type: str
  plugin_id:
    description: Host volume plugin that creates the volume, for example V(mkdir). Mutually exclusive with O(host_path).
    type: str
  host_path:
    description: Existing path on O(node_id) to register. Mutually exclusive with O(plugin_id).
    type: str
  capabilities:
    description:
      - Capabilities jobs may request when mounting the volume.
      - Reordering this list counts as a change.
      - Passing an empty list removes every capability. This was observed with Nomad 2.1.1.
    type: list
    elements: dict
    suboptions:
      access_mode:
        description: How many tasks may read or write the volume.
        type: str
        required: true
        choices: [single-node-reader-only, single-node-writer, single-node-single-writer, single-node-multi-writer]
      attachment_mode:
        description: How the volume is exposed to a task.
        type: str
        required: true
        choices: [block-device, file-system]
  parameters:
    description:
      - Plugin parameters, passed to Nomad without conversion.
      - Values must be strings. Quote values such as V(0700) as C("0700") so YAML does not convert them to numbers.
      - Passing an empty mapping removes every parameter. This was observed with Nomad 2.1.1.
    type: dict
  wait:
    description:
      - Wait until the node lists the volume's ID and the volume is ready.
      - This reads the node, so according to Nomad's ACL checks the token needs C(node:read).
      - A volume whose node is down fails each run after O(timeout) passes.
    type: bool
    default: true
  timeout:
    description: Seconds to wait before giving up when O(wait=true).
    type: int
    default: 300
  state:
    description: Whether the volume should exist.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
notes:
  - O(namespace) must name one namespace; V(*) is not supported by this module.
  - With O(wait=false), the returned C(State) after an update can be C(pending) even when the stored volume is ready.
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Create a dynamic host volume through the mkdir plugin
  benemon.nomad.nomad_volume:
    name: data
    namespace: web
    node_pool: default
    plugin_id: mkdir
    capabilities:
      - access_mode: single-node-writer
        attachment_mode: file-system
    parameters:
      mode: "0700"

- name: Register an existing directory on a node
  benemon.nomad.nomad_volume:
    name: imports
    node_id: 7f3a9b2c-1d4e-5f6a-8b9c-0d1e2f3a4b5c
    host_path: /srv/imports

- name: Delete the volume
  benemon.nomad.nomad_volume:
    name: data
    namespace: web
    state: absent
"""

RETURN = r"""
volume:
  description: The volume as the Nomad API returns it, with the API's field names.
  returned: when O(state=present)
  type: dict
  sample:
    Namespace: web
    ID: 3735cc2c-cc64-11ef-89ed-bfb5b3bc38ea
    Name: data
    PluginID: mkdir
    NodePool: default
    NodeID: 5c5830d0-cc64-11ef-a293-4f03e55969ea
    Parameters:
      mode: "0700"
    State: ready
    CreateIndex: 12
    ModifyIndex: 15
"""

import time
from datetime import timedelta

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    NOMAD_ARGUMENT_SPEC,
    NOMAD_NAMESPACE_ARGUMENT_SPEC,
    apply_options,
    differs,
    nomad_client,
    nomad_errors,
)

try:
    from nomadpy import HostVolume, QueryOptions
except ImportError:
    pass

WAIT = timedelta(seconds=10)

RESOURCE_SPEC = dict(
    name=dict(type="str", required=True),
    node_pool=dict(type="str"),
    node_id=dict(type="str"),
    plugin_id=dict(type="str"),
    host_path=dict(type="str"),
    capabilities=dict(
        type="list",
        elements="dict",
        options=dict(
            access_mode=dict(
                type="str",
                required=True,
                choices=["single-node-reader-only", "single-node-writer", "single-node-single-writer", "single-node-multi-writer"],
            ),
            attachment_mode=dict(type="str", required=True, choices=["block-device", "file-system"]),
        ),
    ),
    parameters=dict(type="dict"),
)


def find_volume(module, client):
    p = module.params
    volumes = client.host_volumes.list(node_pool=p["node_pool"] or "", node_id=p["node_id"] or "")[0]
    matches = [volume for volume in volumes if volume.name == p["name"]]
    if len(matches) > 1:
        module.fail_json(
            msg="expected one volume named %s in node pool %s, found %d; set node_id"
            % (p["name"], p["node_pool"] or "any", len(matches))
        )
    return client.host_volumes.get(matches[0].id)[0] if matches else None


def wait_for_volume(module, client, volume, deadline):
    index = 0
    last_state = "not read"
    node_volume_id = "not read"
    while time.monotonic() < deadline:
        node, qm = client.nodes.info(volume.node_id, QueryOptions(wait_index=index, wait_time=WAIT))
        node_volume = (node.host_volumes or {}).get(volume.name)
        node_volume_id = node_volume.id if node_volume else "missing"
        if node_volume_id == volume.id:
            volume = client.host_volumes.get(volume.id)[0]
            last_state = volume.state or "unknown"
            if volume.state == "ready":
                return volume
        index = qm.last_index
    module.fail_json(
        msg="volume %s did not become ready on node %s within %d seconds (last state: %s; node volume ID: %s)"
        % (volume.id, volume.node_id, module.params["timeout"], last_state, node_volume_id)
    )


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            **NOMAD_NAMESPACE_ARGUMENT_SPEC,
            **RESOURCE_SPEC,
            wait=dict(type="bool", default=True),
            timeout=dict(type="int", default=300),
            state=dict(type="str", choices=["present", "absent"], default="present"),
        ),
        supports_check_mode=True,
        required_if=[["state", "present", ["plugin_id", "host_path"], True]],
        mutually_exclusive=[["plugin_id", "host_path"]],
        required_by={"host_path": "node_id"},
    )
    p = module.params
    client = nomad_client(module)
    if client.config.namespace == "*":
        module.fail_json(msg="namespace must name one namespace, not *")
    with nomad_errors(module):
        current = find_volume(module, client)
        before = current.to_json() if current else {}

        if p["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.host_volumes.delete(current.id)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        wanted = apply_options(
            current,
            HostVolume,
            dict(
                name=p["name"],
                node_pool=p["node_pool"],
                node_id=p["node_id"],
                plugin_id=p["plugin_id"],
                host_path=p["host_path"],
                requested_capabilities=p["capabilities"],
                parameters=p["parameters"],
            ),
        )
        changed = current is None or differs(current, wanted)
        if changed and not module.check_mode:
            response = (client.host_volumes.register if p["host_path"] else client.host_volumes.create)(wanted)[0]
            wanted = response.volume
        if p["wait"] and not module.check_mode:
            wanted = wait_for_volume(module, client, wanted, time.monotonic() + p["timeout"])
        module.exit_json(changed=changed, volume=wanted.to_json(), diff=dict(before=before, after=wanted.to_json()))


if __name__ == "__main__":
    main()
