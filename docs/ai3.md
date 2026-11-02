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
The existing 4,096-token inference context and 256-token structured output limit remain; managed chat allows 2,048 output
tokens (`chat_num_predict` in inference settings), with inline Qwen reasoning
removed and incomplete/limit-exhausted chat rejected;
character budgeting is approximate, not a tokenizer. Responses are redacted and saved whole up to 8,192 characters; larger replies fail
rather than being silently truncated. Operational text limits remain unchanged. No tools or hosted dependency
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

## Task 1 inference compatibility correction

The general chat wire request can use an Ansible-managed empty-thinking prefill
for the retained Qwen template (`chat_empty_thinking_prefill`). This prevents the
observed missing-final-answer failure without increasing the 512-token chat budget
or changing structured AI2 requests, stored dialogue or approval handling. Real
chat and restart acceptance passed again in execution 203. See
[Rufus Web's completion record](rufus-web.md#automated-completion-record--2-november-2026)
for the reproduction and full Task 1 evidence.

## Thinking-only model response-budget correction

The installed `qwen3:4b` reports Qwen3-4B-Thinking-2507 metadata and only supports
`thinking.values: [true]`. `think:false`, `/no_think` and the existing empty
thinking prefill do not reliably eliminate reasoning. The wire request used
`num_ctx=4096`, `num_predict=512`, `temperature=0`, `stream=false`, `keep_alive=0`.
Connection timeout was 5 seconds; generation timeout was 120 seconds.

Replaying the failed name question with its saved 583-character context produced
`done_reason=length`, `eval_count=512`, with no closing reasoning tag or final
answer. A diagnostic replay with a 2,048-token ceiling stopped naturally at
1,107 tokens: 161.2 seconds generation, 169.5 seconds overall, and a 14-character
final response. Another ordinary name follow-up consumed 460 tokens for “Ian”.
Thus both reasoning and answers need budget; a shorter question is not the fix.

Ansible now supplies a bounded 2,048-token chat allowance and a separate
360-second chat timeout. At the measured approximately 6.9 tokens/second, the
ceiling requires about 300 seconds plus loading/prompt overhead. Structured AI2
requests retain 256 tokens and 120 seconds; model, endpoint, template, context,
approvals and history selection are unchanged. `done_reason=length` remains a
failure, and reasoning is excluded from replies. Longer complete answers are no
longer silently shortened at the old 2,048-character persistence cut-off.

The [publisher model card](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507)
confirms this variant is thinking-only; [Ollama's documentation](https://docs.ollama.com/capabilities/thinking)
notes that `think:false` is conditional on model support.
