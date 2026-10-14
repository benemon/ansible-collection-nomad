.. _ansible_collections.benemon.nomad.docsite.enterprise:

Enterprise behaviour
====================

The collection presents Community and Enterprise surfaces identically. There is
no licence detection and no client-side check of the edition: a request the
server will not serve fails the task through the same path as any other
refused request, with the server's message in ``msg`` and the HTTP status in
``status_code``.

Which endpoints and fields are Enterprise is stated by the
`Nomad API documentation <https://developer.hashicorp.com/nomad/api-docs>`_,
and each plugin option carries the same label in its description.

Enterprise surfaces
-------------------

Endpoints
   :ansplugin:`benemon.nomad.nomad_quota#module`,
   :ansplugin:`benemon.nomad.nomad_quota_info#module`,
   :ansplugin:`benemon.nomad.nomad_sentinel_policy#module` and
   :ansplugin:`benemon.nomad.nomad_sentinel_policy_info#module`.
   `Quotas <https://developer.hashicorp.com/nomad/api-docs/quotas>`_ and
   `Sentinel policies <https://developer.hashicorp.com/nomad/api-docs/sentinel-policies>`_
   need the Governance and Policy module on the licence. Sentinel policies also
   need ACLs enabled on the server.

Fields on Community resources
   :ansopt:`benemon.nomad.nomad_namespace#module:quota`,
   :ansopt:`benemon.nomad.nomad_namespace#module:node_pool_configuration`,
   :ansopt:`benemon.nomad.nomad_namespace#module:vault_configuration` and
   :ansopt:`benemon.nomad.nomad_namespace#module:consul_configuration` on a
   namespace; :ansopt:`benemon.nomad.nomad_node_pool#module:scheduler_configuration`
   on a node pool; :ansopt:`benemon.nomad.nomad_job#module:policy_override` on
   a job registration.

What a Community server answers
-------------------------------

The responses below are what Nomad Community 2.0.5 returns. The collection's
integration tests assert them on the Community lane.

.. list-table::
   :header-rows: 1

   * - Request
     - ``status_code``
     - ``msg``
   * - Any quota or Sentinel policy task
     - 501
     - ``Nomad Enterprise only endpoint``
   * - A namespace with ``quota`` set
     - 500
     - names the quota specification the server cannot find
   * - A node pool with ``scheduler_configuration`` set
     - 500
     - ``Feature "Node Pools Governance" is unlicensed``

A play that runs against both editions can branch on the status:

.. code-block:: yaml

   - name: Apply the quota where the server supports it
     benemon.nomad.nomad_quota:
       name: web
       limits:
         - region: global
           region_limit:
             cpu: 2500
             memory_mb: 1000
     register: quota
     failed_when: quota is failed and quota.status_code != 501

Reading an Enterprise resource with an ``_info`` module on a Community server
fails the same way; the module does not translate the refusal into an empty
list.
