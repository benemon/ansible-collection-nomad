.. _ansible_collections.benemon.nomad.docsite.inventory:

Inventory
=========

:ansplugin:`benemon.nomad.nomad#inventory` builds an inventory from a Nomad
cluster. By default the hosts are the client nodes. Server members and
running allocations are added on request.

The plugin reads a file whose name ends in ``nomad.yml`` or ``nomad.yaml``:

.. code-block:: yaml

   # cluster.nomad.yml
   plugin: benemon.nomad.nomad
   address: https://nomad.example.com:4646

.. code-block:: console

   ansible-inventory -i cluster.nomad.yml --graph

Connection options are the ones every plugin in the collection takes, with
the same environment fallbacks; see
:ref:`ansible_collections.benemon.nomad.docsite.getting_started`. The plugin
is outside the action group and does not see ``module_defaults``.

Host variables
--------------

Each host carries the Nomad API document it was built from, with the API's
field names, and with it every address the API attaches to that host. The
plugin sets no ``ansible_host``: the inventory file chooses one with
``compose``, and :ref:`ansible_collections.benemon.nomad.docsite.inventory_addresses`
gives the expression for each kind of host.

.. list-table::
   :header-rows: 1

   * - Host
     - Name
     - Variables
   * - Client node
     - the node's ``Name``
     - ``nomad_node``, the `node list <https://developer.hashicorp.com/nomad/api-docs/nodes#list-nodes>`_ stub, or the full document with ``node_detail``
   * - Server member
     - the member's ``Name``, which Nomad writes as ``<node>.<region>``
     - ``nomad_member``, the `agent members <https://developer.hashicorp.com/nomad/api-docs/agent#list-members>`_ entry
   * - Allocation
     - ``<namespace>.<job>.<group>.<index>``
     - ``nomad_allocation``, the `allocation list <https://developer.hashicorp.com/nomad/api-docs/allocations#list-allocations>`_ stub with ``AllocatedResources``; ``ansible_nomad_alloc_id`` and ``ansible_nomad_namespace``; ``nomad_services`` with ``services: true``

Groups
------

Hosts are placed in groups by the fields of their document. Group names pass
through Ansible's usual sanitising, so a datacenter ``eu-west`` gives
``nomad_datacenter_eu_west``.

.. list-table::
   :header-rows: 1

   * - Group
     - Members
   * - ``nomad_clients``
     - every client node
   * - ``nomad_datacenter_<dc>``
     - client nodes and server members in the datacenter
   * - ``nomad_node_pool_<pool>``
     - client nodes in the node pool
   * - ``nomad_node_class_<class>``
     - client nodes with a node class
   * - ``nomad_status_<status>``
     - client nodes by ``Status``
   * - ``nomad_eligibility_<eligibility>``
     - client nodes by ``SchedulingEligibility``
   * - ``nomad_driver_<driver>``
     - client nodes on which the driver is detected
   * - ``nomad_servers``
     - every server member
   * - ``nomad_allocations``
     - every running allocation
   * - ``nomad_namespace_<namespace>``
     - allocations in the namespace
   * - ``nomad_job_<job>``
     - allocations of the job

The ``keyed_groups``, ``groups`` and ``compose`` options of the
``constructed`` fragment add groups and variables from any field of the host
variables:

.. code-block:: yaml

   plugin: benemon.nomad.nomad
   keyed_groups:
     - key: nomad_node.Attributes['os.name']
       prefix: os
   compose:
     nomad_version: nomad_node.Version

Allocation hosts
----------------

With ``allocations: true`` every running allocation is a host, named
``<namespace>.<job>.<group>.<index>``: allocation ``web.web[0]`` in the
``default`` namespace is the host ``default.web.web.0``. The API's own
allocation name contains ``[0]``, which an Ansible host pattern reads as a
group slice, and names repeat across namespaces. ``namespace`` selects the
namespace whose allocations are listed and defaults to ``*``, every namespace
the token can read.

``services: true`` reads the service registrations of the listed namespaces,
one request per service name, and ``nomad_services`` is the list of
registrations the allocation made, empty when it made none.

A task with no address of its own, in a container or a chroot, is reached
through :ref:`ansible_collections.benemon.nomad.docsite.exec` instead. Every
allocation host carries the ``ansible_nomad_alloc_id`` and
``ansible_nomad_namespace`` that connection needs; the task name is set in
the play or composed from ``nomad_allocation.TaskStates``.

.. _ansible_collections.benemon.nomad.docsite.inventory_addresses:

Choosing the address
--------------------

``compose`` entries are Jinja expressions evaluated per host against that
host's variables, so ``nomad_member is defined`` is how one line applies to
members only. The addresses below are the ones the API attaches to each kind
of host; none of them is checked for reachability.

