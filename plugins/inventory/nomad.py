# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
name: nomad
short_description: Nomad client nodes, server members and allocations as hosts
version_added: 0.2.0
description:
  - Lists the client nodes of a Nomad cluster as hosts, and on request its server members and running allocations.
  - Host variables are the Nomad API documents with the API's field names.
  - Reads a YAML configuration file whose name ends in C(nomad.yml) or C(nomad.yaml).
options:
  plugin:
    description: The name of this plugin.
    type: str
    required: true
    choices: [benemon.nomad.nomad]
  clients:
    description: List client nodes as hosts, in the group C(nomad_clients).
    type: bool
    default: true
  servers:
    description: List the server agent members as hosts, in the group C(nomad_servers).
    type: bool
    default: false
  allocations:
    description: List running allocations as hosts, in the group C(nomad_allocations).
    type: bool
    default: false
  namespace:
    description:
      - Namespace whose allocations are listed.
      - V(*) is every namespace the token can read.
    type: str
    default: "*"
  allocation_address:
    description:
      - Where the C(ansible_host) of an allocation host comes from.
      - V(node) is the address of the node the allocation runs on.
      - V(network) is the IP of the allocation's first network.
      - V(service:NAME) is the address and port the allocation registered for the Nomad service NAME; C(ansible_port) is set as well.
      - V(meta:KEY) is the value of KEY in the meta of the allocation's tasks, then of its task group, then of its job.
      - A host whose address is not found this way has no C(ansible_host).
    type: str
    default: node
  node_detail:
    description:
      - Read every client node in full, one request per node, so C(nomad_node) carries C(Attributes), C(Meta), C(Links),
        C(HostVolumes) and the other fields of the node endpoint.
      - Off, C(nomad_node) is the stub the node list returns.
    type: bool
    default: false
extends_documentation_fragment:
  - benemon.nomad.nomad
  - ansible.builtin.constructed
  - ansible.builtin.inventory_cache
author:
  - Benjamin Holmes (@benemon)
"""

EXAMPLES = r"""
# cluster.nomad.yml: client nodes, grouped by datacenter, node pool, class, status, eligibility and driver
plugin: benemon.nomad.nomad
address: https://nomad.example.com:4646

# Server members and running allocations as well, reached through the node they run on
plugin: benemon.nomad.nomad
servers: true
allocations: true

# Virtual machines run as allocations, reached at the address their task registered as a Nomad service
plugin: benemon.nomad.nomad
clients: false
allocations: true
namespace: vms
allocation_address: service:ssh
keyed_groups:
  - key: nomad_allocation.JobID
    prefix: vm
compose:
  ansible_user: nomad_allocation.TaskGroup
