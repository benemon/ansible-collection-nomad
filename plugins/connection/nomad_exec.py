# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
name: nomad_exec
short_description: Run tasks inside a task of a Nomad allocation
version_added: 0.2.0
description:
  - Runs each command in a task of a running allocation over the Nomad exec API, through the server, the way C(nomad alloc exec) does.
  - Files travel over the same channel, as C(cat) with its stdin or stdout, so the task needs a POSIX shell and C(cat), and
    Python where modules run.
  - Commands run as the task's user. Privilege escalation is not supported.
author:
  - Benjamin Holmes (@benemon)
requirements:
  - nomadpy[exec] >= 0.2.0
options:
  alloc_id:
    description:
      - ID of the allocation, in full.
      - The P(benemon.nomad.nomad#inventory) inventory plugin sets it on allocation hosts.
    type: str
    vars:
      - name: ansible_nomad_alloc_id
  task:
    description:
      - Name of the task to run in.
      - Set it in the play, or compose it from C(nomad_allocation.TaskStates) on the hosts of the P(benemon.nomad.nomad#inventory) inventory plugin.
    type: str
    vars:
      - name: ansible_nomad_task
  namespace:
    description:
      - Namespace of the allocation.
      - Falls back to E(NOMAD_NAMESPACE), then V(default).
    type: str
    vars:
      - name: ansible_nomad_namespace
    env:
      - name: NOMAD_NAMESPACE
  timeout:
    description:
      - Seconds to wait for the exec connection to open and for each frame of output.
      - Unset, a wait has no bound.
    type: float
    vars:
      - name: ansible_nomad_timeout
  address:
    description:
      - Address of the Nomad HTTP API, including the scheme.
      - Falls back to E(NOMAD_ADDR), then V(http://127.0.0.1:4646).
    type: str
    vars:
      - name: ansible_nomad_address
    env:
      - name: NOMAD_ADDR
  token:
    description:
      - ACL token secret sent with every request.
      - Falls back to E(NOMAD_TOKEN).
    type: str
    vars:
      - name: ansible_nomad_token
    env:
      - name: NOMAD_TOKEN
  region:
    description:
      - Region to send requests to.
      - Falls back to E(NOMAD_REGION), then the region of the server answering.
    type: str
    vars:
      - name: ansible_nomad_region
    env:
      - name: NOMAD_REGION
  ca_cert:
    description:
      - Path to a CA certificate file to verify the server against.
      - Falls back to E(NOMAD_CACERT).
    type: path
    vars:
      - name: ansible_nomad_ca_cert
    env:
      - name: NOMAD_CACERT
  ca_path:
    description:
      - Path to a directory of CA certificates to verify the server against.
      - Falls back to E(NOMAD_CAPATH).
    type: path
    vars:
      - name: ansible_nomad_ca_path
    env:
      - name: NOMAD_CAPATH
  client_cert:
    description:
      - Path to the client certificate for TLS authentication.
      - Falls back to E(NOMAD_CLIENT_CERT).
    type: path
    vars:
      - name: ansible_nomad_client_cert
    env:
      - name: NOMAD_CLIENT_CERT
  client_key:
    description:
      - Path to the private key of O(client_cert).
      - Falls back to E(NOMAD_CLIENT_KEY).
    type: path
    vars:
      - name: ansible_nomad_client_key
    env:
      - name: NOMAD_CLIENT_KEY
  tls_server_name:
    description:
      - Server name to verify the certificate against instead of the host in O(address).
      - Falls back to E(NOMAD_TLS_SERVER_NAME).
    type: str
    vars:
      - name: ansible_nomad_tls_server_name
    env:
      - name: NOMAD_TLS_SERVER_NAME
  skip_verify:
    description:
      - Do not verify the server certificate.
      - Falls back to E(NOMAD_SKIP_VERIFY).
    type: bool
    vars:
      - name: ansible_nomad_skip_verify
    env:
      - name: NOMAD_SKIP_VERIFY
notes:
  - Enterprise features are not checked client-side. On a Community server the request fails with the server's own error.
"""

EXAMPLES = r"""
# With an inventory from the benemon.nomad.nomad plugin (allocations: true), allocation hosts already carry
# ansible_nomad_alloc_id and ansible_nomad_namespace; the task is named in the play.
- hosts: nomad_job_web
  connection: benemon.nomad.nomad_exec
  vars:
    ansible_nomad_task: web
    ansible_nomad_address: https://nomad.example.com:4646
    ansible_nomad_token: "{{ nomad_token }}"
  tasks:
    - ansible.builtin.command: cat /etc/hostname

# A host added by hand
- hosts: localhost
  gather_facts: false
  tasks:
    - ansible.builtin.add_host:
        name: web-alloc
        ansible_connection: benemon.nomad.nomad_exec
        ansible_nomad_alloc_id: 8b5e7a4e-2b1d-6f0c-9a3e-0d1f2a3b4c5d
        ansible_nomad_task: web
"""

import io
import os
import shlex
import urllib.error

from ansible.errors import AnsibleConnectionFailure, AnsibleError, AnsibleFileNotFound
from ansible.module_utils.basic import missing_required_lib
from ansible.plugins.connection import ConnectionBase

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    HAS_NOMADPY,
    NOMAD_ARGUMENT_SPEC,
    NOMADPY_IMPORT_ERROR,
    client_from_options,
)

try:
    from nomadpy import QueryOptions, UnexpectedResponseError
except ImportError:
    pass


class Connection(ConnectionBase):
    transport = "benemon.nomad.nomad_exec"
    has_pipelining = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None

    def _connect(self):
        if not self._connected:
            if not HAS_NOMADPY:
                raise AnsibleConnectionFailure(missing_required_lib("nomadpy") + "\n" + NOMADPY_IMPORT_ERROR)
            for name in ("alloc_id", "task"):
                if not self.get_option(name):
                    raise AnsibleConnectionFailure("ansible_nomad_%s is not set" % name)
            self._client = client_from_options({name: self.get_option(name) for name in NOMAD_ARGUMENT_SPEC})
            self._connected = True
        return self

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super().exec_command(cmd, in_data=in_data, sudoable=sudoable)
        stdout, stderr = io.BytesIO(), io.BytesIO()
        rc = self._exec([self._play_context.executable, "-c", cmd], io.BytesIO(in_data) if in_data else None, stdout, stderr)
        return rc, stdout.getvalue(), stderr.getvalue()

    def put_file(self, in_path, out_path):
        super().put_file(in_path, out_path)
        if not os.path.exists(in_path):
            raise AnsibleFileNotFound("file or module does not exist: %s" % in_path)
        stderr = io.BytesIO()
        with open(in_path, "rb") as source:
            rc = self._exec([self._play_context.executable, "-c", "cat > " + shlex.quote(out_path)], source, None, stderr)
        if rc:
            raise AnsibleError("failed to transfer file to %s: %s" % (out_path, stderr.getvalue().decode(errors="replace").strip()))

    def fetch_file(self, in_path, out_path):
        super().fetch_file(in_path, out_path)
        stderr = io.BytesIO()
        with open(out_path, "wb") as target:
            rc = self._exec([self._play_context.executable, "-c", "cat " + shlex.quote(in_path)], None, target, stderr)
        if rc:
            raise AnsibleError("failed to fetch file %s: %s" % (in_path, stderr.getvalue().decode(errors="replace").strip()))

    def _exec(self, command, stdin, stdout, stderr):
        alloc_id = self.get_option("alloc_id")
        namespace = self.get_option("namespace")
        try:
            return self._client.allocations.exec(alloc_id, self.get_option("task"), command, stdin=stdin, stdout=stdout, stderr=stderr,
                                                 q=QueryOptions(namespace=namespace) if namespace else None, timeout=self.get_option("timeout"))
        except UnexpectedResponseError as e:
            raise AnsibleConnectionFailure("exec in allocation %s: %s" % (alloc_id, e)) from e
        except urllib.error.URLError as e:
            raise AnsibleConnectionFailure("cannot reach Nomad: %s" % e.reason) from e
        except (ConnectionError, TimeoutError, ImportError) as e:
            raise AnsibleConnectionFailure("exec in allocation %s: %s" % (alloc_id, e)) from e

    def close(self):
        self._connected = False
