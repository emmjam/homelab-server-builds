# Rundeck Pipelines

Complete, approved workflows live directly in this directory. Their Rundeck group is `pipelines`. Pipeline steps invoke reusable jobs by UUID, pass required options explicitly, stop on failures, and summarize useful outputs.

Current workflows cover VM creation and deletion through `Proxmox - Manage VM`, Debian template rebuilding, and TNAS script synchronization. `Proxmox - Manage VM` dispatches the existing child jobs through the Rundeck API from the `localhost` node; see `Rundeck/README.md` for its Key Storage token requirement. The VM workflow runs checkout refresh and script deployment only for creation; deletion invokes the delete operation directly.