Server members
   ``Addr`` is the Serf gossip address and ``Tags.rpc_addr`` the RPC
   advertise address. On a flat network they are the same; where the servers
   run in containers or pods they differ, and the RPC address is the routable
   one.

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      clients: false
      servers: true
      compose:
        ansible_host: nomad_member.Tags.rpc_addr

Client nodes
   ``Address`` is the HTTP advertise address, one per node however many
   interfaces it has.

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      compose:
        ansible_host: nomad_node.Address

   The API does not carry a multihomed node's other addresses: with
   ``node_detail: true`` the full document adds ``HostNetworks``, which holds
   the configured ranges rather than the node's address in them, and
   ``Attributes['unique.network.ip-address']``, which is the default-route
   interface. A node reached on an interface the agent does not advertise is
   named instead, by the hostname the agent fingerprinted or by a ``meta``
   value set in the client configuration:

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      node_detail: true
      compose:
        ansible_host: nomad_node.Attributes['unique.hostname'] ~ '.mgmt.example.com'

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      node_detail: true
      compose:
        ansible_host: nomad_node.Meta.ansible_host

Allocations by host-mapped port
   ``AllocatedResources.Shared.Ports`` lists each port the group maps on the
   node, with ``Label``, ``HostIP`` and ``Value``. A virtual machine whose
   group labels its SSH port ``ssh``:

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      clients: false
      allocations: true
      namespace: vms
      compose:
        ansible_host: (nomad_allocation.AllocatedResources.Shared.Ports | selectattr('Label', 'eq', 'ssh') | first).HostIP
        ansible_port: (nomad_allocation.AllocatedResources.Shared.Ports | selectattr('Label', 'eq', 'ssh') | first).Value

Allocations by service registration
   ``nomad_services`` holds the ``Address`` and ``Port`` the task registered
   as a `Nomad service <https://developer.hashicorp.com/nomad/docs/job-specification/service>`_.
   The same fleet, reached at the address each guest registered as ``ssh``:

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      clients: false
      allocations: true
      services: true
      compose:
        ansible_host: (nomad_services | selectattr('ServiceName', 'eq', 'ssh') | first).Address
        ansible_port: (nomad_services | selectattr('ServiceName', 'eq', 'ssh') | first).Port

Allocations by bridge address
   ``AllocatedResources.Shared.Networks[].IP`` is the task's own address in
   ``bridge`` or CNI network mode, reachable from the node it runs on. A
   controller on that node, or a play delegated to it:

   .. code-block:: yaml

      compose:
        ansible_host: nomad_allocation.AllocatedResources.Shared.Networks[0].IP

Allocations by node
   A task in ``host`` network mode shares the node's address. The allocation
   document names the node, ``NodeName``, and every host-mapped port carries
   the node's address as ``HostIP``; ``compose`` sees only the host's own
   variables, so the node's document is not reachable from the allocation.

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      clients: false
      allocations: true
      compose:
        ansible_host: (nomad_allocation.AllocatedResources.Shared.Ports | first).HostIP

   Where node names resolve in DNS, the name alone does:

   .. code-block:: yaml

      compose:
        ansible_host: nomad_allocation.NodeName

One inventory for all three
   A single expression serves a mixed inventory by testing which document the
   host carries. This one reaches members by RPC address, nodes by advertise
   address, allocations with ports by the node address those ports are mapped
   on, and the rest by node name:

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      servers: true
      allocations: true
      compose:
        ansible_host: >-
          nomad_member.Tags.rpc_addr if nomad_member is defined
          else nomad_node.Address if nomad_node is defined
          else (nomad_allocation.AllocatedResources.Shared.Ports | first).HostIP if nomad_allocation.AllocatedResources.Shared.Ports
          else nomad_allocation.NodeName

Node detail
-----------

The node list stub carries ``Drivers`` and the resource fields;
``Attributes``, ``Meta``, ``Links`` and ``HostVolumes`` are in the
`node read <https://developer.hashicorp.com/nomad/api-docs/nodes#read-node>`_
document only. ``node_detail: true`` reads every client node in full, one
request per node, and ``nomad_node`` becomes that document. The full
document has no ``Address``; ``HTTPAddr`` carries the same address with its
port.

Caching
-------

The ``inventory_cache`` options apply. One run's reads are stored as the
documents above and the next run builds the same hosts from them without
touching the API, until the cache times out or ``--flush-cache`` is given.

.. code-block:: yaml

   plugin: benemon.nomad.nomad
   cache: true
   cache_plugin: ansible.builtin.jsonfile
   cache_connection: /tmp/nomad-inventory
   cache_timeout: 300
