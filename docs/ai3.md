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

Status: implementation awaiting final scripted acceptance.
