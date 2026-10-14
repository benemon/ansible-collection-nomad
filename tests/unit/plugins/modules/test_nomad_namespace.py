from unittest import mock

import pytest
from nomadpy import Namespace, NamespaceCapabilities, QueryMeta, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_namespace, nomad_namespace_info

from .conftest import Fail

WEB = Namespace(name="web", description="Web tier", capabilities=NamespaceCapabilities(enabled_task_drivers=["docker"]), create_index=5, modify_index=5)


def client(existing=None):
    c = mock.MagicMock()
    if existing is None:
        c.namespaces.info.side_effect = UnexpectedResponseError(404, body="Namespace not found")
    else:
        c.namespaces.info.return_value = (existing, QueryMeta())
    c.namespaces.register.return_value = WriteMeta()
    return c


def test_create(run):
    c = client()
    c.namespaces.info.side_effect = [UnexpectedResponseError(404), (WEB, QueryMeta())]
    result = run(nomad_namespace, dict(name="web", description="Web tier", capabilities=dict(enabled_task_drivers=["docker"])), c)
    assert result["changed"] is True
    sent = c.namespaces.register.call_args.args[0]
    assert sent == Namespace(name="web", description="Web tier", capabilities=NamespaceCapabilities(enabled_task_drivers=["docker"]))
    assert result["namespace"]["CreateIndex"] == 5
    assert result["diff"]["before"] == {}


def test_unchanged_when_set_options_match(run):
    c = client(WEB)
    result = run(nomad_namespace, dict(name="web", capabilities=dict(enabled_task_drivers=["docker"])), c)
    assert result["changed"] is False
    c.namespaces.register.assert_not_called()


def test_update_keeps_unset_fields(run):
    c = client(WEB)
    result = run(nomad_namespace, dict(name="web", description="Front door"), c)
    assert result["changed"] is True
    sent = c.namespaces.register.call_args.args[0]
    assert sent.description == "Front door" and sent.capabilities == WEB.capabilities


def test_check_mode_writes_nothing(run):
    c = client(WEB)
    result = run(nomad_namespace, dict(name="web", description="Front door"), c, check_mode=True)
    assert result["changed"] is True and result["namespace"]["Description"] == "Front door"
    c.namespaces.register.assert_not_called()


def test_absent(run):
    c = client(WEB)
    assert run(nomad_namespace, dict(name="web", state="absent"), c)["changed"] is True
    c.namespaces.delete.assert_called_once_with("web")
    assert run(nomad_namespace, dict(name="web", state="absent"), client())["changed"] is False


def test_server_error_fails_with_status(run):
    c = client(WEB)
    c.namespaces.register.side_effect = UnexpectedResponseError(500, body="quota not found")
    with pytest.raises(Fail) as e:
        run(nomad_namespace, dict(name="web", quota="q1"), c)
    assert e.value.args[0]["status_code"] == 500 and "quota not found" in e.value.args[0]["msg"]


def test_info(run):
    c = client(WEB)
    assert run(nomad_namespace_info, dict(name="web"), c)["namespaces"] == [WEB.to_json()]
    assert run(nomad_namespace_info, dict(name="web"), client())["namespaces"] == []
    c.namespaces.list.return_value = ([WEB], QueryMeta())
    assert run(nomad_namespace_info, dict(), c)["namespaces"] == [WEB.to_json()]
