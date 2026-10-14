#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_variable
short_description: Manage a Nomad variable
version_added: 0.1.0
description:
  - Create, update or delete a variable at a path in a namespace.
  - The whole item set is compared and written; a key left out of O(items) is removed from the variable.
options:
  path:
    description: Path of the variable.
    type: str
    required: true
  items:
    description: Key-value items stored in the variable. Required when O(state=present).
    type: dict
  state:
    description: Whether the variable should exist.
    type: str
    choices: [present, absent]
    default: present
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
notes:
  - The returned document carries the item values. The diff carries a digest of each value, so it shows which items
    changed without showing what they hold.
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Store database credentials
  benemon.nomad.nomad_variable:
    path: db/credentials
    namespace: web
    items:
      username: app
      password: "{{ db_password }}"

- name: Delete the variable
  benemon.nomad.nomad_variable:
    path: db/credentials
    namespace: web
    state: absent
"""

RETURN = r"""
variable:
  description:
    - The variable as the Nomad API returns it, with the API's field names. C(Items) carries the values.
    - O(items) is C(no_log), so a value given there is shown as C(VALUE_SPECIFIED_IN_NO_LOG_PARAMETER) in the registered result.
  returned: when O(state=present)
  type: dict
  sample:
    Namespace: web
    Path: db/credentials
    Items:
      username: app
      password: secret
    CreateIndex: 12
    ModifyIndex: 12
    CreateTime: 1760000000000000000
    ModifyTime: 1760000000000000000
"""

import hashlib

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
    from nomadpy import Variable
except ImportError:
    pass


def fingerprinted(variable):
    """fingerprinted replaces each item value with a digest, so a diff shows what changed and never what it holds."""
    doc = variable.to_json()
    if doc.get("Items"):
        doc["Items"] = {k: "sha256:" + hashlib.sha256(v.encode()).hexdigest()[:12] for k, v in doc["Items"].items()}
    return doc


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            **NOMAD_NAMESPACE_ARGUMENT_SPEC,
            path=dict(type="str", required=True),
            items=dict(type="dict", no_log=True),
            state=dict(type="str", choices=["present", "absent"], default="present"),
        ),
        supports_check_mode=True,
        required_if=[["state", "present", ["items"]]],
    )
    client = nomad_client(module)
    path = module.params["path"]
    with nomad_errors(module):
        current = client.variables.peek(path)[0]
        before = fingerprinted(current) if current else {}

        if module.params["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.variables.delete(path)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        wanted = apply_options(current, Variable, dict(path=path, items=module.params["items"]))
        changed = current is None or differs(current, wanted)
        if changed and not module.check_mode:
            wanted = (client.variables.create if current is None else client.variables.update)(wanted)[0]
        module.exit_json(changed=changed, variable=wanted.to_json(), diff=dict(before=before, after=fingerprinted(wanted)))


if __name__ == "__main__":
    main()
