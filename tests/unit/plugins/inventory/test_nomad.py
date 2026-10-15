import json
from unittest import mock

import pytest
from ansible.errors import AnsibleParserError
from ansible.inventory.data import InventoryData
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import inventory_loader
from nomadpy import (
    AgentMember,
    AllocatedResources,
    AllocatedSharedResources,
    AllocationListStub,
    DriverInfo,
    TaskState,
    Job,
    Node,
    NodeListStub,
    QueryMeta,
    ServerMembers,
    ServiceRegistration,
    Task,
    TaskGroup,
    UnexpectedResponseError,
)

from ansible_collections.benemon.nomad.plugins.module_utils import nomad as module_utils

NODE = NodeListStub(
    id="n1", name="node1", address="10.0.0.5", datacenter="dc1", node_pool="default", status="ready",
    scheduling_eligibility="eligible", version="2.0.5",
    drivers={"raw_exec": DriverInfo(detected=True, healthy=True), "docker": DriverInfo(detected=False)},
)
MEMBER = AgentMember(name="server1.global", addr="10.0.0.1", port=4648, tags={"dc": "dc1", "region": "global"}, status="alive")
RUNNING = AllocationListStub(
    id="a1", name="web.web[0]", namespace="default", node_id="n1", job_id="web", task_group="web", client_status="running",
    allocated_resources=AllocatedResources(shared=AllocatedSharedResources(networks=[{"IP": "172.26.64.3", "Mode": "bridge"}])),
    task_states={"web": TaskState(state="running")},
)
STOPPED = AllocationListStub(id="a2", name="web.web[1]", namespace="default", node_id="n1", job_id="web", task_group="web", client_status="complete")


def client_with(nodes=(NODE,), members=(MEMBER,), allocations=(RUNNING, STOPPED)):
    client = mock.MagicMock()
    client.nodes.list.return_value = (list(nodes), QueryMeta())
    client.agent.members.return_value = ServerMembers(members=list(members))
    client.allocations.list.return_value = (list(allocations), QueryMeta())
    return client


def run(tmp_path, client, parse_cache=True, **config):
    path = tmp_path / "test.nomad.yml"
    path.write_text(json.dumps({"plugin": "benemon.nomad.nomad", **config}))
    plugin = inventory_loader.get("benemon.nomad.nomad")
    inventory = InventoryData()
    with mock.patch.object(module_utils.nomadpy, "Client", return_value=client) as cls:
        plugin.parse(inventory, DataLoader(), str(path), cache=parse_cache)
    return inventory, plugin, cls.call_args.args[0] if cls.call_args else None


def hosts_of(inventory, group):
    return sorted(h.name for h in inventory.groups[group].get_hosts())


def test_verify_file(tmp_path):
    plugin = inventory_loader.get("benemon.nomad.nomad")
    for name, ok in (("x.nomad.yml", True), ("x.nomad.yaml", True), ("x.yml", False)):
        path = tmp_path / name
        path.write_text("")
        assert plugin.verify_file(str(path)) is ok


def test_clients_by_default(tmp_path):
    client = client_with()
    inventory = run(tmp_path, client)[0]
    host = inventory.get_host("node1")
    assert host.vars["ansible_host"] == "10.0.0.5"
    assert host.vars["nomad_node"]["ID"] == "n1" and host.vars["nomad_node"]["Datacenter"] == "dc1"
    for group in ("nomad_clients", "nomad_datacenter_dc1", "nomad_node_pool_default", "nomad_status_ready",
                  "nomad_eligibility_eligible", "nomad_driver_raw_exec"):
        assert hosts_of(inventory, group) == ["node1"]
    assert "nomad_driver_docker" not in inventory.groups
    assert "nomad_node_class_" not in " ".join(inventory.groups)
    assert "nomad_servers" not in inventory.groups and "nomad_allocations" not in inventory.groups
    client.agent.members.assert_not_called()
    client.allocations.list.assert_not_called()
    client.nodes.info.assert_not_called()


def test_node_class_group(tmp_path):
    inventory = run(tmp_path, client_with(nodes=[NodeListStub(id="n2", name="node2", node_class="gpu", drivers=None)]))[0]
    assert hosts_of(inventory, "nomad_node_class_gpu") == ["node2"]


def test_servers(tmp_path):
    inventory = run(tmp_path, client_with(), servers=True)[0]
    host = inventory.get_host("server1.global")
    assert host.vars["ansible_host"] == "10.0.0.1" and host.vars["nomad_member"]["Tags"]["region"] == "global"
    assert hosts_of(inventory, "nomad_servers") == ["server1.global"]
    assert hosts_of(inventory, "nomad_datacenter_dc1") == ["node1", "server1.global"]


def test_allocations_at_node_address(tmp_path):
    client = client_with()
    inventory = run(tmp_path, client, allocations=True)[0]
    assert hosts_of(inventory, "nomad_allocations") == ["default.web.web.0"]
    host = inventory.get_host("default.web.web.0")
    assert host.vars["ansible_host"] == "10.0.0.5" and host.vars["nomad_allocation"]["ID"] == "a1"
    assert host.vars["ansible_nomad_alloc_id"] == "a1" and host.vars["ansible_nomad_namespace"] == "default"
    assert host.vars["ansible_nomad_task"] == "web"
    assert hosts_of(inventory, "nomad_namespace_default") == ["default.web.web.0"]
    assert hosts_of(inventory, "nomad_job_web") == ["default.web.web.0"]
    q = client.allocations.list.call_args.args[0]
    assert q.namespace == "*" and q.params == {"resources": "true"}


