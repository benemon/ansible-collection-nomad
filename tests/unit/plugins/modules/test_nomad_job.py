from unittest import mock

import pytest
from nomadpy import Deployment, Evaluation, Job, JobDiff, JobPlanResponse, JobRegisterResponse, JobSubmission, QueryMeta, UnexpectedResponseError, WriteMeta

import json

from ansible_collections.benemon.nomad.plugins.modules import nomad_job, nomad_job_info

from .conftest import Fail

SPEC = {"ID": "web", "Name": "web", "Type": "service", "TaskGroups": [{"Name": "g", "Count": 1}]}
RUNNING = Job(id="web", name="web", type="service", status="running")


def client(existing=None, diff_type="Added"):
    c = mock.MagicMock()
    if existing is None:
        c.jobs.info.side_effect = [UnexpectedResponseError(404), (RUNNING, QueryMeta())]
    else:
        c.jobs.info.return_value = (existing, QueryMeta())
    c.jobs.plan.return_value = (JobPlanResponse(diff=JobDiff(type=diff_type)), WriteMeta())
    c.jobs.register.return_value = (JobRegisterResponse(eval_id="ev1"), WriteMeta())
    c.evaluations.info.return_value = (Evaluation(id="ev1", status="complete"), QueryMeta(last_index=1))
    c.jobs.latest_deployment.return_value = (Deployment(id="dep1"), QueryMeta())
    c.deployments.info.return_value = (Deployment(id="dep1", status="successful"), QueryMeta(last_index=2))
    return c


def test_register_and_wait(run):
    c = client()
    result = run(nomad_job, dict(jobspec=SPEC), c)
    assert result["changed"] is True and result["eval_id"] == "ev1" and result["deployment"]["Status"] == "successful"
    assert result["job"]["Status"] == "running"
    c.jobs.register.assert_called_once_with(SPEC, policy_override=False, submission=None)


def test_hcl_is_parsed_by_the_server(run):
    c = client()
    c.jobs.parse_hcl.return_value = Job(id="web", type="service")
    run(nomad_job, dict(jobspec='job "web" {}'), c)
    c.jobs.parse_hcl.assert_called_once_with('job "web" {}', variables="")
    assert c.jobs.register.call_args.kwargs["submission"] == JobSubmission(source='job "web" {}', format="hcl2", variables="")
    assert c.jobs.register.call_args.args[0]["ID"] == "web"


def test_hcl_variables_reach_the_parser(run):
    c = client()
    c.jobs.parse_hcl.return_value = Job(id="web", type="service")
    run(nomad_job, dict(jobspec='job "web" {}', hcl_variables=dict(count=3, image="nginx:1.27", debug=False, tags=["a", "b"])), c)
    assert c.jobs.parse_hcl.call_args.kwargs["variables"] == 'count = 3\nimage = "nginx:1.27"\ndebug = false\ntags = ["a", "b"]'
    assert c.jobs.register.call_args.kwargs["submission"].variables == c.jobs.parse_hcl.call_args.kwargs["variables"]
    with pytest.raises(Fail, match="jobspec is a document, not HCL"):
        run(nomad_job, dict(jobspec=SPEC, hcl_variables=dict(count=3)), client())
    with pytest.raises(Fail, match="must be a string, number, boolean or a list"):
        run(nomad_job, dict(jobspec='job "web" {}', hcl_variables=dict(meta=dict(a=1))), c)


def test_namespace_in_the_specification_is_used_for_reads(run):
    c = client()
    run(nomad_job, dict(jobspec=dict(SPEC, Namespace="web", Region="eu")), c)
    c.set_namespace.assert_called_once_with("web")
    c.set_region.assert_called_once_with("eu")
    c = client(RUNNING, diff_type="None")
    run(nomad_job, dict(jobspec=SPEC), c)
    c.set_namespace.assert_not_called()


def test_json_text_is_the_document(run):
    c = client()
    run(nomad_job, dict(jobspec=json.dumps(SPEC)), c)
    c.jobs.parse_hcl.assert_not_called()
    assert c.jobs.register.call_args.args[0] == SPEC


