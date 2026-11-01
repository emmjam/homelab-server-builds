Project: emmjam/homelab-server-builds

TASK

Deploy the first working inference backend on the HP AI node using our
Git-managed Ansible/Rundeck pattern.

The HP and Dell currently have no AI runtime installed. Do not assume that
an inference endpoint, model or deployment account already exists.

ARCHITECTURE

- TNAS hosts Rufus, the application and orchestration layer.
- The HP is the primary interactive inference machine.
- The Dell is intended for later background/worker capacity.
- Rundeck is the trusted infrastructure execution authority.
- Ansible manages installation and configuration.
- Rufus will consume the inference API; it must not receive infrastructure
  SSH credentials or administer the HP directly.

Scope this task to the HP. Do not install the Dell worker, implement scheduling,
or install an inference runtime inside the Rufus container.

INSPECT FIRST

Inspect:
1. Repository conventions, documentation, BACKLOG.md and relevant Git history.
2. Existing Rundeck jobs, Ansible inventory and deployment patterns.
3. The HP’s actual identity, OS, CPU, RAM, GPU/VRAM, available storage and network.
4. Existing SSH connectivity and administrative deployment access.
5. Whether any runtime or model is already present.
6. Rufus’s existing application and configuration.

Do not confuse intended architecture with verified current configuration.
Preserve unrelated uncommitted changes.

If deployment access or a required OS prerequisite is missing, report exactly
what is required. Do not invent credentials or weaken authentication.

RUNTIME AND MODEL DECISION

Based on the verified hardware:
- Propose one suitable inference runtime.
- Propose one initial model suitable for interactive conversation, structured
  action proposals and explaining diagnostic evidence.
- Explain model download size, expected RAM/VRAM use, storage needs and likely
  performance limitations.
- Establish whether CPU or GPU inference is practical.
- Obtain my approval for the runtime/model before installation or large downloads.
- Ask before installing GPU drivers or making changes requiring a reboot.

Avoid unnecessary components. A single working runtime and model are sufficient.

IMPLEMENT THROUGH ANSIBLE

Store the playbook/role, non-secret configuration, service definitions and
required Rundeck job definition in the existing repository structure.

Follow:
Git → existing Rundeck checkout/deployment flow → Ansible → HP.

Do not create a parallel manual installation process or unnecessary wrapper
scripts. Do not change working VM/LXC provisioning as part of this task.

Ansible should manage:
- Required packages and approved runtime installation.
- Appropriate service account.
- Runtime configuration.
- Model storage directories and ownership.
- Download of the approved model.
- Service startup and automatic startup after reboot.
- Sensible restart behaviour.
- Useful service logs.
- Required network/access restrictions.
- Health checks.

A repeat run must not reinstall the runtime or redownload an unchanged model.
Record the runtime version and exact model identifier used.

ACCESS AND SECRETS

The inference API must be reachable from Rufus over the approved LAN path.

Define and explain the smallest appropriate access arrangement:
- Intended bind address and port.
- Which clients may connect.
- Authentication and/or network restrictions supported by the chosen runtime.
- Any remaining limitations.

Do not expose an unauthenticated endpoint broadly.
Ask before introducing a proxy or another service if one is genuinely necessary.

Use the established ignored secret/configuration mechanism where credentials
are required. Do not implement OpenBao.
Never commit or log tokens, passwords or private keys.
Do not copy deployment SSH credentials into Rufus.

RUFUS INTEGRATION

Provide configurable values for:
- Inference API URL.
- Model identifier.
- Authentication source, if required.
- Connection and inference timeouts.

Do not add conversational execution or repair behaviour yet.
A real inference request originating from the Rufus container is sufficient
for this task.

VALIDATION

Verify:
1. HP service is running and enabled at boot.
2. The approved model is present.
3. A local inference request succeeds.
4. A request from the Rufus container succeeds.
5. A structured-response request works, or document the runtime’s limitations.
6. Access restrictions behave as configured.
7. Ansible’s second run is idempotent.
8. Rufus receives a bounded, clear error when inference is unavailable.
9. Startup persistence after a controlled reboot, if approved and safe.

Do not disrupt unrelated workloads to manufacture a failure.

DELIVERY

- Run relevant automated checks.
- Commit logical changes separately and push to the existing branch.
- Update documentation and BACKLOG.md using verified results only.
- Document start/stop/status/log commands and how to rerun deployment.
- Report hardware findings, runtime/version, model, endpoint, access controls,
  Ansible/Rundeck entry points, tests, execution links, commit hashes and blockers.

STOP once Rufus can successfully call the HP inference backend.

Do not begin the conversational repair workflow, Dell deployment, VS Code
extension, OpenBao, WOL, Sonos, Bobarr or other backlog work.