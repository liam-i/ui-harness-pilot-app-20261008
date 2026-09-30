---
name: openspec-apply-change
description: Implement tasks from an OpenSpec change. Use when the user wants to start implementing, continue implementation, or work through tasks.
allowed-tools: Bash(openspec:*)
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.12.0"
---

<!-- harness-workflows-v3 codex:apply OpenSpec 1.12.0 e062b9572be933564ba3899d059377dfa1393e32 -->
Implement tasks from an OpenSpec change.

**Store selection:** If the user names a store (a store is a standalone OpenSpec repo registered on this machine) or the work lives in one, run `openspec store list --json` to discover registered store ids, then pass `--store <id>` on the commands that read or write specs and changes (`new change`, `status`, `instructions`, `list`, `show`, `validate`, `archive`, `doctor`, `context`, `schemas`, `view`). Once selected, treat `--store <id>` as sticky for the rest of the workflow. Every unscoped example of those commands below is shorthand: before running it, append the flag. For example, run `openspec status --change "<name>" --json --store "<id>"`, not the unscoped form shown below. Other commands do not take the flag. Hints printed by commands already carry the flag; keep it on follow-ups. Without a store, commands act on the nearest local `openspec/` root.

**Input**: Optionally specify a change name (e.g., `$openspec-apply-change (Codex) or /openspec-apply-change (other agents) add-auth`). If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `openspec list --json` to get available changes and ask the user to select one

   Always announce: "Using change: <name>" and how to override (e.g., `$openspec-apply-change (Codex) or /openspec-apply-change (other agents) <other>`).

2. **Check status to understand the schema**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - `planningHome`, `changeRoot`, and `actionContext`: planning scope and edit constraints
   - Which artifact contains the tasks (typically "tasks" for spec-driven, check status for others)

3. **Get apply instructions**

   ```bash
   openspec instructions apply --change "<name>" --json
   ```

   This returns:
   - `contextFiles`: artifact ID -> array of concrete file paths (varies by schema - could be proposal/specs/design/tasks or spec/tests/implementation/docs)
   - Progress (total, complete, remaining)
   - Task list with status
   - Dynamic instruction based on current state
   - Optional `context`: current required project instruction input from the selected root
   - Optional `operationGuidance`: current advisory guidance for apply

   **Handle states:**
   - If `state: "blocked"` (missing artifacts): stop dependent implementation and report the gap and proposed planning work. You may inspect `openspec status --change "<name>" --json` and `openspec instructions <artifact-id> --change "<name>" --json` for actual schema paths and requirements; these reads do not authorize creating or editing planning files. A general Apply request does not authorize filling the gap. With explicit planning authorization (including authorization already given), follow the actual schema instructions to complete the planning, have it reviewed, then resume authorized Apply. Do not install another workflow just to clear this state.
   - If `state: "all_done"`: congratulate, suggest archive
   - Otherwise: proceed to implementation

   Treat `context` as a required prompt-level input. Read and consider it, and
   apply relevant project facts, conventions, and constraints while implementing.
   Treat `operationGuidance` as optional additive advice. Read and consider every
   entry, and follow entries that are applicable and compatible with the built-in
   workflow.

   Keep both fields separate from CLI-returned state, missing artifacts, tasks,
   progress, `contextFiles`, and the built-in `instruction`. They are not
   evidence of task completion, do not replace the built-in instruction, and do
   not permit bypassing a blocked state. If context conflicts with the built-in
   instruction, an explicit user choice, or a CLI-controlled value, report the
   conflict and preserve the controlling value. If guidance is inapplicable or
   conflicts with those controlling inputs, do not follow it and explain why.
   These are prompt-level behavior contracts, not enforceable checks.

4. **Read context files**

   Read every file path listed under `contextFiles` from the apply instructions output.
   The files depend on the schema being used:
   - **spec-driven**: proposal, specs, design, tasks
   - Other schemas: follow the contextFiles from CLI output

   Do not copy `context` or `operationGuidance` verbatim into implementation
   files or planning artifacts unless the user separately asks for that content.

5. **Show current progress**

   Display:
   - Schema being used
   - Progress: "N/M tasks complete"
   - Remaining tasks overview
   - Dynamic instruction from CLI

