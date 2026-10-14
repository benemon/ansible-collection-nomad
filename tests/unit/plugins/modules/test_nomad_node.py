from unittest import mock

import pytest
from nomadpy import DrainSpec, Node, NodeDrainUpdateResponse, NodeEligibilityUpdateResponse, NodeListStub, QueryMeta, UnexpectedResponseError, WriteMeta

from ansible_collections.benemon.nomad.plugins.modules import nomad_node, nomad_node_info

from .conftest import Fail

ID = "7f3a9b2c-1d4e-5f6a-8b9c-0d1e2f3a4b5c"
READY = Node(id=ID, name="worker-03", drain=False, scheduling_eligibility="eligible", status="ready")
DRAINING = Node(id=ID, name="worker-03", drain=True, scheduling_eligibility="ineligible", status="ready")
DRAINED = Node(id=ID, name="worker-03", drain=False, scheduling_eligibility="ineligible", status="ready")
STUB = NodeListStub(id=ID, name="worker-03", drain=False, scheduling_eligibility="eligible", status="ready")


def client(current=READY, after=None):
    """client answers nodes.info with current, then after (or current again) on every later read."""
    c = mock.MagicMock()
    c.nodes.info.side_effect = [(current, QueryMeta())] + [(after or current, QueryMeta(last_index=2))] * 5
    c.nodes.list.return_value = ([STUB], QueryMeta())
    c.nodes.toggle_eligibility.return_value = (NodeEligibilityUpdateResponse(), WriteMeta())
    c.nodes.update_drain.return_value = (NodeDrainUpdateResponse(), WriteMeta())
    return c


def test_ineligible(run):
    c = client(READY, after=DRAINED)
    result = run(nomad_node, dict(node_id=ID, eligibility="ineligible"), c)
    assert result["changed"] is True and result["node"]["SchedulingEligibility"] == "ineligible"
    c.nodes.toggle_eligibility.assert_called_once_with(ID, False)
    assert result["diff"]["before"]["SchedulingEligibility"] == "eligible"


def test_unchanged_when_eligibility_matches(run):
    c = client(READY)
    assert run(nomad_node, dict(node_id=ID, eligibility="eligible"), c)["changed"] is False
    c.nodes.toggle_eligibility.assert_not_called()
    c.nodes.update_drain.assert_not_called()


def test_name_resolves_through_the_list(run):
    c = client(READY, after=DRAINED)
    run(nomad_node, dict(name="worker-03", eligibility="ineligible"), c)
    c.nodes.list.assert_called_once()
    c.nodes.toggle_eligibility.assert_called_once_with(ID, False)
    c = client(READY)
    c.nodes.list.return_value = ([STUB, STUB], QueryMeta())
    with pytest.raises(Fail) as e:
        run(nomad_node, dict(name="worker-03", eligibility="ineligible"), c)
    assert "found 2" in e.value.args[0]["msg"]
    c.nodes.list.return_value = ([], QueryMeta())
    with pytest.raises(Fail) as e:
        run(nomad_node, dict(name="worker-03", eligibility="ineligible"), c)
    assert "found 0" in e.value.args[0]["msg"]


def test_drain_waits_until_the_flag_clears(run):
    c = client(READY)
    c.nodes.info.side_effect = [(READY, QueryMeta()), (DRAINING, QueryMeta(last_index=3)), (DRAINED, QueryMeta(last_index=4))]
    result = run(nomad_node, dict(node_id=ID, drain=True, deadline="30m", ignore_system_jobs=True), c)
    assert result["changed"] is True and result["node"]["Drain"] is False and result["node"]["SchedulingEligibility"] == "ineligible"
    c.nodes.update_drain.assert_called_once_with(ID, DrainSpec(deadline=1_800_000_000_000, ignore_system_jobs=True))
    assert c.nodes.info.call_args.args[1].wait_index == 3


