# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
name: nomad_variable
short_description: Read a Nomad variable
description:
  - Return the items of a variable, or one item of it, read inline.
  - A variable that does not exist is an error.
options:
  _terms:
    description: Paths of the variables to read.
    type: list
    elements: str
    required: true
  key:
    description: Return only this item's value instead of the items dict. An item that does not exist is an error.
    type: str
extends_documentation_fragment:
  - benemon.nomad.nomad
  - benemon.nomad.nomad.namespace
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
- name: Read every item of a variable
  ansible.builtin.debug:
    msg: "{{ lookup('benemon.nomad.nomad_variable', 'db/credentials', namespace='web') }}"

- name: Read one item
  ansible.builtin.debug:
    msg: "{{ lookup('benemon.nomad.nomad_variable', 'db/credentials', key='username') }}"
"""

RETURN = r"""
_raw:
  description: The item dictionary of each path, or the value of O(key) in each.
  type: list
  elements: raw
"""

import urllib.error

from ansible.errors import AnsibleError
from ansible.module_utils.basic import missing_required_lib
from ansible.plugins.lookup import LookupBase

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    HAS_NOMADPY,
    NOMAD_ARGUMENT_SPEC,
    NOMADPY_IMPORT_ERROR,
    client_from_options,
)

try:
    from nomadpy import UnexpectedResponseError
except ImportError:
    pass

CONNECTION_OPTIONS = (*NOMAD_ARGUMENT_SPEC, "namespace")


class LookupModule(LookupBase):
    def run(self, terms, variables=None, **kwargs):
        if not HAS_NOMADPY:
            raise AnsibleError(missing_required_lib("nomadpy") + "\n" + NOMADPY_IMPORT_ERROR)
        self.set_options(var_options=variables, direct=kwargs)
        client = client_from_options({name: self.get_option(name) for name in CONNECTION_OPTIONS})
        key = self.get_option("key")
        results = []
        for path in terms:
            try:
                variable = client.variables.peek(path)[0]
            except UnexpectedResponseError as e:
                raise AnsibleError("reading variable %s: %s" % (path, e)) from e
            except urllib.error.URLError as e:
                raise AnsibleError("cannot reach Nomad: %s" % e.reason) from e
            if variable is None:
                raise AnsibleError("variable %s not found" % path)
            items = variable.items or {}
            if key is None:
                results.append(items)
            elif key in items:
                results.append(items[key])
            else:
                raise AnsibleError("variable %s has no item %s" % (path, key))
        return results
