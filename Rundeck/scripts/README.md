# Rundeck Scripts

This directory contains the flat set of shell scripts referenced by Rundeck job definitions. The scripts must be available in the Rundeck checkout at `/opt/homelab-server-builds/Rundeck/scripts/`.

`invoke-provision-vm.sh`, `invoke-template-rebuild.sh`, and `invoke-delete-vm.sh` call the deployed Proxmox scripts on TNAS. `power-ai-host.sh` handles the allowlisted AI-host wake/sleep job and verifies the result. `deploy-build-scripts-to-tnas.sh` copies the Proxmox scripts and `scripts/debian-baseline.sh` from the local checkout to the established TNAS paths. `update-github-checkout.sh` refreshes the checkout, imports and updates the YAML definitions in `Rundeck/jobs/` and `Rundeck/pipelines/`, and deletes Rundeck jobs in the managed `jobs` and `pipelines` groups whose UUIDs are no longer in Git. All job YAML files must specify matching `id` and `uuid` values and use one of those two groups.

API-calling jobs read `RUNDECK_TOKEN` from `/tmp/secrets.txt` on the Rundeck host
using `read-secret.py`. Copy the local `CRAP/secrets.txt` there manually, owned by
`rundeck` with the temporary mode `0777`. The file is parsed as literal data, never sourced as a
shell script; private-key blocks are ignored and no SSH key files are changed.
Missing or unreadable files stop the job before API operations.

The checkout job uses `GITHUB_TOKEN` from the same file when supplied. Otherwise
it retains the existing secure GitHub option at
`keys/project/HomeLab/github_read_token`. The API token must allow importing and
deleting jobs in HomeLab. The previous API-token Key Storage option is no longer
used by the checkout job or Manage VM pipeline. Existing SSH authentication,
including `/var/lib/rundeck/.ssh/target_ed25519`, is unchanged.

Keep job `scriptfile` paths, source paths, and TNAS destinations in sync when relocating files.

Push the local credentials using the laptop's existing script:

```sh
/home/ian/Projects/CRAP/update_secrets.sh
```

That script copies `/home/ian/Projects/CRAP/secrets.txt` to `/tmp/secrets.txt` on
Rundeck and sets ownership to `rundeck:rundeck` and temporary mode `0777`. It is a local
operational file, not part of this Git repository. Existing SSH key blocks in the
secrets file are not extracted or used by these jobs.
