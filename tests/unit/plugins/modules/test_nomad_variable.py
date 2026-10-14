from unittest import mock

import pytest
from nomadpy import QueryMeta, UnexpectedResponseError, Variable, VariableMetadata, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_variable, nomad_variable_info

from .conftest import Fail

CREDS = Variable(namespace="default", path="db/credentials", items={"username": "app", "password": "s3cret"}, create_index=5, modify_index=5)


def client(existing=None):
    c = mock.MagicMock()
    c.variables.peek.return_value = (existing, QueryMeta())
    c.variables.create.return_value = (existing, WriteMeta())
    c.variables.update.return_value = (existing, WriteMeta())
    return c


def test_create(run):
    c = client()
    c.variables.create.return_value = (CREDS, WriteMeta())
    result = run(nomad_variable, dict(path="db/credentials", items=dict(username="app", password="s3cret")), c)
    assert result["changed"] is True
    c.variables.read.assert_not_called()
    assert c.variables.create.call_args.args[0] == Variable(path="db/credentials", items={"username": "app", "password": "s3cret"})
    c.variables.update.assert_not_called()
    assert result["variable"]["Items"] == {"username": "app", "password": "s3cret"} and result["variable"]["CreateIndex"] == 5
    assert result["diff"]["before"] == {}
    assert result["diff"]["after"]["Items"]["password"].startswith("sha256:") and "s3cret" not in str(result["diff"])


def test_unchanged_when_items_match(run):
    c = client(CREDS)
    result = run(nomad_variable, dict(path="db/credentials", items=dict(username="app", password="s3cret")), c)
    assert result["changed"] is False
    c.variables.create.assert_not_called()
    c.variables.update.assert_not_called()


def test_update_replaces_items_and_keeps_metadata(run):
    c = client(CREDS)
    result = run(nomad_variable, dict(path="db/credentials", items=dict(username="app")), c)
    assert result["changed"] is True
    sent = c.variables.update.call_args.args[0]
    assert sent.items == {"username": "app"} and sent.modify_index == 5 and sent.namespace == "default"
    c.variables.create.assert_not_called()


def test_check_mode_writes_nothing(run):
    c = client(CREDS)
    result = run(nomad_variable, dict(path="db/credentials", items=dict(username="app")), c, check_mode=True)
    assert result["changed"] is True and result["variable"]["Items"] == {"username": "app"}
    assert result["diff"]["before"]["Items"].keys() == CREDS.items.keys() and "s3cret" not in str(result["diff"])
    c.variables.update.assert_not_called()


def test_absent(run):
    c = client(CREDS)
    assert run(nomad_variable, dict(path="db/credentials", state="absent"), c)["changed"] is True
    c.variables.delete.assert_called_once_with("db/credentials")
    assert run(nomad_variable, dict(path="db/credentials", state="absent"), client())["changed"] is False
    c = client(CREDS)
    assert run(nomad_variable, dict(path="db/credentials", state="absent"), c, check_mode=True)["changed"] is True
    c.variables.delete.assert_not_called()


def test_present_requires_items(run):
    with pytest.raises(Fail):
        run(nomad_variable, dict(path="db/credentials"), client())


def test_server_error_fails_with_status(run):
    c = client()
    c.variables.create.side_effect = UnexpectedResponseError(403, body="Permission denied")
    with pytest.raises(Fail) as e:
        run(nomad_variable, dict(path="db/credentials", items=dict(a="b")), c)
    assert e.value.args[0]["status_code"] == 403 and "Permission denied" in e.value.args[0]["msg"]


def test_info(run):
    c = client(CREDS)
    assert run(nomad_variable_info, dict(path="db/credentials"), c)["variables"] == [CREDS.to_json()]
    assert run(nomad_variable_info, dict(path="db/credentials"), client())["variables"] == []
    stub = CREDS.metadata()
    c.variables.list.return_value = ([stub], QueryMeta())
    assert run(nomad_variable_info, dict(), c)["variables"] == [stub.to_json()]
    c.variables.prefix_list.return_value = ([VariableMetadata(path="db/other")], QueryMeta())
    assert run(nomad_variable_info, dict(prefix="db/"), c)["variables"] == [VariableMetadata(path="db/other").to_json()]
    c.variables.prefix_list.assert_called_once_with("db/")
