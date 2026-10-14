.. _ansible_collections.benemon.nomad.docsite.jobs:

Jobs
====

:ansplugin:`benemon.nomad.nomad_job#module` registers a job from its
specification and :ansplugin:`benemon.nomad.nomad_job_info#module` reads jobs
back. Both are in the ``default`` namespace unless ``namespace`` or
:ansenvvar:`NOMAD_NAMESPACE` says otherwise.

The jobspec option
------------------

:ansopt:`benemon.nomad.nomad_job#module:jobspec` takes the job specification in
one of three forms. The module decides which by looking at the value.

HCL text
   A string that is not JSON is sent to the server's parse endpoint and
   converted there, and the registration carries the source as the job's
   submission, so the cluster keeps the specification as written and the
   UI shows it beside the canonical document. The `job specification <https://developer.hashicorp.com/nomad/docs/job-specification>`_
   must be valid for the server's version; no HCL is parsed on the controller.

   .. code-block:: yaml

      - name: Register a job from an HCL file
        benemon.nomad.nomad_job:
          jobspec: "{{ lookup('ansible.builtin.file', 'web.nomad.hcl') }}"

      - name: Register a job from an HCL template
        benemon.nomad.nomad_job:
          jobspec: "{{ lookup('ansible.builtin.template', 'web.nomad.hcl.j2') }}"
          namespace: web

JSON document as text
   A string that parses as a JSON object is used as the job document directly.
   This is the shape ``nomad job run -output`` prints and the
   `JSON job specification <https://developer.hashicorp.com/nomad/api-docs/json-jobs>`_
   documents.

   .. code-block:: yaml

      - name: Register a job from its JSON document
        benemon.nomad.nomad_job:
          jobspec: "{{ lookup('ansible.builtin.file', 'web.json') }}"

The document itself
   A dict is used as the job document without conversion. It can come from a
   variable, from ``from_json`` or ``from_yaml`` on a file, or be written
   inline in the play.

   .. code-block:: yaml

      - name: Register a job from a document held in a variable
        benemon.nomad.nomad_job:
          jobspec: "{{ lookup('ansible.builtin.file', 'web.json') | from_json }}"

      - name: Register a job written inline
        benemon.nomad.nomad_job:
          jobspec:
            ID: web
            Name: web
            Type: service
            Datacenters: [dc1]
            TaskGroups:
              - Name: web
                Tasks:
                  - Name: web
                    Driver: docker
                    Config:
                      image: nginx:1.27

In every form the document must carry an ``ID``, so
:ansopt:`benemon.nomad.nomad_job#module:name` is not set with a specification.
The same rule holds for :ansopt:`benemon.nomad.nomad_job#module:namespace` and
:ansopt:`benemon.nomad.nomad_job#module:region`: a value is given either on the
module or in the specification, and the task fails when both carry one. Nothing
is overridden and nothing is ignored. A document read back from the API carries
all three, so a round trip is registered without those options; a specification
meant to be registered under several names or namespaces is a template.

HCL variables
-------------

An HCL specification may declare ``variable`` blocks and use them as
``var.name``. Values for them go in
:ansopt:`benemon.nomad.nomad_job#module:hcl_variables`, which the module
passes to the server's parse endpoint; a variable with no default must be
supplied there. The option is for HCL input only, and the task fails when it
is given with a document, so a value is never silently ignored.

.. code-block:: yaml

   - name: Register a specification that declares variables
     benemon.nomad.nomad_job:
       jobspec: "{{ lookup('ansible.builtin.file', 'web.nomad.hcl') }}"
       hcl_variables:
         count: 3
         image: nginx:1.27

Values are strings, numbers, booleans or lists of those. A specification
that needs more structure than that is a template.

Change detection and diff
-------------------------

The server's plan endpoint decides whether the submitted document changes
anything. A job that is already registered in that form reports
``changed: false`` and returns the job as the server holds it. The plan is also
what check mode reports.

The diff shows the job document on the server as ``before`` and the submitted
document as ``after``. The two come from different sources, so fields the server
fills in at registration, such as ``CreateIndex``, ``Version`` and ``Status``,
appear in ``before`` only, and a diff can show lines the plan does not count
as a change.

Waiting
-------

By default a registration waits. The module blocks on the evaluation the
registration created until it completes, then, for a job that has a deployment,
on the latest deployment until it reaches a terminal status. A deployment that
ends anywhere other than ``successful`` fails the task, as does an evaluation
whose allocations cannot all be placed; the failed deployment or the
``FailedTGAllocs`` of the evaluation are in the failure result.

:ansopt:`benemon.nomad.nomad_job#module:timeout` bounds the whole wait, 300
seconds by default. With :ansopt:`benemon.nomad.nomad_job#module:wait=false`
the task returns as soon as the server accepts the registration, with
:ansretval:`benemon.nomad.nomad_job#module:eval_id` for the caller to follow.

The returned :ansretval:`benemon.nomad.nomad_job#module:job` is read back after
the wait, and :ansretval:`benemon.nomad.nomad_job#module:deployment` is the
deployment the module waited for, when there was one.

Stopping
--------

:ansopt:`benemon.nomad.nomad_job#module:state=absent` stops the job named by
:ansopt:`benemon.nomad.nomad_job#module:name`. A job that is already stopped
reports no change unless :ansopt:`benemon.nomad.nomad_job#module:purge=true`
asks for it to be removed from the server as well. Stopping waits for its
evaluation under the same :ansopt:`benemon.nomad.nomad_job#module:wait` and
:ansopt:`benemon.nomad.nomad_job#module:timeout`.

.. code-block:: yaml

   - name: Stop and purge a job
     benemon.nomad.nomad_job:
       name: web
       state: absent
       purge: true

Reading
-------

:ansplugin:`benemon.nomad.nomad_job_info#module` returns one job in full by
:ansopt:`benemon.nomad.nomad_job_info#module:name`, or without it the list stubs
the `jobs list endpoint <https://developer.hashicorp.com/nomad/api-docs/jobs#list-jobs>`_
returns for the namespace. A job that does not exist is an empty list.
