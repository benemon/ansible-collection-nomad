# Examples

Each playbook here runs on its own against a Nomad cluster and removes what
it created at the end, so it can be run repeatedly. Every resource name
carries `prefix`, which defaults to `example`, so the playbooks are safe on a
shared cluster. The connection comes from the extra vars `nomad_address` and
`nomad_token`; when they are left out the plugins read `NOMAD_ADDR` and
`NOMAD_TOKEN`. Pass `--skip-tags cleanup` to keep what a playbook created.

```
ansible-playbook deploy-job.yml -e nomad_address=https://nomad.example.com:4646 -e nomad_token=... -e prefix=demo
```

| Playbook | What it does | Variables |
|---|---|---|
| `namespace-onboarding.yml` | Creates a namespace, an ACL policy scoped to it, a role, and a client token stored in a Nomad variable | `prefix` |
| `deploy-job.yml` | Registers a service job rendered from `templates/web.nomad.hcl.j2`, waits for the deployment, reads it back, scales it by re-registering, then stops and purges it | `prefix`, `driver` (default `raw_exec`), `sleep_seconds` |
| `node-maintenance.yml` | Drains the first ready client node, waits for its allocations to move, then stops the drain and marks it eligible | none |
| `secrets-rotation.yml` | Writes a new password to a Nomad variable and renders it into a file through the `nomad_variable` lookup | `prefix` |
| `enterprise-governance.yml` | Applies a quota to a namespace, adds a soft-mandatory Sentinel policy and registers a job that overrides it; skips the Enterprise steps on a Community server | `prefix`, `driver` (default `raw_exec`) |

`driver` is the task driver of the jobs the playbooks register. The default,
`raw_exec`, runs `/bin/sh` without isolation; on a cluster whose clients do
not enable it, pass `-e driver=exec`.
