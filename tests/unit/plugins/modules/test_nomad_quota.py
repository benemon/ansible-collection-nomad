from unittest import mock

import pytest
from nomadpy import NodePoolLimit, QueryMeta, QuotaLimit, QuotaResources, QuotaSpec, QuotaStorageResources, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_quota, nomad_quota_info

from .conftest import Fail

# As the server answers: unset limits are 0 and every limit carries a Hash.
STORED = QuotaResources(cpu=1000, cores=0, memory_mb=100, memory_max_mb=0, secrets_mb=0, storage=QuotaStorageResources(variables_mb=5),
                        node_pools=[NodePoolLimit(node_pool="default", cpu=0, cores=0, memory_mb=10, memory_max_mb=0, secrets_mb=0)])
WEB = QuotaSpec(name="web", description="Web tier", limits=[QuotaLimit(region="global", region_limit=STORED, variables_limit=5, hash="abc=")],
                create_index=5, modify_index=5)
LIMITS = [dict(region="global", region_limit=dict(cpu=1000, memory_mb=100, storage=dict(variables_mb=5), node_pools=[dict(node_pool="default", memory_mb=10)]),
               variables_limit=5)]


def client(existing=None):
    c = mock.MagicMock()
    if existing is None:
        c.quotas.info.side_effect = UnexpectedResponseError(404, body="quota not found")
    else:
        c.quotas.info.return_value = (existing, QueryMeta())
    c.quotas.register.return_value = WriteMeta()
    return c


def test_create(run):
    c = client()
    c.quotas.info.side_effect = [UnexpectedResponseError(404), (WEB, QueryMeta())]
    result = run(nomad_quota, dict(name="web", description="Web tier", limits=LIMITS), c)
    assert result["changed"] is True
    sent = c.quotas.register.call_args.args[0]
    assert sent.limits == [QuotaLimit(region="global", region_limit=STORED, variables_limit=5)]
    assert result["quota"]["CreateIndex"] == 5
    assert result["diff"]["before"] == {}


def test_unchanged_when_set_options_match(run):
    c = client(WEB)
    result = run(nomad_quota, dict(name="web", limits=LIMITS), c)
    assert result["changed"] is False
    c.quotas.register.assert_not_called()


def test_update_keeps_unset_fields(run):
    c = client(WEB)
    result = run(nomad_quota, dict(name="web", description="Front door"), c)
    assert result["changed"] is True
    sent = c.quotas.register.call_args.args[0]
    assert sent.description == "Front door" and sent.limits == WEB.limits


def test_check_mode_writes_nothing(run):
    c = client(WEB)
    result = run(nomad_quota, dict(name="web", limits=[dict(region="global", region_limit=dict(cpu=2000))]), c, check_mode=True)
    assert result["changed"] is True and result["quota"]["Limits"][0]["RegionLimit"]["CPU"] == 2000
    c.quotas.register.assert_not_called()


def test_absent(run):
    c = client(WEB)
    assert run(nomad_quota, dict(name="web", state="absent"), c)["changed"] is True
    c.quotas.delete.assert_called_once_with("web")
    assert run(nomad_quota, dict(name="web", state="absent"), client())["changed"] is False


def test_server_error_fails_with_status(run):
    c = client()
    c.quotas.info.side_effect = UnexpectedResponseError(501, body="Nomad Enterprise only endpoint")
    with pytest.raises(Fail) as e:
        run(nomad_quota, dict(name="web", limits=LIMITS), c)
    assert e.value.args[0]["status_code"] == 501 and "Enterprise only" in e.value.args[0]["msg"]


def test_info(run):
    c = client(WEB)
    assert run(nomad_quota_info, dict(name="web"), c)["quotas"] == [WEB.to_json()]
    assert run(nomad_quota_info, dict(name="web"), client())["quotas"] == []
    c.quotas.list.return_value = ([WEB], QueryMeta())
    assert run(nomad_quota_info, dict(), c)["quotas"] == [WEB.to_json()]