def test_allocations_without_clients_still_read_the_nodes(tmp_path):
    client = client_with()
    inventory = run(tmp_path, client, clients=False, allocations=True)[0]
    assert "nomad_clients" not in inventory.groups
    assert inventory.get_host("default.web.web.0").vars["ansible_host"] == "10.0.0.5"
    client.nodes.list.assert_called_once()


def test_network_address(tmp_path):
    client = client_with()
    inventory = run(tmp_path, client, allocations=True, allocation_address="network")[0]
    assert inventory.get_host("default.web.web.0").vars["ansible_host"] == "172.26.64.3"
    client.nodes.list.assert_called_once()  # clients are on by default; the strategy itself does not read nodes


def test_service_address(tmp_path):
    client = client_with()
    client.services.get.return_value = ([ServiceRegistration(id="r1", alloc_id="a1", address="192.0.2.8", port=2222)], QueryMeta())
    inventory = run(tmp_path, client, allocations=True, allocation_address="service:ssh")[0]
    host = inventory.get_host("default.web.web.0")
    assert host.vars["ansible_host"] == "192.0.2.8" and host.vars["ansible_port"] == 2222
    name, q = client.services.get.call_args.args
    assert name == "ssh" and q.namespace == "default"


def test_service_without_registration_has_no_address(tmp_path):
    client = client_with()
    client.services.get.return_value = ([], QueryMeta())
    inventory = run(tmp_path, client, allocations=True, allocation_address="service:ssh")[0]
    assert "ansible_host" not in inventory.get_host("default.web.web.0").vars


def test_meta_address(tmp_path):
    second = AllocationListStub(id="a3", name="web.api[0]", namespace="default", node_id="n1", job_id="web", task_group="api", client_status="running")
    client = client_with(allocations=[RUNNING, second])
    job = Job(id="web", meta={"ansible_host": "job.example"}, task_groups=[
        TaskGroup(name="web", meta={"ansible_host": "group.example"}, tasks=[Task(name="t", meta={"ansible_host": "task.example"})]),
        TaskGroup(name="api", tasks=[Task(name="t")]),
    ])
    client.jobs.info.return_value = (job, QueryMeta())
    inventory = run(tmp_path, client, allocations=True, allocation_address="meta:ansible_host")[0]
    assert inventory.get_host("default.web.web.0").vars["ansible_host"] == "task.example"
    assert inventory.get_host("default.web.api.0").vars["ansible_host"] == "job.example"
    assert "ansible_nomad_task" not in inventory.get_host("default.web.api.0").vars  # no task states on the stub
    client.jobs.info.assert_called_once()
    assert client.jobs.info.call_args.args[0] == "web" and client.jobs.info.call_args.args[1].namespace == "default"


def test_bad_strategy(tmp_path):
    with pytest.raises(AnsibleParserError, match="allocation_address must be"):
        run(tmp_path, client_with(), allocations=True, allocation_address="bogus")


def test_node_detail(tmp_path):
    client = client_with()
    client.nodes.info.return_value = (Node(id="n1", name="node1", meta={"rack": "r1"}, attributes={"os.name": "linux"}), QueryMeta())
    inventory = run(tmp_path, client, node_detail=True)[0]
    host = inventory.get_host("node1")
    assert host.vars["nomad_node"]["Meta"] == {"rack": "r1"} and host.vars["ansible_host"] == "10.0.0.5"
    client.nodes.info.assert_called_once_with("n1")


def test_options_build_the_client(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_ADDR", "http://env:4646")
    monkeypatch.setenv("NOMAD_TOKEN", "env-token")
    config = run(tmp_path, client_with(), address="http://option:4646", skip_verify=True, namespace="web", allocations=True)[2]
    assert config.address == "http://option:4646" and config.secret_id == "env-token"
    assert config.tls_config.insecure is True
    assert config.namespace != "web"  # the plugin's namespace is a query option, not the client default


def test_constructed_options(tmp_path):
    inventory = run(
        tmp_path, client_with(),
        compose={"nomad_version": "nomad_node.Version"},
        keyed_groups=[{"key": "nomad_node.Datacenter", "prefix": "dc"}],
        groups={"ready": "nomad_node.Status == 'ready'"},
    )[0]
    assert inventory.get_host("node1").vars["nomad_version"] == "2.0.5"
    assert hosts_of(inventory, "dc_dc1") == ["node1"] and hosts_of(inventory, "ready") == ["node1"]


def test_cache(tmp_path):
    cache = dict(cache=True, cache_plugin="ansible.builtin.jsonfile", cache_connection=str(tmp_path / "cache"), servers=True)
    inventory, plugin = run(tmp_path, client_with(), **cache)[:2]
    plugin.update_cache_if_changed()
    failing = mock.MagicMock()
    failing.nodes.list.side_effect = AssertionError("the API was read")
    cached = run(tmp_path, failing, **cache)[0]
    assert hosts_of(cached, "nomad_clients") == hosts_of(inventory, "nomad_clients") == ["node1"]
    assert hosts_of(cached, "nomad_servers") == ["server1.global"]
    assert cached.get_host("node1").vars == inventory.get_host("node1").vars
    with pytest.raises(AssertionError, match="the API was read"):
        run(tmp_path, failing, parse_cache=False, **cache)
    with pytest.raises(AssertionError, match="the API was read"):
        run(tmp_path, failing, **dict(cache, allocations=True))


def test_server_error_carries_status_and_body(tmp_path):
    client = client_with()
    client.nodes.list.side_effect = UnexpectedResponseError(403, body="Permission denied")
    with pytest.raises(AnsibleParserError, match="403.*Permission denied"):
        run(tmp_path, client)
