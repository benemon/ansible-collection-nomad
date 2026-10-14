from unittest import mock

import pytest
from nomadpy import NodePool, NodePoolSchedulerConfiguration, QueryMeta, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_node_pool, nomad_node_pool_info

from .conftest import Fail

HOUR = 3600 * 10**9
GPU = NodePool(name="gpu", description="GPU nodes", meta={"tier": "compute"}, node_identity_ttl=24 * HOUR, create_index=5, modify_index=5)


def client(existing=None):
    c = mock.MagicMock()
    if existing is None:
        c.node_pools.info.side_effect = UnexpectedResponseError(404, body="node pool not found")
    else:
        c.node_pools.info.return_value = (existing, QueryMeta())
    c.node_pools.register.return_value = WriteMeta()
    return c


def test_create(run):
    c = client()
    c.node_pools.info.side_effect = [UnexpectedResponseError(404), (GPU, QueryMeta())]
    result = run(nomad_node_pool, dict(name="gpu", description="GPU nodes", meta=dict(tier="compute"), node_identity_ttl="1h"), c)
    assert result["changed"] is True
    sent = c.node_pools.register.call_args.args[0]
    assert sent == NodePool(name="gpu", description="GPU nodes", meta={"tier": "compute"}, node_identity_ttl=HOUR)
    assert result["node_pool"]["CreateIndex"] == 5
    assert result["diff"]["before"] == {}


def test_unchanged_when_set_options_match(run):
    c = client(GPU)
    result = run(nomad_node_pool, dict(name="gpu", meta=dict(tier="compute"), node_identity_ttl="24h"), c)
    assert result["changed"] is False
    c.node_pools.register.assert_not_called()


def test_update_keeps_unset_fields(run):
    c = client(GPU)
    result = run(nomad_node_pool, dict(name="gpu", scheduler_configuration=dict(scheduler_algorithm="spread")), c)
    assert result["changed"] is True
    sent = c.node_pools.register.call_args.args[0]
    assert sent.scheduler_configuration == NodePoolSchedulerConfiguration(scheduler_algorithm="spread")
    assert sent.meta == GPU.meta and sent.node_identity_ttl == 24 * HOUR


def test_check_mode_writes_nothing(run):
    c = client(GPU)
    result = run(nomad_node_pool, dict(name="gpu", description="Accelerators"), c, check_mode=True)
    assert result["changed"] is True and result["node_pool"]["Description"] == "Accelerators"
    c.node_pools.register.assert_not_called()


def test_absent(run):
    c = client(GPU)
    assert run(nomad_node_pool, dict(name="gpu", state="absent"), c)["changed"] is True
    c.node_pools.delete.assert_called_once_with("gpu")
    assert run(nomad_node_pool, dict(name="gpu", state="absent"), client())["changed"] is False


def test_server_error_fails_with_status(run):
    c = client(GPU)
    c.node_pools.register.side_effect = UnexpectedResponseError(500, body='Feature "Node Pools Governance" is unlicensed')
    with pytest.raises(Fail) as e:
        run(nomad_node_pool, dict(name="gpu", scheduler_configuration=dict(scheduler_algorithm="spread")), c)
    assert e.value.args[0]["status_code"] == 500 and "unlicensed" in e.value.args[0]["msg"]


def test_invalid_duration_fails(run):
    with pytest.raises(Fail) as e:
        run(nomad_node_pool, dict(name="gpu", node_identity_ttl="soon"), client(GPU))
    assert "invalid duration" in e.value.args[0]["msg"]


def test_info(run):
    c = client(GPU)
    assert run(nomad_node_pool_info, dict(name="gpu"), c)["node_pools"] == [GPU.to_json()]
    assert run(nomad_node_pool_info, dict(name="gpu"), client())["node_pools"] == []
    c.node_pools.list.return_value = ([GPU], QueryMeta())
    assert run(nomad_node_pool_info, dict(), c)["node_pools"] == [GPU.to_json()]
