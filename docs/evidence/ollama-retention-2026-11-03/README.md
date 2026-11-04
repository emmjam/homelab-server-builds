# HP Ollama retention — verified 3 November 2026

Managed default changed from 0 to 30m using role default `ollama_keep_alive` and
the existing service template/handler. A service-configuration tag permits narrow
application without model, resource, firewall, runtime or Rufus changes. Deployed
from a manifest-verified working-source snapshot on Rundeck; no commit or push.

Checks: Ansible syntax, rendered unit differing only in KEEP_ALIVE, systemd unit
verification, check-mode diff, tagged apply and convergence check. The first
preview stopped safely because the Ansible API needed trust_as_template; corrected
before deployment, with no initial live changes. See both result logs.

The apply changed the template and restarted Ollama to update its environment.
Actual process environment is 30m; unit, resource properties and model manifest
were compared before/after. A real inference from unprivileged Rufus reached the
HP, completed, and the model was still resident after five seconds and on a later
read. `same-host-expiry.json` verifies expiry is 1800.000116 seconds after the HP's
request-completion journal timestamp. The initial acceptance.json duration mixes
HP/Rufus clocks and is superseded by this same-host calculation (40-second offset).
Natural unloading after 30 minutes was not observed; the task explicitly permits
reporting this unverified without an unnecessary wait.

IMPORTANT: unchanged Rufus/inference.py sends keep_alive=0 on each request, and
Ansible/playbooks/ai-inference-validate.yml does so too. These explicit API values
override the server default. Thus ordinary Rufus requests still request immediate
unloading: the latency benefit for Rufus is NOT established by this server-only
change. The retention test omitted keep_alive. No Rufus code or inference options
were changed. Official precedence: https://docs.ollama.com/faq .

Files: deployment.log (Ansible checks/apply/convergence), before/after.json (service
and model facts), acceptance.json (Rufus-origin inference/residency),
same-host-expiry.json (corrected expiry), SOURCE.json (staged Ansible manifest),
retention.py (controller validation script), preflight.log and result logs.
Timing uses the local Europe/London wall clock and a monotonic elapsed timer;
active working time was not separately instrumented. See timing.json. The initial
interrupted read-only inspection is excluded because its start was not measured.
The separate deferred VS Code continuation remains intact.
