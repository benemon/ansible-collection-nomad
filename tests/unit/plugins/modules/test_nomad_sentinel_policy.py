from unittest import mock

import pytest
from nomadpy import QueryMeta, SentinelPolicy, SentinelPolicyListStub, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_sentinel_policy, nomad_sentinel_policy_info

from .conftest import Fail

ALLOW = SentinelPolicy(name="allow", description="Allow all", scope="submit-job", enforcement_level="advisory", policy="main = rule { true }",
                       create_index=5, modify_index=5)


def client(existing=None):
    c = mock.MagicMock()
    if existing is None:
        c.sentinel_policies.info.side_effect = UnexpectedResponseError(404, body="policy not found")
    else:
        c.sentinel_policies.info.return_value = (existing, QueryMeta())
    c.sentinel_policies.upsert.return_value = WriteMeta()
    return c


def test_create(run):
    c = client()
    c.sentinel_policies.info.side_effect = [UnexpectedResponseError(404), (ALLOW, QueryMeta())]
    result = run(nomad_sentinel_policy, dict(name="allow", description="Allow all", scope="submit-job", enforcement_level="advisory",
                                             policy="main = rule { true }"), c)
    assert result["changed"] is True
    sent = c.sentinel_policies.upsert.call_args.args[0]
    assert sent == SentinelPolicy(name="allow", description="Allow all", scope="submit-job", enforcement_level="advisory", policy="main = rule { true }")
    assert result["sentinel_policy"]["CreateIndex"] == 5
    assert result["diff"]["before"] == {}


def test_unchanged_when_set_options_match(run):
    c = client(ALLOW)
    result = run(nomad_sentinel_policy, dict(name="allow", scope="submit-job", policy="main = rule { true }"), c)
    assert result["changed"] is False
    c.sentinel_policies.upsert.assert_not_called()


def test_update_keeps_unset_fields(run):
    c = client(ALLOW)
    result = run(nomad_sentinel_policy, dict(name="allow", enforcement_level="hard-mandatory"), c)
    assert result["changed"] is True
    sent = c.sentinel_policies.upsert.call_args.args[0]
    assert sent.enforcement_level == "hard-mandatory" and sent.policy == ALLOW.policy and sent.scope == ALLOW.scope


def test_check_mode_writes_nothing(run):
    c = client(ALLOW)
    result = run(nomad_sentinel_policy, dict(name="allow", description="Permissive"), c, check_mode=True)
    assert result["changed"] is True and result["sentinel_policy"]["Description"] == "Permissive"
    c.sentinel_policies.upsert.assert_not_called()


def test_absent(run):
    c = client(ALLOW)
    assert run(nomad_sentinel_policy, dict(name="allow", state="absent"), c)["changed"] is True
    c.sentinel_policies.delete.assert_called_once_with("allow")
    assert run(nomad_sentinel_policy, dict(name="allow", state="absent"), client())["changed"] is False


def test_server_error_fails_with_status(run):
    c = client()
    c.sentinel_policies.info.side_effect = UnexpectedResponseError(501, body="Nomad Enterprise only endpoint")
    with pytest.raises(Fail) as e:
        run(nomad_sentinel_policy, dict(name="allow", policy="main = rule { true }"), c)
    assert e.value.args[0]["status_code"] == 501 and "Enterprise only" in e.value.args[0]["msg"]


def test_info(run):
    c = client(ALLOW)
    assert run(nomad_sentinel_policy_info, dict(name="allow"), c)["sentinel_policies"] == [ALLOW.to_json()]
    assert run(nomad_sentinel_policy_info, dict(name="allow"), client())["sentinel_policies"] == []
    stub = SentinelPolicyListStub(name="allow", scope="submit-job", enforcement_level="advisory", create_index=5, modify_index=5)
    c.sentinel_policies.list.return_value = ([stub], QueryMeta())
    assert run(nomad_sentinel_policy_info, dict(), c)["sentinel_policies"] == [stub.to_json()]
