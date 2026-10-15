from unittest import mock

import pytest
from nomadpy import AllocationListStub, Allocation, AllocStopResponse, QueryMeta
from nomadpy.fs import StreamFrame

from ansible_collections.benemon.nomad.plugins.modules import nomad_allocation, nomad_allocation_info
from ansible_collections.benemon.nomad.plugins.module_utils.nomad import UnexpectedResponseError

from .conftest import Fail

ID = "8b5e7a4e-2b1d-6f0c-9a3e-0d1f2a3b4c5d"
RUNNING = Allocation(id=ID, name="web.web[0]", namespace="default", job_id="web", task_group="web", client_status="running", desired_status="run")
COMPLETE = Allocation(id=ID, name="web.web[0]", namespace="default", job_id="web", task_group="web", client_status="complete", desired_status="stop")


def client(current=RUNNING, after=None):
    c = mock.MagicMock()
    c.allocations.info.side_effect = [(current, QueryMeta())] + [(after or current, QueryMeta(last_index=2))] * 5
    c.allocations.stop.return_value = (AllocStopResponse(eval_id="e1"), QueryMeta())
    return c


def test_restart_all_tasks(run):
    c = client()
    result = run(nomad_allocation, dict(alloc_id=ID, restart=True), c)
    assert result["changed"] is True and result["allocation"]["ID"] == ID
    c.allocations.restart_all_tasks.assert_called_once()
    assert c.allocations.restart_all_tasks.call_args.args[0] == ID
    c.allocations.restart.assert_not_called()


def test_restart_one_task(run):
    c = client()
    run(nomad_allocation, dict(alloc_id=ID, restart=True, task="web", namespace="web"), c)
    alloc_id, task, q = c.allocations.restart.call_args.args
    assert (alloc_id, task, q.namespace) == (ID, "web", "web")


def test_signal(run):
    c = client()
    assert run(nomad_allocation, dict(alloc_id=ID, task="web", signal="SIGHUP"), c)["changed"] is True
    assert c.allocations.signal.call_args.args[:3] == (ID, "web", "SIGHUP")
    with pytest.raises(Fail) as e:
        run(nomad_allocation, dict(alloc_id=ID, signal="SIGHUP"), c)
    assert "task" in e.value.args[0]["msg"]


def test_check_mode_reports_without_acting(run):
    c = client()
    assert run(nomad_allocation, dict(alloc_id=ID, restart=True), c, check_mode=True)["changed"] is True
    c.allocations.restart_all_tasks.assert_not_called()
    assert run(nomad_allocation, dict(alloc_id=ID, state="absent"), c, check_mode=True)["changed"] is True
    c.allocations.stop.assert_not_called()


def test_stop_waits_for_a_terminal_status(run):
    c = client()
    c.allocations.info.side_effect = [(RUNNING, QueryMeta()), (RUNNING, QueryMeta(last_index=3)), (COMPLETE, QueryMeta(last_index=4))]
    result = run(nomad_allocation, dict(alloc_id=ID, state="absent"), c)
    assert result["changed"] is True and result["eval_id"] == "e1" and result["allocation"]["ClientStatus"] == "complete"
    assert c.allocations.info.call_args_list[1].args[1].wait_index == 0
    assert c.allocations.info.call_args_list[2].args[1].wait_index == 3


def test_stop_without_wait(run):
    c = client(RUNNING, after=RUNNING)
    result = run(nomad_allocation, dict(alloc_id=ID, state="absent", wait=False), c)
    assert result["changed"] is True and result["allocation"]["ClientStatus"] == "running"
    assert c.allocations.info.call_count == 2


def test_stop_is_unchanged_when_finished_or_missing(run):
    c = client(COMPLETE)
    assert run(nomad_allocation, dict(alloc_id=ID, state="absent"), c)["changed"] is False
    c.allocations.stop.assert_not_called()
    c = client()
    c.allocations.info.side_effect = UnexpectedResponseError(404, body="alloc not found")
    result = run(nomad_allocation, dict(alloc_id=ID, state="absent"), c)
    assert result["changed"] is False and result["allocation"] is None


def test_restart_of_a_missing_allocation_fails(run):
    c = client()
    c.allocations.info.side_effect = UnexpectedResponseError(404, body="alloc not found")
    with pytest.raises(Fail) as e:
        run(nomad_allocation, dict(alloc_id=ID, restart=True), c)
    assert "not found" in e.value.args[0]["msg"]


def test_absent_excludes_actions(run):
    with pytest.raises(Fail) as e:
        run(nomad_allocation, dict(alloc_id=ID, state="absent", restart=True), client())
    assert "state=absent" in e.value.args[0]["msg"]


def test_info_one_with_logs(run):
    c = client()
    c.alloc_fs.logs.return_value = iter([StreamFrame(data="aGVsbG8K", offset=6), StreamFrame(data="d29ybGQK", offset=12)])
    result = run(nomad_allocation_info, dict(alloc_id=ID, task="web", log_type="stderr"), c)
    assert result["allocations"][0]["ID"] == ID and result["logs"] == "hello\nworld\n"
    alloc_id, follow, task, log_type, origin, offset = c.alloc_fs.logs.call_args.args[:6]
    assert (alloc_id, follow, task, log_type, origin, offset) == (ID, False, "web", "stderr", "start", 0)


def test_info_list_filters(run):
    c = client()
    c.allocations.list.return_value = ([AllocationListStub(id=ID, job_id="web")], QueryMeta())
    result = run(nomad_allocation_info, dict(job="web", node_id="n1", namespace="web"), c)
    assert [a["ID"] for a in result["allocations"]] == [ID]
    q = c.allocations.list.call_args.args[0]
    assert q.filter == 'JobID == "web" and NodeID == "n1"' and q.namespace == "web"
    c.allocations.list.return_value = ([], QueryMeta())
    assert run(nomad_allocation_info, dict(), c)["allocations"] == []
    assert c.allocations.list.call_args.args[0].filter == ""


def test_info_missing_allocation(run):
    c = client()
    c.allocations.info.side_effect = UnexpectedResponseError(404, body="alloc not found")
    assert run(nomad_allocation_info, dict(alloc_id=ID), c)["allocations"] == []
    with pytest.raises(Fail):
        run(nomad_allocation_info, dict(alloc_id=ID, task="web"), c)
