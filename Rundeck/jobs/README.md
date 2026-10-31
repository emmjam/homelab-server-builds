# Rundeck Jobs

Reusable, independently runnable operations live directly in this directory. Their Rundeck group is `jobs`. Definitions preserve their UUIDs and list required options, descriptions, and execution steps.

Pipelines live in `Rundeck/pipelines/` and reference reusable jobs by UUID rather than duplicating their implementation.
