# Rufus – Implement General Conversational Processing

## Objective

Make Rufus usable as an ordinary conversational assistant using the existing local Qwen3 4B inference service on the HP EliteDesk.

The read-only audit has established that:

- Rufus is operational on TNAS.
- Ollama is operational on the HP EliteDesk.
- Local inference connectivity is working.
- Qwen3 4B is installed and available.
- SQLite conversation storage is working.
- The supervised Rundeck repair workflow has been successfully tested.
- The missing functionality is general-purpose conversational processing.

## Requirements

### 1. General conversation

- Implement ordinary conversational responses through the existing message API.
- Use the existing inference client and configured Qwen3 4B model.
- Do not invoke Rundeck for ordinary conversation.
- Support questions, explanations, follow-up questions and general discussion.

### 2. Conversational history

- Include both user and assistant messages in subsequent inference requests.
- Maintain conversation separation.
- Implement sensible context limits so history cannot grow indefinitely.
- Preserve existing SQLite persistence.
- Ensure assistant responses are saved before returning successful completion.

### 3. Preserve operational capabilities

- Retain the existing infrastructure workflow classifier.
- Infrastructure requests must continue through the existing deterministic validation and approval mechanisms.
- Never allow ordinary conversational model output to trigger infrastructure operations directly.
- Do not weaken permission checks or Rundeck restrictions.
- Do not change the successful AI2 repair implementation unnecessarily.

### 4. Error handling

- Return understandable errors when Ollama is unavailable.
- Handle generation timeouts.
- Handle missing models.
- Preserve conversation history when inference fails.
- Ensure failed conversational requests cannot accidentally enter the operational execution path.

### 5. Testing

Implement automated tests covering:

1. Ordinary conversational question and response.
2. Multi-turn conversation with assistant history supplied to inference.
3. Separate conversations maintaining separate histories.
4. Ordinary conversation generating zero Rundeck executions.
5. Infrastructure requests still following the existing approval workflow.
6. Rejected infrastructure operations remaining rejected.
7. Conversation history surviving a Rufus service restart.
8. Ollama unavailable or generation timeout.
9. Failed requests not being recorded as successful responses.

Use mocks where appropriate. Do not perform unnecessary infrastructure operations.

## Constraints

- Preserve the existing architecture.
- No Docker.
- No hosted AI dependency.
- Use the existing HP Ollama installation.
- Keep configuration under Ansible management.
- Maintain least-privilege security.
- Make changes idempotently and keep them in the Git repository.
- Do not modify unrelated components.
- Do not rebuild the HP or TNAS.
- Do not remove or weaken any existing AI2 functionality.

## Acceptance criteria

Rufus must demonstrate:

- A normal multi-turn conversation using local Qwen3 4B.
- Correct use of previous user and assistant messages.
- Zero Rundeck executions during ordinary conversation.
- Existing supervised repair functionality remains intact.
- Conversation history survives a service restart.

Run the relevant automated tests and report their results.

Do not proceed to remote chat clients, worker allocation, or additional features.

At completion, provide a concise implementation report identifying files changed, tests performed, results and any outstanding limitations.
