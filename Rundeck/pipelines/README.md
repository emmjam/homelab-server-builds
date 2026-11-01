# Rundeck Pipelines

Complete, approved workflows live directly in this directory. Their Rundeck group is `pipelines`. Pipeline steps invoke reusable jobs by UUID, pass required options explicitly, stop on failures, and summarize useful outputs.

Current workflows cover VM creation and deletion through `Proxmox - Manage VM`, Debian template rebuilding, and TNAS script synchronization. `Proxmox - Manage VM` uses Rundeck Conditional Logic; see `Rundeck/README.md` for the Rundeck 6.3.0 availability and edition note. The VM workflow runs checkout refresh and script deployment only for creation; deletion invokes the delete operation directly.