6. **Implement tasks (loop until done or blocked)**

   For each pending task:
   - Show which task is being worked on
   - Make the code changes required
   - Keep changes minimal and focused
   - Mark task complete in the tasks file: `- [ ]` → `- [x]`
   - Continue to next task

   **Harness recovery policy**

   Read the applicable project AGENTS.md. Within an actually authorized Apply, continue ordinary diagnosis, correction and targeted verification for the current task without asking again for the same authorization. This policy does not authorize planning-only, read-only, unrelated work, new tools/dependencies, global configuration changes, or another phase.

   - Confirmed assertion failures caused by the approved missing behavior are valid RED: follow the project's TDD method, implement minimally and verify GREEN. If an implementation attempt still fails that valid behavior assertion, continue the same TDD cycle; an attempted GREEN is not a successful GREEN or an execution-recovery round. Compilation errors, zero selected tests, stale runners and faulty test interaction are not RED or passing evidence.
   - For execution/test-method problems, first inspect the relevant facts. Correct only the current task's implementation, tests or approved local tooling, preserving behavior, design, dependencies, required checks and acceptance criteria. Explain test corrections and retain the original failure. Do not weaken assertions, skip checks or relax an approved response-time limit to get GREEN.
   - Use only approved project commands and isolated environments. Do not repeat an identical failed action without new evidence or expand an unproductive investigation indefinitely. Ordinary diagnosis does not implicitly load systematic-debugging or another optional Skill.
   - Stop after two unsuccessful correction-and-targeted-retest rounds for the same unresolved failure. Reads/polls are not rounds; a new error caused by the correction, renaming a task or starting another session does not reset the count. Record the unresolved cause, attempted fixes and count briefly under the current task. Resolving the original check and affected regressions ends recovery; an unrelated successful command does not. Genuine behavior RED/GREEN is not a recovery round; verify that classification rather than relabeling errors.
   - Stop earlier for missing TDD, CLI blocked, conflicting requirements/design, an unusable required acceptance method, unprotected user work/resources, or a need for new scope/authority. Preserve incomplete tasks and do not start another implementation task. State the evidence, attempts and concrete missing decision; do not ask a content-free “continue?” or rerun a proven ineffective action after a generic “continue”.
   - When the approved design or required acceptance method must change, prepare the complete affected-artifact diff for Update's coherent review before asking for approval. A method suggestion or approval of a direction alone is not review of unshown revisions. After approval, write and cross-check the planning set before editing dependent implementation or tests; then resume under existing implementation authorization without another per-file or “continue?” confirmation. Honor any explicit user pause or planning-only boundary.
   - If an authorized operation needs host permission, use the host's approval mechanism directly; do not add duplicate chat approval and do not bypass denial. Honor an explicit user stop. Already authorized logging, stopping this task's processes and restoring its test state may continue as cleanup; report any cleanup failure or additional permission needed. Preserve the original operation's failure separately when cleanup also fails; an overall failure code alone does not describe both failures.

   Project rules and explicit user constraints determine the authorized scope. This adaptation replaces the upstream blanket error-pause policy; it does not override CLI state, schema instructions, required verification or an explicit user decision.

   **Pause if:**
   - Task is unclear → ask for clarification
   - Implementation reveals a design issue → suggest updating artifacts
   - A task needs work beyond what the spec and tasks describe, or you are tempted to drop, narrow, defer, or accept exceptions to specified behavior to make it fit → surface the added scope and ask; do not absorb it silently
   - Recovery reaches its limit or needs a new decision/authority → report the specific gap and wait; ordinary in-scope execution errors follow the Harness recovery policy above
   - User interrupts

7. **On completion or pause, show status**

   Display:
   - Tasks completed this session
   - Overall progress: "N/M tasks complete"
   - If all done: suggest archive
   - If paused: explain why and wait for guidance

**Output During Implementation**

```
## Implementing: <change-name> (schema: <schema-name>)

Working on task 3/7: <task description>
[...implementation happening...]
✓ Task complete

Working on task 4/7: <task description>
[...implementation happening...]
✓ Task complete
```

**Output On Completion**

```
## Implementation Complete

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 7/7 tasks complete ✓

### Completed This Session
- [x] Task 1
- [x] Task 2
...

All tasks complete! You can archive this change with `$openspec-archive-change (Codex) or /openspec-archive-change (other agents)`.
```

**Output On Pause (Issue Encountered)**

```
## Implementation Paused

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 4/7 tasks complete

### Issue Encountered
<description of the issue>

**Options:**
1. <option 1>
2. <option 2>
3. Other approach

What would you like to do?
```

**Guardrails**
- Keep going through tasks until done or blocked
- Always read context files before starting (from the apply instructions output)
- If task is ambiguous, pause and ask before implementing
- If implementation reveals a conflict with the approved design or scope, pause and suggest artifact updates; ordinary implementation errors follow the Harness recovery policy
- Keep code changes minimal and scoped to each task
- Update task checkbox immediately after completing each task
- Follow the Harness recovery policy for execution errors; pause for unresolved blockers or required decisions, and never guess or weaken acceptance
- When a task needs work beyond what the spec describes, surface the added scope and pause - never silently narrow, defer, or simplify away specified behavior
- Only mark a task `- [x]` when its specified behavior is fully implemented, not when it is partially done or deferred
- Use contextFiles from CLI output, don't assume specific file names
- Do not use context or operation guidance as proof that a task is complete
- Apply relevant project context; report conflicts with controlling workflow inputs
- Consider every guidance entry; explain any inapplicable or conflicting advice
- Do not copy runtime context or operation guidance into implementation files or planning artifacts
- Preserve CLI-controlled blocked/ready/all-done behavior and completion criteria

**Fluid Workflow Integration**

This skill supports the "actions on a change" model:

- **Can be invoked anytime**: Before all artifacts are done (if tasks exist), after partial implementation, interleaved with other actions
- **Allows artifact updates**: If implementation reveals design issues, suggest updating artifacts - not phase-locked, work fluidly
<!-- /harness-workflows-v3 -->
