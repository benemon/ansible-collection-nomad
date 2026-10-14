from unittest import mock

import pytest
from nomadpy import ACLRole, ACLRoleListStub, ACLRolePolicyLink, QueryMeta, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_acl_role, nomad_acl_role_info

from .conftest import Fail

READERS = ACLRole(id="r-1", name="readers", description="Readers", policies=[ACLRolePolicyLink(name="read-default")], create_index=5, modify_index=5)


def client(existing=None):
    c = mock.MagicMock()
    if existing is None:
        c.acl_roles.get_by_name.side_effect = UnexpectedResponseError(404, body="ACL role not found")
    else:
        c.acl_roles.get_by_name.return_value = (existing, QueryMeta())
    c.acl_roles.create.return_value = (READERS, WriteMeta())
    c.acl_roles.update.return_value = (READERS, WriteMeta())
    return c


def test_create(run):
    c = client()
    result = run(nomad_acl_role, dict(name="readers", description="Readers", policies=["read-default"]), c)
    assert result["changed"] is True
    sent = c.acl_roles.create.call_args.args[0]
    assert sent == ACLRole(name="readers", description="Readers", policies=[ACLRolePolicyLink(name="read-default")])
    c.acl_roles.update.assert_not_called()
    assert result["role"]["ID"] == "r-1"
    assert result["diff"]["before"] == {}


def test_unchanged_when_set_options_match(run):
    c = client(READERS)
    result = run(nomad_acl_role, dict(name="readers", policies=["read-default"]), c)
    assert result["changed"] is False
    c.acl_roles.create.assert_not_called()
    c.acl_roles.update.assert_not_called()


def test_update_keeps_unset_fields(run):
    c = client(READERS)
    result = run(nomad_acl_role, dict(name="readers", description="Read-only operators"), c)
    assert result["changed"] is True
    sent = c.acl_roles.update.call_args.args[0]
    assert sent.id == "r-1" and sent.description == "Read-only operators" and sent.policies == READERS.policies
    c.acl_roles.create.assert_not_called()


def test_check_mode_writes_nothing(run):
    c = client(READERS)
    result = run(nomad_acl_role, dict(name="readers", description="Read-only operators"), c, check_mode=True)
    assert result["changed"] is True and result["role"]["Description"] == "Read-only operators"
    c.acl_roles.update.assert_not_called()


def test_absent(run):
    c = client(READERS)
    assert run(nomad_acl_role, dict(name="readers", state="absent"), c)["changed"] is True
    c.acl_roles.delete.assert_called_once_with("r-1")
    assert run(nomad_acl_role, dict(name="readers", state="absent"), client())["changed"] is False


def test_server_error_fails_with_status(run):
    c = client()
    c.acl_roles.create.side_effect = UnexpectedResponseError(400, body="ACL policy not found")
    with pytest.raises(Fail) as e:
        run(nomad_acl_role, dict(name="readers", policies=["missing"]), c)
    assert e.value.args[0]["status_code"] == 400 and "ACL policy not found" in e.value.args[0]["msg"]


def test_info(run):
    c = client(READERS)
    assert run(nomad_acl_role_info, dict(name="readers"), c)["roles"] == [READERS.to_json()]
    assert run(nomad_acl_role_info, dict(name="readers"), client())["roles"] == []
    c.acl_roles.get.return_value = (READERS, QueryMeta())
    assert run(nomad_acl_role_info, dict(id="r-1"), c)["roles"] == [READERS.to_json()]
    c.acl_roles.get.assert_called_once_with("r-1")
    stub = ACLRoleListStub(id="r-1", name="readers", description="Readers", policies=READERS.policies, create_index=5, modify_index=5)
    c.acl_roles.list.return_value = ([stub], QueryMeta())
    assert run(nomad_acl_role_info, dict(), c)["roles"] == [stub.to_json()]