def test_drain_without_wait(run):
    c = client(READY, after=DRAINING)
    result = run(nomad_node, dict(node_id=ID, drain=True, wait=False), c)
    assert result["changed"] is True and result["node"]["Drain"] is True
    assert c.nodes.info.call_count == 2


def test_drain_timeout_fails(run):
    c = client(READY, after=DRAINING)
    with pytest.raises(Fail) as e:
        run(nomad_node, dict(node_id=ID, drain=True, timeout=0), c)
    assert "did not finish draining" in e.value.args[0]["msg"]


def test_drain_unchanged_when_already_draining(run):
    c = client(DRAINING)
    assert run(nomad_node, dict(node_id=ID, drain=True), c)["changed"] is False
    c.nodes.update_drain.assert_not_called()


def test_stop_drain_and_mark_eligible(run):
    c = client(DRAINING, after=READY)
    result = run(nomad_node, dict(node_id=ID, drain=False, mark_eligible=True), c)
    assert result["changed"] is True and result["node"]["SchedulingEligibility"] == "eligible"
    c.nodes.update_drain.assert_called_once_with(ID, None, mark_eligible=True)
    c.nodes.toggle_eligibility.assert_not_called()


def test_mark_eligible_after_a_finished_drain(run):
    c = client(DRAINED, after=READY)
    result = run(nomad_node, dict(node_id=ID, drain=False, mark_eligible=True), c)
    assert result["changed"] is True and result["node"]["SchedulingEligibility"] == "eligible"
    c.nodes.update_drain.assert_not_called()
    c.nodes.toggle_eligibility.assert_called_once_with(ID, True)
    assert run(nomad_node, dict(node_id=ID, drain=False), client(DRAINED))["changed"] is False


def test_check_mode_writes_nothing(run):
    c = client(READY)
    result = run(nomad_node, dict(node_id=ID, drain=True), c, check_mode=True)
    assert result["changed"] is True and result["diff"]["after"]["Drain"] is True and result["diff"]["after"]["SchedulingEligibility"] == "ineligible"
    c.nodes.update_drain.assert_not_called()
    result = run(nomad_node, dict(node_id=ID, eligibility="ineligible"), client(READY), check_mode=True)
    assert result["changed"] is True and result["diff"]["after"]["SchedulingEligibility"] == "ineligible"
    assert c.nodes.info.call_count == 1


def test_bad_deadline_fails(run):
    with pytest.raises(Fail) as e:
        run(nomad_node, dict(node_id=ID, drain=True, deadline="soon"), client(READY))
    assert "invalid duration" in e.value.args[0]["msg"]


def test_server_error_fails_with_status(run):
    c = client(READY)
    c.nodes.toggle_eligibility.side_effect = UnexpectedResponseError(403, body="Permission denied")
    with pytest.raises(Fail) as e:
        run(nomad_node, dict(node_id=ID, eligibility="ineligible"), c)
    assert e.value.args[0]["status_code"] == 403 and "Permission denied" in e.value.args[0]["msg"]


def test_info(run):
    c = client(READY)
    assert run(nomad_node_info, dict(node_id=ID), c)["nodes"] == [READY.to_json()]
    assert run(nomad_node_info, dict(name="worker-03"), client(READY))["nodes"] == [READY.to_json()]
    missing = mock.MagicMock()
    missing.nodes.info.side_effect = UnexpectedResponseError(404)
    missing.nodes.list.return_value = ([], QueryMeta())
    assert run(nomad_node_info, dict(node_id=ID), missing)["nodes"] == []
    assert run(nomad_node_info, dict(name="worker-03"), missing)["nodes"] == []
    assert run(nomad_node_info, dict(), client())["nodes"] == [STUB.to_json()]
    c = client()
    c.nodes.prefix_list.return_value = ([STUB], QueryMeta())
    assert run(nomad_node_info, dict(prefix="7f3a"), c)["nodes"] == [STUB.to_json()]
    c.nodes.prefix_list.assert_called_once_with("7f3a")
