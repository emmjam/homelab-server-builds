# Rundeck Scripts

This directory contains the flat set of shell scripts referenced by Rundeck job definitions. The scripts must be available in the Rundeck checkout at `/opt/homelab-server-builds/Rundeck/scripts/`.

`invoke-provision-vm.sh` and `invoke-template-rebuild.sh` call the deployed Proxmox scripts on TNAS. `deploy-build-scripts-to-tnas.sh` copies those scripts and `scripts/debian-baseline.sh` from the local checkout to the established TNAS paths. `update-github-checkout.sh` refreshes the checkout used by the jobs.

Keep job `scriptfile` paths, source paths, and TNAS destinations in sync when relocating files.
