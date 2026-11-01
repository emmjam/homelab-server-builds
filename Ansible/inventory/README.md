# Ansible Inventory

Keep non-secret inventory sources or inventory documentation here. Do not commit credentials or private keys. No inventory is currently defined.

## Rufus provisioning

`Ansible/playbooks/rufus.yml` prepares a Debian 13 host in the `rufus` inventory
group. It creates Ian's administrative account, key-only SSH access, the Rufus
service account and directories, and the Python environment. It does not deploy
an application or start a Rufus service.

Supply `ian_ssh_public_key` and `ian_password_hash` from an untracked secret source;
the latter must be an encrypted Unix password hash for password-required sudo.
Keep existing Rundeck SSH authentication in place. Run Ansible on Rundeck, not TNAS.

Local Ollama installation defaults to disabled, matching the separate inference
workers. Explicitly set `install_ollama: true` only for a local inference host;
`install_ollama_model: false` skips the optional model download.
