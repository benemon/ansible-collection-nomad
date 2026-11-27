from unittest import mock

import pytest
from nomadpy import (
    HostVolume,
    HostVolumeCapability,
    HostVolumeCreateResponse,
    HostVolumeInfo,
    HostVolumeRegisterResponse,
    HostVolumeStub,
    Node,
    QueryMeta,
    UnexpectedResponseError,
    WriteMeta,
)

from ansible_collections.benemon.nomad.plugins.modules import nomad_volume, nomad_volume_info

from .conftest import Fail

ID = "3735cc2c-cc64-11ef-89ed-bfb5b3bc38ea"
OLD_ID = "11111111-1111-1111-1111-111111111111"
NODE_ID = "5c5830d0-cc64-11ef-a293-4f03e55969ea"
CAPABILITY = HostVolumeCapability(access_mode="single-node-writer", attachment_mode="file-system")
EXISTING = HostVolume(
    namespace="default",
    id=ID,
    name="data",
    plugin_id="mkdir",
    node_pool="default",
    node_id=NODE_ID,
    requested_capabilities=[CAPABILITY],
    parameters={"mode": "0700"},
    host_path="/opt/nomad/data/host_volumes/data",
    capacity_bytes=1024,
    state="ready",
    create_index=12,
    create_time=1760000000000000000,
    modify_index=15,
    modify_time=1760000001000000000,
    allocations=[],
)
STUB = HostVolumeStub(
    namespace="default",
    id=ID,
    name="data",
    plugin_id="mkdir",
    node_pool="default",
    node_id=NODE_ID,
    capacity_bytes=1024,
    state="ready",
    create_index=12,
    create_time=1760000000000000000,
    modify_index=15,
    modify_time=1760000001000000000,
)


def volume_client(existing=EXISTING):
    c = mock.MagicMock()
    c.config.namespace = "default"
    c.host_volumes.list.return_value = ([STUB] if existing else [], QueryMeta())
    c.host_volumes.get.return_value = (existing, QueryMeta())
    pending = HostVolume(
        id=ID,
        name="data",
        plugin_id="mkdir",
        node_pool="default",
        node_id=NODE_ID,
        requested_capabilities=[CAPABILITY],
        parameters={"mode": "0700"},
        state="pending",
    )
    c.host_volumes.create.return_value = (HostVolumeCreateResponse(volume=pending), WriteMeta())
    c.host_volumes.register.return_value = (HostVolumeRegisterResponse(volume=pending), WriteMeta())
    c.nodes.info.return_value = (
        Node(id=NODE_ID, host_volumes={"data": HostVolumeInfo(id=ID)}),
        QueryMeta(last_index=2),
    )
    return c


def options(**overrides):
    values = dict(
        name="data",
        node_pool="default",
        plugin_id="mkdir",
        capabilities=[dict(access_mode="single-node-writer", attachment_mode="file-system")],
        parameters={"mode": "0700"},
        wait=False,
    )
    values.update(overrides)
    return values


def test_create_sends_volume(run):
    c = volume_client(None)
    result = run(nomad_volume, options(), c)
    assert result["changed"] is True and result["diff"]["before"] == {}
    sent = c.host_volumes.create.call_args.args[0]
    assert sent == HostVolume(
        name="data",
        node_pool="default",
        plugin_id="mkdir",
        requested_capabilities=[CAPABILITY],
        parameters={"mode": "0700"},
    )
    assert sent.id == ""


def test_unchanged_when_options_match(run):
    c = volume_client()
    result = run(nomad_volume, options(), c)
    assert result["changed"] is False
    c.host_volumes.create.assert_not_called()
    c.host_volumes.register.assert_not_called()

    without_parameters = HostVolume.from_json(EXISTING.to_json() | {"Parameters": None})
    c = volume_client(without_parameters)
    result = run(nomad_volume, options(parameters={}), c)
    assert result["changed"] is False


def test_empty_parameters_and_capabilities_clear_them(run):
    c = volume_client()
    result = run(nomad_volume, options(parameters={}, capabilities=[]), c)
    assert result["changed"] is True
    sent = c.host_volumes.create.call_args.args[0]
    assert sent.parameters == {} and sent.requested_capabilities == []


