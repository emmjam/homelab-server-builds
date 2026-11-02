# AI3 general conversation

Uses the existing authenticated loopback `/conversations/ID/messages` endpoint.
The structured classifier now distinguishes `chat` from operational requests.
Conceptual questions belong to chat; requests to inspect/change infrastructure
continue through the unchanged AI2 validation and exact-action approval path.
Chat generation receives no operation tools and its text is never parsed for
execution. Classifier or chat failure has no operational fallback.

Assistant messages appear in history with `role: assistant`, `reply_to` identifying
the user message, and `status: completed`. Existing user messages now explicitly
include `role: user`. An additive SQLite `assistant_replies` table preserves the
existing conversation/action schema. Reply insertion and user-message completion
commit atomically. Failed requests retain their prompt and error event, without
an assistant success message. Duplicate request IDs do not regenerate replies.

Inference context contains at most six completed exchanges plus the current
prompt, bounded to 6,000 characters excluding the fixed system prompt. Oldest
exchanges are omitted whole; failed/interrupted requests are excluded. The durable
archive is retained; this is an inference context limit, not history deletion.
The existing 4,096-token inference context and 256-token structured output limit remain; chat defaults to 512 output
tokens (`chat_num_predict` in inference settings), with inline Qwen reasoning
removed and incomplete/limit-exhausted chat rejected;
character budgeting is approximate, not a tokenizer. Responses are bounded and
redacted to 2,048 characters before persistence. No tools or hosted dependency
are added. Endpoint/model/timeouts remain in Ansible-managed inference.json.

Backend unavailability and timeouts produce safe persisted error events. HTTP 404
identifies the configured model or endpoint as unavailable without disclosing
upstream bodies. Interrupted generation is not automatically retried after restart.

Deployment/acceptance: the Git-managed **HomeLab - Deploy and Validate Rufus AI3**
job refreshes Git, runs the automated suite, deploys only Rufus application tasks,
and runs `Ansible/playbooks/ai3-acceptance.yml` through `scripts/ai3-final.py`.
This single final script verifies multi-turn local inference, restarts Rufus,
verifies history and another follow-up, and compares controller execution IDs
before/after chat. The API-side execution count and action/events are also checked.
No AI2 repair or disposable fixture is needed. No new Rufus ACL permissions.

## Acceptance — 2 November 2026

**AI3 complete.** Deployment and acceptance
[196](http://192.168.0.51:4440/project/HomeLab/execution/show/196) succeeded
with source `b217029`. HP was awakened through Rundeck execution 192.
All six automated validation groups passed, including 14 new chat/inference
regression tests and the existing AI2 approval/rejection/recovery tests.
Validation logs: `/tmp/homelab-validation-c7zb4u0r`; complete deployment/acceptance
log: `/tmp/ai3-final-bt2et6lj.log` on Rundeck.

Real configured HP Qwen3 4B conversation:

1. User: “Reply with exactly these two words: Amber Willow” → “Amber Willow”.
2. User: “What was the second word in your previous reply? Reply with that word
   only.” → “Willow”.
3. After a managed Rufus restart, saved history matched its pre-restart digest.
   User: “Which word did you give in your last answer? Reply with that word
   only.” → “Willow”.

Controller execution IDs were unchanged across chat/restart acceptance; Rufus's
own execution count was unchanged and no actions or operational execution events
were generated. Existing infrastructure approval functionality was exercised by
mocks, without another live repair. The earlier acceptance failure exposed inline
Qwen reasoning; the inference client now excludes it from final replies. The
acceptance runner uses the existing runuser pattern rather than adding ACL tools.

Remaining limitations: loopback-only API, polling rather than streaming, approximate
character-based context budgeting, bounded replies, and no automatic retry of
interrupted generation. Durable history is retained rather than pruned. No remote
client, worker allocation, new operation permissions or hosted dependency was added.
