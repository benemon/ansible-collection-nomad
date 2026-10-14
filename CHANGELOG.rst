===========================
benemon.nomad Release Notes
===========================

.. contents:: Topics

v0.1.0
======

Release Summary
---------------

First release of the ``benemon.nomad`` collection: modules and ``_info`` twins for jobs, namespaces, node pools,
nodes, variables, ACL policies, roles and tokens, quotas and Sentinel policies, and a lookup for variables,
all over the Nomad HTTP API through nomadpy.

New Plugins
-----------

Lookup
~~~~~~

- benemon.nomad.nomad_variable - Read a Nomad variable.

New Modules
-----------

- benemon.nomad.nomad_acl_policy - Manage a Nomad ACL policy.
- benemon.nomad.nomad_acl_policy_info - Read Nomad ACL policies.
- benemon.nomad.nomad_acl_role - Manage a Nomad ACL role.
- benemon.nomad.nomad_acl_role_info - Read Nomad ACL roles.
- benemon.nomad.nomad_acl_token - Manage a Nomad ACL token.
- benemon.nomad.nomad_acl_token_info - Read Nomad ACL tokens.
- benemon.nomad.nomad_job - Register or stop a Nomad job.
- benemon.nomad.nomad_job_info - Read Nomad jobs.
- benemon.nomad.nomad_namespace - Manage a Nomad namespace.
- benemon.nomad.nomad_namespace_info - Read Nomad namespaces.
- benemon.nomad.nomad_node - Set the scheduling eligibility or drain of a Nomad node.
- benemon.nomad.nomad_node_info - Read Nomad client nodes.
- benemon.nomad.nomad_node_pool - Manage a Nomad node pool.
- benemon.nomad.nomad_node_pool_info - Read Nomad node pools.
- benemon.nomad.nomad_quota - Manage a Nomad quota specification.
- benemon.nomad.nomad_quota_info - Read Nomad quota specifications.
- benemon.nomad.nomad_sentinel_policy - Manage a Nomad Sentinel policy.
- benemon.nomad.nomad_sentinel_policy_info - Read Nomad Sentinel policies.
- benemon.nomad.nomad_variable - Manage a Nomad variable.
- benemon.nomad.nomad_variable_info - Read Nomad variables.
