#!/usr/bin/python
# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
module: nomad_acl_token_info
short_description: Read Nomad ACL tokens
version_added: 0.1.0
description:
  - Return the tokens the token can see, optionally narrowed to one accessor ID or name.
  - A token selected by O(accessor_id) or O(name) is returned in full, C(SecretID) included, as the API returns it.
    Without a selector the list endpoint's stubs are returned, which carry no secret.
options:
  accessor_id:
    description: Accessor ID of a single token to return. A token that does not exist returns an empty list.
    type: str
  name:
    description: Name of the tokens to return. Nomad does not keep names unique, so more than one may match.
    type: str
notes:
  - A result for a selected token is a secret. Set C(no_log) on the task, and register the result only when a later task
    needs the secret.
extends_documentation_fragment:
  - benemon.nomad.nomad
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: List every token
  benemon.nomad.nomad_acl_token_info:
  register: result

- name: Read the token named ci-reader, secret included
  benemon.nomad.nomad_acl_token_info:
    name: ci-reader
  register: result
  no_log: true
"""

RETURN = r"""
tokens:
  description:
    - Tokens as the Nomad API returns them, with the API's field names.
    - With O(accessor_id) or O(name), the full token documents, C(SecretID) included.
    - Without a selector, the list endpoint's stubs, which carry no C(SecretID) or C(ExpirationTTL) and name roles by ID only.
  returned: always
  type: list
  elements: dict
  sample:
    - AccessorID: bc91e81f-ac3a-8cbf-b9a1-f68de89f284d
      Name: ci-reader
      Type: client
      Policies: [read-default]
      Roles:
        - ID: 2876d4b6-7302-c0fb-4bf7-66e339eaa337
          Name: ""
      Global: false
      CreateTime: "2026-10-14T16:07:21.359687Z"
      ExpirationTime: "2026-10-15T16:07:21.359687Z"
      CreateIndex: 12
      ModifyIndex: 12
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import NOMAD_ARGUMENT_SPEC, nomad_client, nomad_errors, read_or_none


def main():
    module = AnsibleModule(
        argument_spec=dict(NOMAD_ARGUMENT_SPEC, accessor_id=dict(type="str"), name=dict(type="str")),
        supports_check_mode=True,
        mutually_exclusive=[["accessor_id", "name"]],
    )
    p = module.params
    client = nomad_client(module)
    with nomad_errors(module):
        if p["accessor_id"]:
            token = read_or_none(lambda: client.acl_tokens.info(p["accessor_id"]))
            tokens = [token] if token else []
        elif p["name"]:
            tokens = [client.acl_tokens.info(t.accessor_id)[0] for t in client.acl_tokens.list()[0] if t.name == p["name"]]
        else:
            tokens = client.acl_tokens.list()[0]
    module.exit_json(changed=False, tokens=[t.to_json() for t in tokens])


if __name__ == "__main__":
    main()
