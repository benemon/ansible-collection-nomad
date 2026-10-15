# Copyright (c) 2026 Benjamin Holmes
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations

DOCUMENTATION = r"""
name: nomad
short_description: Nomad client nodes, server members and allocations as hosts
version_added: 0.2.0
description:
  - Lists the client nodes of a Nomad cluster as hosts, and on request its server members and running allocations.
  - Host variables are the Nomad API documents with the API's field names, carrying every address the API attaches to
    a host. The plugin sets no C(ansible_host); the inventory file chooses one with O(compose), and the guide shows the
    expression for each kind of host.
  - Allocation hosts carry the allocation ID and namespace that P(benemon.nomad.nomad_exec#connection) needs.
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
      - Namespace whose allocations and service registrations are listed.
      - V(*) is every namespace the token can read.
    type: str
    default: "*"
  services:
    description:
      - Read the Nomad service registrations of the listed namespaces, one request per service name, and set
        C(nomad_services) on each allocation host to the registrations it made.
    type: bool
    default: false
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
# cluster.nomad.yml: client nodes at their advertised address, grouped by datacenter, node pool, class, status,
# eligibility and driver
plugin: benemon.nomad.nomad
address: https://nomad.example.com:4646
compose:
  ansible_host: nomad_node.Address

# Server members at their RPC address, client nodes at their advertised address
plugin: benemon.nomad.nomad
servers: true
compose:
  ansible_host: nomad_member.Tags.rpc_addr if nomad_member is defined else nomad_node.Address

# Virtual machines run as allocations: reach each guest at the host-mapped port its group labels "ssh"
plugin: benemon.nomad.nomad
clients: false
allocations: true
namespace: vms
compose:
  ansible_host: (nomad_allocation.AllocatedResources.Shared.Ports | selectattr('Label', 'eq', 'ssh') | first).HostIP
  ansible_port: (nomad_allocation.AllocatedResources.Shared.Ports | selectattr('Label', 'eq', 'ssh') | first).Value
keyed_groups:
  - key: nomad_allocation.JobID
    prefix: vm

# Or at the address a task registered as the Nomad service "ssh"
plugin: benemon.nomad.nomad
clients: false
allocations: true
services: true
compose:
  ansible_host: (nomad_services | selectattr('ServiceName', 'eq', 'ssh') | first).Address
  ansible_port: (nomad_services | selectattr('ServiceName', 'eq', 'ssh') | first).Port
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
SHAPE_OPTIONS = ("clients", "servers", "allocations", "namespace", "services", "node_detail")


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = "benemon.nomad.nomad"

    def verify_file(self, path):
        return super().verify_file(path) and path.endswith(("nomad.yml", "nomad.yaml"))

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path)
        if not HAS_NOMADPY:
            raise AnsibleParserError(missing_required_lib("nomadpy") + "\n" + NOMADPY_IMPORT_ERROR)
        self._read_config_data(path)
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
            payload = self._fetch()
            payload["shape"] = shape
            if use_cache:
                self._cache[cache_key] = payload
        self._populate(payload)

    def _fetch(self):
        """_fetch reads what the configured hosts need and returns it as plain documents, the shape the cache holds."""
        client = client_from_options({name: self.get_option(name) for name in NOMAD_ARGUMENT_SPEC})
        namespace = self.get_option("namespace")
        payload = {}
        try:
            if self.get_option("clients"):
                stubs = client.nodes.list()[0]
                payload["nodes"] = [n.to_json() for n in stubs]
                if self.get_option("node_detail"):
                    payload["node_detail"] = {n.id: client.nodes.info(n.id)[0].to_json() for n in stubs}
            if self.get_option("servers"):
                payload["members"] = [m.to_json() for m in client.agent.members().members or []]
            if self.get_option("allocations"):
                q = QueryOptions(namespace=namespace, params={"resources": "true"})
                payload["allocations"] = [a.to_json() for a in client.allocations.list(q)[0] if a.client_status == "running"]
                if self.get_option("services"):
                    payload["services"] = []
                    for listed in client.services.list(QueryOptions(namespace=namespace))[0]:
                        for service in listed.services or []:
                            registrations = client.services.get(service.service_name, QueryOptions(namespace=listed.namespace))[0]
                            payload["services"] += [r.to_json() for r in registrations]
        except UnexpectedResponseError as e:
            raise AnsibleParserError("reading from Nomad: %s" % e) from e
        except urllib.error.URLError as e:
            raise AnsibleParserError("cannot reach Nomad: %s" % e.reason) from e
        return payload

    def _populate(self, payload):
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
                self._add(stub["Name"], groups, {"nomad_node": detail.get(stub["ID"], stub)}, strict)
        if self.get_option("servers"):
            for member in payload["members"]:
                groups = ["nomad_servers"]
                datacenter = (member["Tags"] or {}).get("dc")
                if datacenter:
                    groups.append("nomad_datacenter_" + datacenter)
                self._add(member["Name"], groups, {"nomad_member": member}, strict)
        if self.get_option("allocations"):
            registrations = payload.get("services")
            for alloc in payload["allocations"]:
                name = alloc["Namespace"] + "." + INDEX.sub(r".\1", alloc["Name"])
                groups = ["nomad_allocations", "nomad_namespace_" + alloc["Namespace"], "nomad_job_" + alloc["JobID"]]
                hostvars = {"nomad_allocation": alloc, "ansible_nomad_alloc_id": alloc["ID"], "ansible_nomad_namespace": alloc["Namespace"]}
                if registrations is not None:
                    hostvars["nomad_services"] = [r for r in registrations if r["AllocID"] == alloc["ID"]]
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