def test_update_carries_id_and_node(run):
    c = volume_client()
    run(nomad_volume, options(parameters={"mode": "0755"}), c)
    sent = c.host_volumes.create.call_args.args[0]
    assert sent.id == ID and sent.node_id == NODE_ID


def test_identity_is_exact_name_in_pool(run):
    c = volume_client()
    old = HostVolumeStub(id=OLD_ID, name="data-old", node_pool="default", node_id=NODE_ID)
    c.host_volumes.list.return_value = ([old, STUB], QueryMeta())
    run(nomad_volume, options(node_id=NODE_ID), c)
    c.host_volumes.list.assert_called_once_with(node_pool="default", node_id=NODE_ID)
    c.host_volumes.get.assert_called_once_with(ID)


def test_two_matches_fail(run):
    c = volume_client()
    c.host_volumes.list.return_value = ([STUB, HostVolumeStub(id=OLD_ID, name="data")], QueryMeta())
    with pytest.raises(Fail) as e:
        run(nomad_volume, options(), c)
    assert "found 2" in e.value.args[0]["msg"]


def test_register_with_host_path(run):
    c = volume_client(None)
    result = run(
        nomad_volume,
        dict(name="reg", node_id=NODE_ID, host_path="/srv/reg", wait=False),
        c,
    )
    assert result["changed"] is True
    sent = c.host_volumes.register.call_args.args[0]
    assert sent == HostVolume(name="reg", node_id=NODE_ID, host_path="/srv/reg")
    c.host_volumes.create.assert_not_called()


def test_check_mode_writes_nothing(run):
    c = volume_client()
    result = run(nomad_volume, options(parameters={"mode": "0755"}, wait=True), c, check_mode=True)
    assert result["changed"] is True and result["volume"]["Parameters"] == {"mode": "0755"}
    c.host_volumes.create.assert_not_called()
    c.host_volumes.register.assert_not_called()
    c.nodes.info.assert_not_called()


def test_absent(run):
    c = volume_client()
    result = run(nomad_volume, dict(name="data", state="absent"), c)
    assert result["changed"] is True and result["diff"]["after"] == {}
    c.host_volumes.delete.assert_called_once_with(ID)

    missing = volume_client(None)
    assert run(nomad_volume, dict(name="data", state="absent"), missing)["changed"] is False
    missing.host_volumes.delete.assert_not_called()

    c = volume_client()
    assert run(nomad_volume, dict(name="data", state="absent"), c, check_mode=True)["changed"] is True
    c.host_volumes.delete.assert_not_called()


def test_wait_polls_until_node_lists_the_id(run):
    c = volume_client()
    c.nodes.info.side_effect = [
        (Node(id=NODE_ID), QueryMeta(last_index=2)),
        (Node(id=NODE_ID, host_volumes={"data": HostVolumeInfo(id=OLD_ID)}), QueryMeta(last_index=3)),
        (Node(id=NODE_ID, host_volumes={"data": HostVolumeInfo(id=ID)}), QueryMeta(last_index=4)),
    ]
    result = run(nomad_volume, options(wait=True), c)
    assert result["volume"]["State"] == "ready"
    assert [call.args[1].wait_index for call in c.nodes.info.call_args_list] == [0, 2, 3]


def test_wait_requires_ready(run):
    c = volume_client()
    pending = HostVolume.from_json(EXISTING.to_json() | {"State": "pending"})
    c.host_volumes.get.side_effect = [(EXISTING, QueryMeta()), (pending, QueryMeta()), (EXISTING, QueryMeta())]
    c.nodes.info.side_effect = [
        (Node(id=NODE_ID, host_volumes={"data": HostVolumeInfo(id=ID)}), QueryMeta(last_index=2)),
        (Node(id=NODE_ID, host_volumes={"data": HostVolumeInfo(id=ID)}), QueryMeta(last_index=3)),
    ]
    result = run(nomad_volume, options(wait=True), c)
    assert result["volume"]["State"] == "ready"
    assert c.nodes.info.call_count == 2 and c.host_volumes.get.call_count == 3


