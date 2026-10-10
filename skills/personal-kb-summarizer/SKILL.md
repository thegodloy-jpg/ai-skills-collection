---
name: personal-kb-summarizer
description: Convert a Codex or ChatGPT conversation event stream into a compact, structured, provenance-preserving SummaryResult JSON object for a local personal knowledge base. Use when summarizing, incrementally updating, classifying, indexing, or archiving a conversation, and when a downstream program needs deterministic fields for decisions, actions, questions, claims, topics, value, lifecycle state, and source-turn traceability.
---

# Personal KB Summarizer

Produce one machine-readable `SummaryResult` object from the supplied conversation. Treat the transcript as a record of what participants said, not as proof that every statement is true.

## Read the Contract

Read `references/summary-result-schema.json` before producing output. Return an object that validates against that schema.

## Accept Input

Accept either:

- raw JSONL conversation events; or
- an explicitly supplied list of turns with stable turn or event identifiers.

Use a supplied prior `SummaryResult` as incremental state. Reuse its item IDs for unchanged decisions, actions, questions, and claims. Never infer missing transcript content from the prior summary alone.

Expect raw events to contain some or all of these fields: `event_id`, `thread_id`, `turn_id`, `role`, `content`, `timestamp`, and `event_type`. Ignore tool protocol noise unless it materially changes the user's result.

When `event_type` is present, interpret `UserPromptSubmit` as user input, `AssistantCommentary` as user-visible work progress, `Stop` as the authoritative final assistant answer for that turn, and `SessionEnd` as a lifecycle marker. Older v1 events may omit `event_type`; treat an assistant event without it as a final answer for compatibility. Preserve durable verification results, commands, paths, file changes, test outcomes, and failure boundaries from commentary when the later final answer does not repeat them. Do not promote an interim plan or status update into the final conclusion, and never let commentary override a later `Stop` event. If a turn has no `Stop`, mark its question unresolved and never borrow a final answer from a later turn.

## Build the Result

1. Identify the thread and the final included event.
2. Write a specific title that exposes the actual conversation subject. Avoid generic titles such as “日常对话” or “问题讨论”.
3. Choose one stable `primary_topic` and at most three concise `topics`.
4. Classify value:
   - `ephemeral`: short-lived lookup or low-reuse chat.
   - `reference`: information likely to be looked up again.
   - `knowledge`: reusable explanation, method, model, or synthesized insight.
   - `project`: work tied to an ongoing deliverable, decision, or execution state.
5. Recommend `archive_policy`:
   - use `summary_only` for ordinary `ephemeral` material;
   - use `full` for source-sensitive, reusable, or project material;
   - use `local_only` when the transcript visibly contains sensitive material that should not sync;
   - use `skip` only for obvious system tests, summarizer jobs, or empty/noise-only sessions.
6. Set lifecycle `state` to `active`, `dormant`, or `archived` from explicit context. Default to `active` when the conversation has current open work.
7. Summarize the durable substance, not the conversational choreography. When the assistant answered the user's request, preserve the concrete answer or conclusion and the essential reasoning, commands, paths, constraints, or steps needed to reuse it; never reduce the summary to a restatement of the user's question.
8. Extract structured items in source order and attach `source_turns`.
9. Set `derived_from.last_event_id` and `derived_from.event_count` from the supplied input.
10. Validate the complete object against the schema before returning it.

Treat `archive_policy` as a recommendation. Never delete, move, or rewrite raw conversations.

## Preserve Evidence and Ownership

- Put an item in `decisions` only when the user explicitly confirms or adopts it. Do not promote an assistant recommendation into a user decision.
- Put concrete unfinished or completed work in `actions`; record the owner only when it is explicit.
- Put unresolved information needs in `questions`.
- Put durable factual assertions, recommendations, constraints, or assistant proposals in `claims`.
- Use `user_confirmed` only for statements the user explicitly adopts.
- Use `assistant_proposed` for assistant analysis or recommendations that the user has not confirmed.
- Use `externally_verified` only when the transcript itself contains a cited or tool-produced verification.
- Use `unverified` when provenance is unclear or the statement remains an assertion.
- Preserve disagreement and supersession. Mark an older item `superseded` and point `superseded_by` to the newer item instead of silently replacing it.
- Mark an assistant claim `rejected` when the user explicitly rejects it. Its `superseded_by` may point to the user decision that replaced it.
- Never invent dates, owners, evidence, source turns, completion status, or decisions.

## Keep IDs Stable

Use `D-001`, `A-001`, `Q-001`, and `C-001` style identifiers. When prior state is provided, keep the identifier for the same semantic item even if wording is tightened. Assign the next unused number only to a genuinely new item.

## Protect Sensitive Data

Do not copy access tokens, passwords, private keys, session cookies, or full credential-like strings into the summary. Replace them with `[REDACTED]` while preserving the fact that sensitive material was discussed. Recommend `local_only` when appropriate.

## Emit Strict Output

Return only the JSON object, with no Markdown fence, preface, commentary, or trailing explanation. Use empty arrays for absent collections. Keep the summary compact while retaining decisions, constraints, open work, and provenance needed for later retrieval.

Before emitting, verify that every `source_turns` value exists in the supplied transcript. This referential check is required even though JSON Schema cannot enforce it by itself.
