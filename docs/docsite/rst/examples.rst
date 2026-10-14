.. _ansible_collections.benemon.nomad.docsite.examples:

Examples
========

The `examples directory <https://github.com/benemon/ansible-collection-nomad/tree/main/examples>`_
of the repository holds five playbooks, each a complete piece of work against
a cluster. This page shows the tasks that carry each one; the linked file is
the whole playbook. Every playbook runs on ``localhost``, sets the connection
once through ``module_defaults``, and removes what it created at the end, so
it can be run repeatedly.

The playbooks take their connection and naming from extra vars:

.. list-table::
   :header-rows: 1

   * - Variable
     - Meaning
   * - ``nomad_address``
     - Address of the Nomad HTTP API. When it is left out the plugins read
       :ansenvvar:`NOMAD_ADDR`.
   * - ``nomad_token``
     - ACL token secret. When it is left out the plugins read
       :ansenvvar:`NOMAD_TOKEN`.
   * - ``prefix``
     - Prefix on the name of every resource a playbook creates, ``example`` by
       default. A prefix of your own keeps the playbooks clear of anything else
       on a shared cluster.
   * - ``driver``
     - Task driver of the jobs the playbooks register, ``raw_exec`` by default.
       On a cluster whose clients do not enable it, pass ``exec``.

.. code-block:: console

   ansible-playbook deploy-job.yml -e nomad_address=https://nomad.example.com:4646 -e nomad_token=... -e prefix=demo

The removal tasks carry the tag ``cleanup``, so ``--skip-tags cleanup`` keeps
what a playbook created.

Namespace onboarding
--------------------

`namespace-onboarding.yml <https://github.com/benemon/ansible-collection-nomad/blob/main/examples/namespace-onboarding.yml>`_
gives a team a namespace, a policy that writes to that namespace only, a role
that grants the policy, and a client token in the role. The token's secret is
stored in a Nomad variable in the namespace, where the team's pipeline reads
it. Every task reports no change on a second run.

.. code-block:: yaml

   - name: Create a policy that writes to the namespace only
     benemon.nomad.nomad_acl_policy:
       name: "{{ prefix }}-web-deploy"
       description: Deploy to the web tier
       rules: |
         namespace "{{ prefix }}-web" {
           policy = "write"
         }

   - name: Create the team's deployment token
     benemon.nomad.nomad_acl_token:
       name: "{{ prefix }}-web-deployer"
       type: client
       roles: ["{{ prefix }}-web-deployers"]
     register: token
     no_log: true

   - name: Store the token where the team's pipeline reads it
     benemon.nomad.nomad_variable:
       path: ci/deployer-token
       namespace: "{{ prefix }}-web"
       items:
         secret: "{{ token.token.SecretID }}"

Deploying a job
---------------

`deploy-job.yml <https://github.com/benemon/ansible-collection-nomad/blob/main/examples/deploy-job.yml>`_
renders a service job from
`templates/web.nomad.hcl.j2 <https://github.com/benemon/ansible-collection-nomad/blob/main/examples/templates/web.nomad.hcl.j2>`_
with the template lookup, registers it and waits for the deployment, reads it
back with :ansplugin:`benemon.nomad.nomad_job_info#module`, scales it by
registering the same template with a higher count, then stops and purges it.
The template takes ``count`` and ``sleep_seconds`` as Jinja variables.

.. code-block:: yaml

   - name: Register the job and wait for its deployment
     benemon.nomad.nomad_job:
       jobspec: "{{ lookup('ansible.builtin.template', 'templates/web.nomad.hcl.j2') }}"
     vars:
       count: 1

   - name: Scale the job by registering it with one more instance
     benemon.nomad.nomad_job:
       jobspec: "{{ lookup('ansible.builtin.template', 'templates/web.nomad.hcl.j2') }}"
     vars:
       count: 2

   - name: Stop the job and remove it from the server
     benemon.nomad.nomad_job:
       name: "{{ prefix }}-web"
       state: absent
       purge: true

Node maintenance
----------------

`node-maintenance.yml <https://github.com/benemon/ansible-collection-nomad/blob/main/examples/node-maintenance.yml>`_
takes the first ready client node out of service: it drains the node and
waits for the allocations to move, runs a placeholder maintenance task, then
stops the drain and marks the node eligible again.

.. code-block:: yaml

   - name: Pick the first ready node
     ansible.builtin.set_fact:
       node_name: "{{ (nodes.nodes | selectattr('Status', 'equalto', 'ready') | first).Name }}"

   - name: Drain the node and wait for its allocations to move
     benemon.nomad.nomad_node:
       name: "{{ node_name }}"
       drain: true
       ignore_system_jobs: true
       deadline: 5m

   - name: Stop the drain and let the scheduler use the node again
     benemon.nomad.nomad_node:
       name: "{{ node_name }}"
       drain: false
       mark_eligible: true

Rotating a secret
-----------------

`secrets-rotation.yml <https://github.com/benemon/ansible-collection-nomad/blob/main/examples/secrets-rotation.yml>`_
writes a new password to a Nomad variable, then renders the variable into a
file through :ansplugin:`benemon.nomad.nomad_variable#lookup`. The lookup
does not see ``module_defaults``, so the template passes the connection
itself; an unset value falls back to the environment.

.. code-block:: yaml

   - name: Write a new password to the variable
     benemon.nomad.nomad_variable:
       path: "{{ prefix }}/db/credentials"
       items:
         username: app
         password: "{{ lookup('ansible.builtin.password', '/dev/null', length=24) }}"

   - name: Render the credentials into it through the lookup
     ansible.builtin.template:
       src: templates/app.env.j2
       dest: "{{ env_file.path }}"
       mode: "0600"

.. code-block:: jinja

   {% set credentials = lookup('benemon.nomad.nomad_variable', prefix ~ '/db/credentials', address=nomad_address | default(none), token=nomad_token | default(none)) %}
   DB_USERNAME={{ credentials.username }}
   DB_PASSWORD={{ credentials.password }}

Enterprise governance
---------------------

`enterprise-governance.yml <https://github.com/benemon/ansible-collection-nomad/blob/main/examples/enterprise-governance.yml>`_
creates a quota, a namespace under it, and a soft-mandatory Sentinel policy
that refuses jobs above priority 50, then registers a priority 80 job with
``policy_override``. The first task reads the quota specifications, an
endpoint only Enterprise serves; a Community server answers 501, which the
task does not treat as a failure, and the Enterprise block is skipped. See
:ref:`ansible_collections.benemon.nomad.docsite.enterprise`.

.. code-block:: yaml

   - name: Read the quota specifications, which only an Enterprise server serves
     benemon.nomad.nomad_quota_info:
     register: quotas
     failed_when: quotas is failed and quotas.status_code != 501

   - name: Apply governance on an Enterprise server
     when: quotas.quotas is defined
     block:
       - name: Refuse high-priority jobs unless an operator overrides
         benemon.nomad.nomad_sentinel_policy:
           name: "{{ prefix }}-priority"
           description: Jobs above priority 50 need an override
           scope: submit-job
           enforcement_level: soft-mandatory
           policy: main = rule { job.priority <= 50 }

       - name: Register a high-priority job with the override
         benemon.nomad.nomad_job:
           jobspec: "{{ nightly_job }}"
           namespace: "{{ prefix }}-batch"
           policy_override: true

A namespace with a quota attached cannot be deleted, so the playbook detaches
the quota before it removes the namespace and the quota.