"""

import re
import urllib.error

from ansible.errors import AnsibleParserError
from ansible.module_utils.basic import missing_required_lib
from ansible.plugins.inventory import BaseInventoryPlugin, Cacheable, Constructable

from ansible_collections.benemon.nomad.plugins.module_utils.nomad import (
    HAS_NOMADPY,
    NOMAD_ARGUMENT_SPEC,
    NOMADPY_IMPORT_ERROR,
    client_from_options,
)

try:
    from nomadpy import QueryOptions, UnexpectedResponseError
except ImportError:
    pass

# The API names an allocation "<job>.<group>[<index>]"; a host pattern reads "[0]" as a group slice.
INDEX = re.compile(r"\[(\d+)\]$")
SHAPE_OPTIONS = ("clients", "servers", "allocations", "namespace", "allocation_address", "node_detail")


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = "benemon.nomad.nomad"

    def verify_file(self, path):
        return super().verify_file(path) and path.endswith(("nomad.yml", "nomad.yaml"))

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path)
        if not HAS_NOMADPY:
            raise AnsibleParserError(missing_required_lib("nomadpy") + "\n" + NOMADPY_IMPORT_ERROR)
        self._read_config_data(path)
        strategy = self.get_option("allocation_address")
        if strategy not in ("node", "network") and not strategy.startswith(("service:", "meta:")):
            raise AnsibleParserError("allocation_address must be node, network, service:NAME or meta:KEY; got %s" % strategy)
        shape = {name: self.get_option(name) for name in SHAPE_OPTIONS}
        use_cache = self.get_option("cache")
        cache_key = self.get_cache_key(path)
        payload = None
        if use_cache and cache:
            try:
                payload = self._cache[cache_key]
            except KeyError:
                pass
            # A payload fetched under other options lacks what these need.
            if payload is not None and payload.get("shape") != shape:
                payload = None
        if payload is None:
            payload = self._fetch(strategy)
            payload["shape"] = shape
            if use_cache:
                self._cache[cache_key] = payload
        self._populate(payload, strategy)

    def _fetch(self, strategy):
        """_fetch reads what the configured hosts need and returns it as plain documents, the shape the cache holds."""
        client = client_from_options({name: self.get_option(name) for name in NOMAD_ARGUMENT_SPEC})
        clients, allocations = self.get_option("clients"), self.get_option("allocations")
        payload = {}
        try:
            if clients or (allocations and strategy == "node"):
                stubs = client.nodes.list()[0]
                payload["nodes"] = [n.to_json() for n in stubs]
                if clients and self.get_option("node_detail"):
                    payload["node_detail"] = {n.id: client.nodes.info(n.id)[0].to_json() for n in stubs}
            if self.get_option("servers"):
                payload["members"] = [m.to_json() for m in client.agent.members().members or []]
            if allocations:
                q = QueryOptions(namespace=self.get_option("namespace"), params={"resources": "true"})
                running = [a for a in client.allocations.list(q)[0] if a.client_status == "running"]
                payload["allocations"] = [a.to_json() for a in running]
                if strategy.startswith("service:"):
                    payload["services"] = []
                    for namespace in sorted({a.namespace for a in running}):
                        registrations = client.services.get(strategy[len("service:"):], QueryOptions(namespace=namespace))[0]
                        payload["services"] += [r.to_json() for r in registrations]
                if strategy.startswith("meta:"):
                    payload["jobs"] = {}
                    for a in running:
                        key = a.namespace + "/" + a.job_id
                        if key not in payload["jobs"]:
                            payload["jobs"][key] = client.jobs.info(a.job_id, QueryOptions(namespace=a.namespace))[0].to_json()
        except UnexpectedResponseError as e:
            raise AnsibleParserError("reading from Nomad: %s" % e) from e
        except urllib.error.URLError as e:
            raise AnsibleParserError("cannot reach Nomad: %s" % e.reason) from e
        return payload

    def _populate(self, payload, strategy):
        strict = self.get_option("strict")
        if self.get_option("clients"):
            detail = payload.get("node_detail", {})
            for stub in payload["nodes"]:
                groups = [
                    "nomad_clients",
                    "nomad_datacenter_" + stub["Datacenter"],
                    "nomad_node_pool_" + stub["NodePool"],
                    "nomad_status_" + stub["Status"],
                    "nomad_eligibility_" + stub["SchedulingEligibility"],
                ]
                if stub["NodeClass"]:
                    groups.append("nomad_node_class_" + stub["NodeClass"])
                groups += ["nomad_driver_" + name for name, driver in (stub["Drivers"] or {}).items() if driver["Detected"]]
                self._add(stub["Name"], groups, {"ansible_host": stub["Address"], "nomad_node": detail.get(stub["ID"], stub)}, strict)
        if self.get_option("servers"):
            for member in payload["members"]:
                groups = ["nomad_servers"]
                datacenter = (member["Tags"] or {}).get("dc")
                if datacenter:
                    groups.append("nomad_datacenter_" + datacenter)
                self._add(member["Name"], groups, {"ansible_host": member["Addr"], "nomad_member": member}, strict)
        if self.get_option("allocations"):
            node_address = {n["ID"]: n["Address"] for n in payload.get("nodes", [])}
            for alloc in payload["allocations"]:
                name = alloc["Namespace"] + "." + INDEX.sub(r".\1", alloc["Name"])
                groups = ["nomad_allocations", "nomad_namespace_" + alloc["Namespace"], "nomad_job_" + alloc["JobID"]]
                hostvars = {"nomad_allocation": alloc, **_allocation_address(alloc, strategy, payload, node_address)}
                self._add(name, groups, hostvars, strict)

    def _add(self, host, groups, hostvars, strict):
        self.inventory.add_host(host)
        for group in groups:
            self.inventory.add_child(self.inventory.add_group(self._sanitize_group_name(group)), host)
        for name, value in hostvars.items():
            self.inventory.set_variable(host, name, value)
        self._set_composite_vars(self.get_option("compose"), hostvars, host, strict)
        self._add_host_to_composed_groups(self.get_option("groups"), hostvars, host, strict)
        self._add_host_to_keyed_groups(self.get_option("keyed_groups"), hostvars, host, strict)


def _allocation_address(alloc, strategy, payload, node_address):
    if strategy == "node":
        address = node_address.get(alloc["NodeID"])
    elif strategy == "network":
        networks = ((alloc["AllocatedResources"] or {}).get("Shared") or {}).get("Networks") or []
        address = networks[0].get("IP") if networks else None
    elif strategy.startswith("service:"):
        for registration in payload["services"]:
            if registration["AllocID"] == alloc["ID"]:
                return {"ansible_host": registration["Address"], "ansible_port": registration["Port"]}
        address = None
    else:
        address = _meta(payload["jobs"][alloc["Namespace"] + "/" + alloc["JobID"]], alloc["TaskGroup"], strategy[len("meta:"):])
    return {"ansible_host": address} if address else {}


def _meta(job, task_group, key):
    group = next((g for g in job["TaskGroups"] or [] if g["Name"] == task_group), {})
    for task in group.get("Tasks") or []:
        if key in (task["Meta"] or {}):
            return task["Meta"][key]
    for meta in (group.get("Meta"), job["Meta"]):
        if meta and key in meta:
            return meta[key]
    return None