def test_no_diff_is_unchanged(run):
    c = client(RUNNING, diff_type="None")
    assert run(nomad_job, dict(jobspec=SPEC), c)["changed"] is False
    c.jobs.register.assert_not_called()


def test_check_mode_plans_only(run):
    c = client(RUNNING, diff_type="Edited")
    result = run(nomad_job, dict(jobspec=SPEC), c, check_mode=True)
    assert result["changed"] is True and result["diff"]["after"] == SPEC
    c.jobs.register.assert_not_called()


def test_failed_placement_fails(run):
    c = client()
    c.evaluations.info.return_value = (Evaluation(id="ev1", status="complete", failed_tg_allocs={"g": {}}), QueryMeta(last_index=1))
    with pytest.raises(Fail) as e:
        run(nomad_job, dict(jobspec=SPEC), c)
    assert "could not place" in e.value.args[0]["msg"]


def test_failed_deployment_fails(run):
    c = client()
    c.deployments.info.return_value = (Deployment(id="dep1", status="failed", status_description="unhealthy"), QueryMeta(last_index=2))
    with pytest.raises(Fail) as e:
        run(nomad_job, dict(jobspec=SPEC), c)
    assert "unhealthy" in e.value.args[0]["msg"]


def test_no_wait(run):
    c = client()
    result = run(nomad_job, dict(jobspec=SPEC, wait=False), c)
    assert result["changed"] is True and "deployment" not in result
    c.evaluations.info.assert_not_called()


def test_one_source_for_identity(run):
    with pytest.raises(Fail, match="name is set on the module and ID in the job specification"):
        run(nomad_job, dict(jobspec=SPEC, name="web"), client())
    with pytest.raises(Fail, match="namespace is set on the module and Namespace"):
        run(nomad_job, dict(jobspec=dict(SPEC, Namespace="web"), namespace="web"), client())
    with pytest.raises(Fail, match="region is set on the module and Region"):
        run(nomad_job, dict(jobspec=dict(SPEC, Region="global"), region="global"), client())
    assert run(nomad_job, dict(jobspec=dict(SPEC, Namespace=""), namespace="web"), client())["changed"] is True


def test_absent(run):
    c = client(RUNNING)
    c.jobs.deregister.return_value = ("ev2", WriteMeta())
    result = run(nomad_job, dict(name="web", state="absent", purge=True), c)
    assert result["changed"] is True and result["diff"] == dict(before=RUNNING.to_json(), after={})
    c.jobs.deregister.assert_called_once_with("web", purge=True)
    stopped = client(Job(id="web", stop=True))
    assert run(nomad_job, dict(name="web", state="absent"), stopped)["changed"] is False
    assert run(nomad_job, dict(name="web", state="absent", purge=True), stopped)["changed"] is True
    missing = mock.MagicMock()
    missing.jobs.info.side_effect = UnexpectedResponseError(404)
    assert run(nomad_job, dict(name="web", state="absent"), missing)["changed"] is False


def test_server_error_fails_with_status(run):
    c = client()
    c.jobs.plan.side_effect = UnexpectedResponseError(500, body="no datacenters")
    with pytest.raises(Fail) as e:
        run(nomad_job, dict(jobspec=SPEC), c)
    assert e.value.args[0]["status_code"] == 500 and "no datacenters" in e.value.args[0]["msg"]


def test_info(run):
    c = client(RUNNING)
    assert run(nomad_job_info, dict(name="web"), c)["jobs"] == [RUNNING.to_json()]
    missing = mock.MagicMock()
    missing.jobs.info.side_effect = UnexpectedResponseError(404)
    assert run(nomad_job_info, dict(name="web"), missing)["jobs"] == []
    c.jobs.list.return_value = ([RUNNING], QueryMeta())
    assert run(nomad_job_info, dict(), c)["jobs"] == [RUNNING.to_json()]
