# Rundeck Jobs

Reusable, independently runnable operations live directly in this directory. Their Rundeck group is `jobs`. Definitions preserve their UUIDs and list required options, descriptions, and execution steps.

`Proxmox - Delete VM` accepts an exact VM name or numeric ID. It refuses template VMs, immediately stops a running VM with `qm stop`, then purges it.

Pipelines live in `Rundeck/pipelines/` and reference reusable jobs by UUID rather than duplicating their implementation.
