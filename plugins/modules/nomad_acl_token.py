#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_acl_token
short_description: Manage a Nomad ACL token
description:
  - Create, update or delete an ACL token.
  - A token is selected by O(accessor_id) when given, otherwise by O(name). Nomad does not keep names unique, so a name
    that matches more than one token fails the task.
  - Only the options that are set are compared and written; an option left out keeps its current value on the server.
options:
  accessor_id:
    description:
      - Accessor ID of the token. The server assigns it, so a token that does not exist cannot be created by accessor ID.
    type: str
  name:
    description: Name of the token. Selects the token when O(accessor_id) is not given.
    type: str
  type:
    description: Type of the token. Required by the server when creating one.
    type: str
    choices: [client, management]
  policies:
    description: Names of the ACL policies granted to a client token.
    type: list
    elements: str
  roles:
    description: Names of the ACL roles granted to a client token.
    type: list
    elements: str
  global:
    description: Replicate the token to every region.
    type: bool
  expiration_ttl:
    description: Lifetime of the token as a Nomad duration, such as V(1h) or V(30m). The server computes the expiry from it at creation.
    type: str
  state:
    description: Whether the token should exist.
    type: str
    choices: [present, absent]
    default: present
notes:
  - The C(SecretID) is returned only by the task that creates the token. Later runs, including unchanged ones, never return it.
    Set C(no_log) on the creating task and register its result to capture the secret.
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Create a client token and keep its secret out of the log
  benemon.nomad.nomad_acl_token:
    name: ci-reader
    type: client
    policies: [read-default]
    roles: [readers]
    expiration_ttl: 24h
  register: token
  no_log: true

- name: Change the policies of a token by accessor ID
  benemon.nomad.nomad_acl_token:
    accessor_id: "{{ token.token.AccessorID }}"
    policies: [read-default, read-nodes]

- name: Delete the token by name
  benemon.nomad.nomad_acl_token:
    name: ci-reader
    state: absent
"""

RETURN = r"""
token:
  description:
    - The token as the Nomad API returns it, with the API's field names.
    - C(SecretID) is present only when this task created the token; every other result leaves it out.
  returned: when O(state=present)
  type: dict
  sample:
    AccessorID: bc91e81f-ac3a-8cbf-b9a1-f68de89f284d
    SecretID: b943d19d-fdb5-ebda-c3ac-d2df33919398
    Name: ci-reader
    Type: client
    Policies: [read-default]
    Roles:
      - ID: 2876d4b6-7302-c0fb-4bf7-66e339eaa337
        Name: readers
    Global: false
    CreateTime: "2026-10-14T16:07:21.359687Z"
    ExpirationTime: "2026-10-15T16:07:21.359687Z"
    ExpirationTTL: 24h0m0s
    CreateIndex: 12
    ModifyIndex: 12
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    NOMAD_ARGUMENT_SPEC,
    apply_options,
    differs,
    nomad_client,
    nomad_errors,
    read_or_none,
)

try:
    from nomadpy import ACLToken, ACLTokenRoleLink
    from nomadpy.models import parse_duration
except ImportError:
    pass


def redacted(token):
    doc = token.to_json()
    del doc["SecretID"]
    return doc


def main():
    module = AnsibleModule(
        argument_spec=dict(
            NOMAD_ARGUMENT_SPEC,
            accessor_id=dict(type="str"),
            name=dict(type="str"),
            type=dict(type="str", choices=["client", "management"]),
            policies=dict(type="list", elements="str"),
            roles=dict(type="list", elements="str"),
            expiration_ttl=dict(type="str"),
            state=dict(type="str", choices=["present", "absent"], default="present"),
            **{"global": dict(type="bool")},
        ),
        supports_check_mode=True,
        required_one_of=[["accessor_id", "name"]],
    )
    p = module.params
    client = nomad_client(module)
    with nomad_errors(module):
        if p["accessor_id"]:
            current = read_or_none(lambda: client.acl_tokens.info(p["accessor_id"]))
        else:
            stubs = [t for t in client.acl_tokens.list()[0] if t.name == p["name"]]
            if len(stubs) > 1:
                module.fail_json(msg="%d tokens are named %s; select one with accessor_id" % (len(stubs), p["name"]))
            current = client.acl_tokens.info(stubs[0].accessor_id)[0] if stubs else None
        before = redacted(current) if current else {}

        if p["state"] == "absent":
            if current is None:
                module.exit_json(changed=False)
            if not module.check_mode:
                client.acl_tokens.delete(current.accessor_id)
            module.exit_json(changed=True, diff=dict(before=before, after={}))

        if current is None and p["accessor_id"]:
            module.fail_json(msg="no token has accessor_id %s and the server assigns accessor IDs, so one cannot be created" % p["accessor_id"])
        # The server fills in both ID and Name on a role link, so a link built from the name alone would always differ.
        links = {r.name: r for r in current.roles or []} if current else {}
        wanted = apply_options(current, ACLToken, dict(
            name=p["name"],
            type=p["type"],
            policies=p["policies"],
            roles=None if p["roles"] is None else [links.get(r, ACLTokenRoleLink(name=r)) for r in p["roles"]],
            global_=p["global"],
            expiration_ttl=None if p["expiration_ttl"] is None else parse_duration(p["expiration_ttl"]),
        ))
        changed = current is None or differs(current, wanted)
        if not changed or module.check_mode:
            module.exit_json(changed=changed, token=redacted(wanted), diff=dict(before=before, after=redacted(wanted)))
        if current is None:
            created = client.acl_tokens.create(wanted)[0]
            module.exit_json(changed=True, token=created.to_json(), diff=dict(before={}, after=redacted(created)))
        updated = client.acl_tokens.update(wanted)[0]
        module.exit_json(changed=True, token=redacted(updated), diff=dict(before=before, after=redacted(updated)))


if __name__ == "__main__":
    main()
