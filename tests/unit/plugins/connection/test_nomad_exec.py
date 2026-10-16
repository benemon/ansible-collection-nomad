from unittest import mock

import pytest
from ansible.errors import AnsibleConnectionFailure, AnsibleError
from ansible.playbook.play_context import PlayContext
from ansible.plugins.loader import connection_loader
from nomadpy import UnexpectedResponseError

from ansible_collections.benemon.nomad.plugins.module_utils import nomad as module_utils

HOST = {"ansible_nomad_alloc_id": "a1", "ansible_nomad_task": "t", "ansible_nomad_address": "http://option:4646", "ansible_nomad_token": "tok"}


def connection(client, **variables):
    conn = connection_loader.get("benemon.nomad.nomad_exec", PlayContext())
    conn.set_options(var_options={**HOST, **variables})
    with mock.patch.object(module_utils.nomadpy, "Client", return_value=client) as cls:
        conn._connect()
    return conn, cls.call_args.args[0]


def exec_returning(rc, out=b"", err=b""):
    def _exec(alloc_id, task, command, *, stdin=None, stdout=None, stderr=None, q=None, timeout=None):
        if stdout is not None:
            stdout.write(out)
        if stderr is not None:
            stderr.write(err)
        return rc
    return mock.MagicMock(side_effect=_exec)


def test_exec_command():
    client = mock.MagicMock()
    client.allocations.exec = exec_returning(3, b"hello\n", b"oops\n")
    conn, config = connection(client, ansible_nomad_namespace="web", ansible_nomad_exec_timeout=30)
    assert config.address == "http://option:4646" and config.secret_id == "tok"
    assert conn.exec_command("echo hello", in_data=b"input") == (3, b"hello\n", b"oops\n")
    alloc_id, task, command = client.allocations.exec.call_args.args
    kwargs = client.allocations.exec.call_args.kwargs
    assert (alloc_id, task, command) == ("a1", "t", ["/bin/sh", "-c", "echo hello"])
    assert kwargs["stdin"].getvalue() == b"input" and kwargs["q"].namespace == "web" and kwargs["timeout"] == 30


def test_no_stdin_without_in_data():
    client = mock.MagicMock()
    client.allocations.exec = exec_returning(0)
    conn, _config = connection(client)
    conn.exec_command("true")
    assert client.allocations.exec.call_args.kwargs["stdin"] is None and client.allocations.exec.call_args.kwargs["q"] is None


def test_put_file(tmp_path):
    source = tmp_path / "in.bin"
    source.write_bytes(b"\x00\xff payload")
    client = mock.MagicMock()
    seen = {}

    def _exec(alloc_id, task, command, *, stdin=None, stdout=None, stderr=None, q=None, timeout=None):
        seen["command"], seen["data"] = command, stdin.read()
        return 0
    client.allocations.exec = mock.MagicMock(side_effect=_exec)
    conn, _config = connection(client)
    conn.put_file(str(source), "/opt/app/it's here")
    assert seen == {"command": ["/bin/sh", "-c", "cat > '/opt/app/it'\"'\"'s here'"], "data": b"\x00\xff payload"}


def test_put_file_failure_carries_stderr(tmp_path):
    source = tmp_path / "in.bin"
    source.write_bytes(b"x")
    client = mock.MagicMock()
    client.allocations.exec = exec_returning(1, err=b"sh: cannot create /ro/x: Read-only file system\n")
    conn, _config = connection(client)
    with pytest.raises(AnsibleError, match="Read-only file system"):
        conn.put_file(str(source), "/ro/x")


def test_fetch_file(tmp_path):
    client = mock.MagicMock()
    client.allocations.exec = exec_returning(0, out=b"remote bytes")
    conn, _config = connection(client)
    conn.fetch_file("/etc/motd", str(tmp_path / "motd"))
    assert (tmp_path / "motd").read_bytes() == b"remote bytes"
    assert client.allocations.exec.call_args.args[2] == ["/bin/sh", "-c", "cat /etc/motd"]


def test_missing_host_options():
    conn = connection_loader.get("benemon.nomad.nomad_exec", PlayContext())
    conn.set_options(var_options={"ansible_nomad_alloc_id": "a1"})
    with pytest.raises(AnsibleConnectionFailure, match="ansible_nomad_task is not set"):
        conn._connect()


def test_server_error_is_a_connection_failure():
    client = mock.MagicMock()
    client.allocations.exec.side_effect = UnexpectedResponseError(403, body="Permission denied")
    conn, _config = connection(client)
    with pytest.raises(AnsibleConnectionFailure, match="403.*Permission denied"):
        conn.exec_command("true")


def test_timeout_unset_ignores_the_connection_timeout_keyword():
    client = mock.MagicMock()
    client.allocations.exec = exec_returning(0)
    conn = connection_loader.get("benemon.nomad.nomad_exec", PlayContext())
    conn.set_options(task_keys={"timeout": 10}, var_options=HOST)
    with mock.patch.object(module_utils.nomadpy, "Client", return_value=client):
        conn._connect()
    conn.exec_command("true")
    assert client.allocations.exec.call_args.kwargs["timeout"] is None
