from unittest import mock

import pytest
from nomadpy import ACLPolicy, ACLPolicyListStub, JobACL, QueryMeta, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_acl_policy, nomad_acl_policy_info

from .conftest import Fail

RULES = 'namespace "default" { policy = "read" }'
READ = ACLPolicy(name="read-default", description="Read default", rules=RULES, job_acl=JobACL(namespace="default", job_id="web"),
                 create_index=5, modify_index=5)


def client(existing=None):
    c = mock.MagicMock()
    if existing is None:
        c.acl_policies.info.side_effect = UnexpectedResponseError(404, body="ACL policy not found")
    else:
        c.acl_policies.info.return_value = (existing, QueryMeta())
    c.acl_policies.upsert.return_value = WriteMeta()
    return c


def test_create(run):
    c = client()
    c.acl_policies.info.side_effect = [UnexpectedResponseError(404), (READ, QueryMeta())]
    result = run(nomad_acl_policy, dict(name="read-default", description="Read default", rules=RULES, job_acl=dict(namespace="default", job_id="web")), c)
    assert result["changed"] is True
    sent = c.acl_policies.upsert.call_args.args[0]
    assert sent == ACLPolicy(name="read-default", description="Read default", rules=RULES, job_acl=JobACL(namespace="default", job_id="web"))
    assert result["policy"]["CreateIndex"] == 5
    assert result["diff"]["before"] == {}


def test_unchanged_when_set_options_match(run):
    c = client(READ)
    result = run(nomad_acl_policy, dict(name="read-default", rules=RULES, job_acl=dict(namespace="default", job_id="web")), c)
    assert result["changed"] is False
    c.acl_policies.upsert.assert_not_called()


def test_update_keeps_unset_fields(run):
    c = client(READ)
    result = run(nomad_acl_policy, dict(name="read-default", description="Readers"), c)
    assert result["changed"] is True
    sent = c.acl_policies.upsert.call_args.args[0]
    assert sent.description == "Readers" and sent.rules == RULES and sent.job_acl == READ.job_acl


def test_check_mode_writes_nothing(run):
    c = client(READ)
    result = run(nomad_acl_policy, dict(name="read-default", description="Readers"), c, check_mode=True)
    assert result["changed"] is True and result["policy"]["Description"] == "Readers"
    c.acl_policies.upsert.assert_not_called()


def test_absent(run):
    c = client(READ)
    assert run(nomad_acl_policy, dict(name="read-default", state="absent"), c)["changed"] is True
    c.acl_policies.delete.assert_called_once_with("read-default")
    assert run(nomad_acl_policy, dict(name="read-default", state="absent"), client())["changed"] is False


def test_server_error_fails_with_status(run):
    c = client(READ)
    c.acl_policies.upsert.side_effect = UnexpectedResponseError(400, body="failed to parse rules")
    with pytest.raises(Fail) as e:
        run(nomad_acl_policy, dict(name="read-default", rules="nonsense"), c)
    assert e.value.args[0]["status_code"] == 400 and "failed to parse rules" in e.value.args[0]["msg"]


def test_info(run):
    c = client(READ)
    assert run(nomad_acl_policy_info, dict(name="read-default"), c)["policies"] == [READ.to_json()]
    assert run(nomad_acl_policy_info, dict(name="read-default"), client())["policies"] == []
    stub = ACLPolicyListStub(name="read-default", description="Read default", create_index=5, modify_index=5)
    c.acl_policies.list.return_value = ([stub], QueryMeta())
    assert run(nomad_acl_policy_info, dict(), c)["policies"] == [stub.to_json()]
