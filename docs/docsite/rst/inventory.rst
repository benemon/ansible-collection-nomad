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
field names:

.. list-table::
   :header-rows: 1

   * - Host
     - Name
     - ``ansible_host``
     - Variable
   * - Client node
     - the node's ``Name``
     - the node's ``Address``
     - ``nomad_node``, the `node list <https://developer.hashicorp.com/nomad/api-docs/nodes#list-nodes>`_ stub
   * - Server member
     - the member's ``Name``, which Nomad writes as ``<node>.<region>``
     - the member's ``Addr``
     - ``nomad_member``, the `agent members <https://developer.hashicorp.com/nomad/api-docs/agent#list-members>`_ entry
   * - Allocation
     - see below
     - chosen by ``allocation_address``
     - ``nomad_allocation``, the `allocation list <https://developer.hashicorp.com/nomad/api-docs/allocations#list-allocations>`_ stub with ``AllocatedResources``

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

With ``allocations: true`` every running allocation is a host. Task drivers
such as QEMU run guests that Ansible reaches directly, so an allocation host
needs an address; ``allocation_address`` says where it comes from.

The host name is ``<namespace>.<job>.<group>.<index>``: allocation
``web.web[0]`` in the ``default`` namespace is the host ``default.web.web.0``.
The API's own allocation name contains ``[0]``, which an Ansible host pattern
reads as a group slice, and names repeat across namespaces.

``namespace`` selects the namespace whose allocations are listed and defaults
to ``*``, every namespace the token can read.

``node``
   The default. The address of the node the allocation runs on. Right for
   tasks that share the node's network, and the only strategy that needs no
   more than the node and allocation lists.

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      allocations: true

``network``
   The ``IP`` of the first network in the allocation's ``AllocatedResources``:
   the bridge or CNI address of a group with a ``network`` block in a mode
   other than ``host``.

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      allocations: true
      allocation_address: network

``service:<name>``
   The ``Address`` and ``Port`` the allocation registered for the named
   `Nomad service <https://developer.hashicorp.com/nomad/docs/job-specification/service>`_
   (``provider = "nomad"``). ``ansible_port`` is set as well. A guest that
   registers its SSH port as a service is reached at that port.

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      clients: false
      allocations: true
      namespace: vms
      allocation_address: service:ssh

``meta:<key>``
   The value of the key in the job's
   `meta <https://developer.hashicorp.com/nomad/docs/job-specification/meta>`_,
   looking first at the tasks of the allocation's task group, then at the task
   group, then at the job. One job read per job with running allocations.

   .. code-block:: yaml

      plugin: benemon.nomad.nomad
      allocations: true
      allocation_address: meta:ansible_host

An allocation whose address is not found by the chosen strategy is still a
host, without ``ansible_host``.

Every allocation host also carries ``ansible_nomad_alloc_id`` and
``ansible_nomad_namespace``, and ``ansible_nomad_task`` when its task group
has one task, so :ref:`ansible_collections.benemon.nomad.docsite.exec` works
on it without further variables.

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
