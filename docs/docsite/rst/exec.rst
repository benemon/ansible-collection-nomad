.. _ansible_collections.benemon.nomad.docsite.exec:

Running tasks inside allocations
================================

:ansplugin:`benemon.nomad.nomad_exec#connection` runs a play's tasks inside a
task of a running allocation, over the
`allocation exec API <https://developer.hashicorp.com/nomad/api-docs/allocations#exec-allocation>`_
that ``nomad alloc exec`` uses. Nothing is installed in the task and no port
is opened: each command travels through the Nomad server to the client node
and into the task.

The plugin needs nomadpy with its ``exec`` extra, which installs the
``websockets`` package:

.. code-block:: console

   pip install 'nomadpy[exec]'

Hosts
-----

A host is one allocation and one task in it. Two variables name them:

.. list-table::
   :header-rows: 1

   * - Variable
     - Meaning
   * - ``ansible_nomad_alloc_id``
     - the allocation ID, in full
   * - ``ansible_nomad_task``
     - the task to run in
   * - ``ansible_nomad_namespace``
     - the allocation's namespace; falls back to :ansenvvar:`NOMAD_NAMESPACE`

The connection options are the same as everywhere else in the collection,
as ``ansible_nomad_address``, ``ansible_nomad_token`` and so on, with the
same environment fallbacks; see
:ref:`ansible_collections.benemon.nomad.docsite.getting_started`.

The :ansplugin:`benemon.nomad.nomad#inventory` inventory plugin sets the
allocation ID and namespace on every allocation host, so a play over its
hosts needs only the connection and the task name:

.. code-block:: yaml

   # allocations.nomad.yml
   plugin: benemon.nomad.nomad
   clients: false
   allocations: true

.. code-block:: yaml

   - hosts: nomad_job_web
     connection: benemon.nomad.nomad_exec
     vars:
       ansible_nomad_task: web
     tasks:
       - ansible.builtin.command: cat /etc/hostname

An inventory whose groups each run one task can compose the name instead:

.. code-block:: yaml

   compose:
     ansible_nomad_task: nomad_allocation.TaskStates | first

What the task needs
-------------------

Commands run through the shell ``ansible_shell_executable`` names,
``/bin/sh`` by default. Files go in and out over the same channel, as
``cat`` reading its stdin or writing its stdout, so the task image needs a
POSIX shell and ``cat``. Modules need Python in the task, found through
``ansible_python_interpreter`` as on any host; raw commands and ``raw`` do
not.

Modules also need the exec session to deliver the end of stdin. A module's
payload reaches the interpreter over stdin, and so does a file sent to
``cat``. Tasks on the podman driver receive the data but never its end, so
a module there waits until ``ansible_nomad_exec_timeout`` runs out, and
indefinitely when it is unset. Only ``raw`` works in a podman task.
Turning pipelining off does not help, because files travel over stdin too.

Commands run as the task's user. ``become`` is not supported.

``ansible_nomad_exec_timeout`` bounds, in seconds, the wait for the exec
connection to open and for each frame of output. Unset, a wait has no bound.

The ACL policy of the token needs ``alloc-exec`` on the namespace, and
``alloc-node-exec`` as well for tasks on the ``raw_exec`` driver.

Acting on an allocation from outside
------------------------------------

What Nomad can do to an allocation without a command running inside it is
restart, signal and stop, and reading its logs.
:ansplugin:`benemon.nomad.nomad_allocation#module` does the first three
over the API, and :ansplugin:`benemon.nomad.nomad_allocation_info#module`
reads allocations by ID, job or node and returns a task's stdout or stderr.

.. code-block:: yaml

   - name: The job's allocations
     benemon.nomad.nomad_allocation_info:
       job: web
     register: web

   - name: Reload the web task of each one
     benemon.nomad.nomad_allocation:
       alloc_id: "{{ item.ID }}"
       task: web
       signal: SIGHUP
     loop: "{{ web.allocations }}"
     loop_control:
       label: "{{ item.Name }}"

A restart and a signal always act and always report a change; a stop acts
only on an allocation that is still running, and waits for it to finish by
default.
