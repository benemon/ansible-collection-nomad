# benemon.nomad

[![ci](https://github.com/benemon/ansible-collection-nomad/actions/workflows/ci.yml/badge.svg)](https://github.com/benemon/ansible-collection-nomad/actions/workflows/ci.yml) [![codeql](https://github.com/benemon/ansible-collection-nomad/actions/workflows/codeql.yml/badge.svg)](https://github.com/benemon/ansible-collection-nomad/actions/workflows/codeql.yml) [![release](https://github.com/benemon/ansible-collection-nomad/actions/workflows/release.yml/badge.svg)](https://github.com/benemon/ansible-collection-nomad/actions/workflows/release.yml) [![Dependabot Updates](https://github.com/benemon/ansible-collection-nomad/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/benemon/ansible-collection-nomad/actions/workflows/dependabot/dependabot-updates) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/benemon/ansible-collection-nomad/badge)](https://scorecard.dev/viewer/?uri=github.com/benemon/ansible-collection-nomad)

Manage HashiCorp Nomad Community Edition and Nomad Enterprise clusters with
Ansible, over the HTTP API through [nomadpy](https://pypi.org/project/nomadpy/).
Documentation: <https://benemon.github.io/ansible-collection-nomad/branch/main/>.

```yaml
- hosts: localhost
  module_defaults:
    group/benemon.nomad.nomad:
      address: https://nomad.example.com:4646
      token: "{{ nomad_token }}"
  tasks:
    - benemon.nomad.nomad_namespace:
        name: web
        description: Web tier
```

Connection options fall back to the environment variables the Nomad CLI
reads (`NOMAD_ADDR`, `NOMAD_TOKEN`, `NOMAD_NAMESPACE`, `NOMAD_REGION`,
`NOMAD_CACERT`, `NOMAD_CAPATH`, `NOMAD_CLIENT_CERT`, `NOMAD_CLIENT_KEY`,
`NOMAD_TLS_SERVER_NAME`, `NOMAD_SKIP_VERIFY`).

Enterprise features are not checked client-side. On a Community server an
Enterprise request fails with the server's own error.

## Install

Requires ansible-core 2.19 or newer.

```
ansible-galaxy collection install benemon.nomad
pip install -r ~/.ansible/collections/ansible_collections/benemon/nomad/requirements.txt
```

## Plugins

| Plugin | Purpose |
|---|---|
| `nomad_job`, `nomad_job_info` | Register, stop and read jobs; waits for the evaluation and deployment by default |
| `nomad_namespace`, `nomad_namespace_info` | Namespaces, including the Enterprise quota and cluster configuration fields |
| `nomad_node_pool`, `nomad_node_pool_info` | Node pools, including the Enterprise scheduler configuration |
| `nomad_node`, `nomad_node_info` | Node eligibility and drains, waiting for a drain to finish by default |
| `nomad_variable`, `nomad_variable_info` | Nomad variables |
| `nomad_variable` (lookup) | Read a variable, or one of its items, inline |
| `nomad` (inventory) | Client nodes, server members and running allocations as hosts |
| `nomad_acl_policy`, `nomad_acl_policy_info` | ACL policies |
| `nomad_acl_role`, `nomad_acl_role_info` | ACL roles |
| `nomad_acl_token`, `nomad_acl_token_info` | ACL tokens; the secret is returned once, at creation |
| `nomad_quota`, `nomad_quota_info` | Quota specifications (Enterprise) |
| `nomad_sentinel_policy`, `nomad_sentinel_policy_info` | Sentinel policies (Enterprise) |

State modules read first and report a change only when the server's state
differs from the options that were set. An option left out keeps its
current value; a dict option that is set replaces the whole nested
structure. Check mode and diff are supported throughout. Returned
resources are the Nomad API documents, with the API's field names.

The lookup and the inventory plugin do not see `module_defaults`. Pass
`address` and `token` as keyword arguments or inventory file options, or set
the environment variables.

## Tests

Prerequisites: a `.venv` at the repository root holding ansible-core,
nomadpy and pytest on Python 3.14, and `rsync`.

`make units`, `make sanity` and `make integration` run `ansible-test` from a
copy of the repository laid out as `ansible-test` requires. Integration
tests start dev agents from binaries named explicitly; a lane whose
variables are unset is skipped, and at least one lane must be set.

| Variable | Lane |
|---|---|
| `NOMADPY_TEST_CE_BIN` | Community binary |
| `NOMADPY_TEST_ENT_BIN` and `NOMAD_LICENSE_PATH` | Enterprise binary and its licence |

CI runs both lanes when the `NOMAD_LICENCE` repository secret is set.
Without it the Enterprise lane is skipped and the run is still green.

## Releases

A release is a tag `v<version>` matching `version` in `galaxy.yml`. The
release workflow refuses a tag that does not match, requires a green test
run for the tagged commit, builds the collection, publishes it to Ansible
Galaxy with the `ANSIBLE_GALAXY_API_KEY` secret, and creates the GitHub
release.
