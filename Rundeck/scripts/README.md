# Rundeck Scripts

This directory contains the flat set of shell scripts referenced by Rundeck job definitions. The scripts must be available in the Rundeck checkout at `/opt/homelab-server-builds/Rundeck/scripts/`.

`invoke-provision-vm.sh`, `invoke-template-rebuild.sh`, and `invoke-delete-vm.sh` call the deployed Proxmox scripts on TNAS. `power-ai-host.sh` handles the allowlisted AI-host wake/sleep job and verifies the result. `deploy-build-scripts-to-tnas.sh` copies the Proxmox scripts and `scripts/debian-baseline.sh` from the local checkout to the established TNAS paths. `update-github-checkout.sh` refreshes the checkout, imports and updates the YAML definitions in `Rundeck/jobs/` and `Rundeck/pipelines/`, and deletes Rundeck jobs in the managed `jobs` and `pipelines` groups whose UUIDs are no longer in Git. All job YAML files must specify matching `id` and `uuid` values and use one of those two groups.

The checkout job requires the GitHub read token and a Rundeck API token in project Key Storage at `keys/project/HomeLab/github_read_token` and `keys/project/HomeLab/rundeck_api_token`. These are secure job options exposed to the script at runtime; the Rundeck API token must be allowed to import and delete jobs in the HomeLab project.

Keep job `scriptfile` paths, source paths, and TNAS destinations in sync when relocating files.