def test_wait_times_out(run):
    c = volume_client()
    c.nodes.info.side_effect = [(Node(id=NODE_ID), QueryMeta(last_index=2))]
    with mock.patch.object(nomad_volume.time, "monotonic", side_effect=[100, 100.5, 101.1]):
        with pytest.raises(Fail) as e:
            run(nomad_volume, options(wait=True, timeout=1), c)
    assert "last state: not read; node volume ID: missing" in e.value.args[0]["msg"]


def test_wait_timeout_does_not_report_unread_results(run):
    c = volume_client()
    with mock.patch.object(nomad_volume.time, "monotonic", side_effect=[100, 100]):
        with pytest.raises(Fail) as e:
            run(nomad_volume, options(wait=True, timeout=0), c)
    assert "last state: not read; node volume ID: not read" in e.value.args[0]["msg"]
    c.nodes.info.assert_not_called()


def test_wait_false_does_not_read_the_node(run):
    c = volume_client(None)
    run(nomad_volume, options(wait=False), c)
    c.nodes.info.assert_not_called()


def test_wait_runs_when_unchanged(run):
    c = volume_client()
    result = run(nomad_volume, options(wait=True), c)
    assert result["changed"] is False and result["volume"]["State"] == "ready"
    c.nodes.info.assert_called_once()


def test_argument_guards(run):
    with pytest.raises(Fail):
        run(nomad_volume, dict(name="data", plugin_id="mkdir", host_path="/srv/data", node_id=NODE_ID), volume_client(None))
    with pytest.raises(Fail):
        run(nomad_volume, dict(name="data", host_path="/srv/data"), volume_client(None))
    with pytest.raises(Fail):
        run(nomad_volume, dict(name="data"), volume_client(None))
    with pytest.raises(Fail):
        run(
            nomad_volume,
            dict(name="data", plugin_id="mkdir", capabilities=[dict(access_mode="single-node-writer")]),
            volume_client(None),
            check_mode=True,
        )
    with pytest.raises(Fail):
        run(
            nomad_volume,
            dict(name="data", plugin_id="mkdir", capabilities=[dict(attachment_mode="file-system")]),
            volume_client(None),
            check_mode=True,
        )
    c = volume_client(None)
    c.config.namespace = "*"
    with pytest.raises(Fail):
        run(nomad_volume, dict(name="data", namespace="*", plugin_id="mkdir"), c, check_mode=True)


def test_environment_namespace_star_fails(run):
    c = volume_client(None)
    c.config.namespace = "*"
    with pytest.raises(Fail) as e:
        run(nomad_volume, dict(name="data", plugin_id="mkdir"), c, check_mode=True)
    assert e.value.args[0]["msg"] == "namespace must name one namespace, not *"
    c.host_volumes.list.assert_not_called()


def test_server_error_fails_with_status(run):
    c = volume_client(None)
    c.host_volumes.create.side_effect = UnexpectedResponseError(500, body="not feasible")
    with pytest.raises(Fail) as e:
        run(nomad_volume, options(), c)
    assert e.value.args[0]["status_code"] == 500 and "not feasible" in e.value.args[0]["msg"]


def test_info(run):
    c = volume_client()
    assert run(nomad_volume_info, dict(id=ID), c)["volumes"] == [EXISTING.to_json()]

    missing = volume_client()
    missing.host_volumes.get.side_effect = UnexpectedResponseError(404, body="volume not found")
    assert run(nomad_volume_info, dict(id=ID), missing)["volumes"] == []

    old = HostVolumeStub(id=OLD_ID, name="data-old", node_pool="default", node_id=NODE_ID)
    c = volume_client()
    c.host_volumes.list.return_value = ([STUB, old], QueryMeta())
    result = run(nomad_volume_info, dict(name="data", node_pool="default", node_id=NODE_ID), c)
    assert result["volumes"] == [STUB.to_json()]
    c.host_volumes.list.assert_called_once_with(node_pool="default", node_id=NODE_ID)


def test_info_argument_guards(run):
    with pytest.raises(Fail):
        run(nomad_volume_info, dict(id=ID, name="data"), volume_client())
    with pytest.raises(Fail):
        run(nomad_volume_info, dict(id=ID, node_pool="default"), volume_client())
    with pytest.raises(Fail):
        run(nomad_volume_info, dict(id=ID, node_id=NODE_ID), volume_client())
