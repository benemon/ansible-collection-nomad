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
plugin sets ``ansible_host`` only where the API gives one address.

.. list-table::
   :header-rows: 1

   * - Host
     - Name
     - ``ansible_host``
     - Variables
   * - Client node
     - the node's ``Name``
     - the node's ``Address``
     - ``nomad_node``, the `node list <https://developer.hashicorp.com/nomad/api-docs/nodes#list-nodes>`_ stub
   * - Server member
     - the member's ``Name``, which Nomad writes as ``<node>.<region>``
     - the member's ``Addr``
     - ``nomad_member``, the `agent members <https://developer.hashicorp.com/nomad/api-docs/agent#list-members>`_ entry
   * - Allocation
     - ``<namespace>.<job>.<group>.<index>``
     - not set; see below
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

An allocation has several addresses, and which one reaches it depends on the
task driver and the network mode, so the plugin sets none. The document
carries them all:

.. list-table::
   :header-rows: 1

   * - Address
     - Where it is
     - Reaches
   * - host-mapped port
     - ``nomad_allocation.AllocatedResources.Shared.Ports``, each with ``Label``, ``HostIP`` and ``Value``
     - a port the task exposes on the node, such as a guest's SSH
   * - bridge address
     - ``nomad_allocation.AllocatedResources.Shared.Networks[].IP``
     - the task's own address in ``bridge`` or CNI network mode, from the node
   * - node
     - ``nomad_allocation.NodeName``, the host of the same name in ``nomad_clients``
     - a task in ``host`` network mode
   * - service registration
     - ``nomad_services``, with ``services: true``
     - the ``Address`` and ``Port`` the task registered as a `Nomad service <https://developer.hashicorp.com/nomad/docs/job-specification/service>`_

``compose`` chooses. A fleet of virtual machines whose groups label their SSH
port ``ssh``:

.. code-block:: yaml

   plugin: benemon.nomad.nomad
   clients: false
   allocations: true
   namespace: vms
   compose:
     ansible_host: (nomad_allocation.AllocatedResources.Shared.Ports | selectattr('Label', 'eq', 'ssh') | first).HostIP
     ansible_port: (nomad_allocation.AllocatedResources.Shared.Ports | selectattr('Label', 'eq', 'ssh') | first).Value

The same fleet reached at the address each guest registered as the service
``ssh``:

.. code-block:: yaml

   plugin: benemon.nomad.nomad
   clients: false
   allocations: true
   services: true
   compose:
     ansible_host: (nomad_services | selectattr('ServiceName', 'eq', 'ssh') | first).Address
     ansible_port: (nomad_services | selectattr('ServiceName', 'eq', 'ssh') | first).Port

``services: true`` reads the service registrations of the listed namespaces,
one request per service name, and ``nomad_services`` is the list of
registrations the allocation made, empty when it made none.

A task with no address of its own, in a container or a chroot, is reached
through :ref:`ansible_collections.benemon.nomad.docsite.exec` instead. Every
allocation host carries the ``ansible_nomad_alloc_id`` and
``ansible_nomad_namespace`` that connection needs; the task name is set in
the play or composed from ``nomad_allocation.TaskStates``.

Node detail
-----------

The node list stub carries ``Drivers`` and the resource fields;
``Attributes``, ``Meta``, ``Links`` and ``HostVolumes`` are in the
`node read <https://developer.hashicorp.com/nomad/api-docs/nodes#read-node>`_
document only. ``node_detail: true`` reads every client node in full, one
request per node, and ``nomad_node`` becomes that document. ``ansible_host``
stays the address from the list, which the full document does not carry.

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
