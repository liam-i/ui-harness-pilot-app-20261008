---
name: openspec-verify-change
description: "Use only when the user explicitly selects Verify to check a specified Change against applicable artifacts, implementation and evidence. Ordinary tests or review do not invoke it; it grants no archive authority."
allowed-tools: Bash(openspec:*)
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.12.0"
---

<!-- harness-workflows-v3 codex:verify OpenSpec 1.12.0 e062b9572be933564ba3899d059377dfa1393e32 -->
**Harness explicit verification scope**

Use this method only after the user explicitly selects Verify and the host makes this entry available. A project-required method remains required, but user-only host invocation must be satisfied; never read a disabled entry to simulate invocation. Ordinary review does not replace an already selected Verify. Read the applicable project AGENTS.md and verify the specified active Change using its actual schema and paths. Do not create an empty Change for Tiny, restore an archive just to inspect it, or silently switch an unsupported target or required method.

The default output is a report, not edits to code, tests, artifacts, task checkboxes, main specs or archives. You may run existing necessary checks within authorized scope; state their environment and generated test/build output. Reading instructions apply obtains context only: it does not enter Apply, load TDD, execute Tasks or authorize planning writes. No automatic Debugging, Verification, fixes, Archive, Merge or publication follows from this method.

Report the scope, artifact/code versions or diff, environment and reviewer. Map each applicable Requirement and Scenario through implementation, test or demonstration step, actual evidence and its current validity, then gaps or justified non-applicability. Include main-spec plus delta semantics, applicable Design and Tasks. Existing test code is not an executed result; old evidence is not a fresh run. Reuse evidence only while the relevant spec, code, inputs, dependencies and environment remain valid; otherwise rerun affected checks or report uncertainty. Explicitly selected Superpowers Verification still requires its fresh complete required checks, including requirement coverage. One Agent using two methods is not an independent reviewer.

Partial in-progress audits are allowed when explicitly scoped; retain incomplete Tasks and report the overall Change as in progress. Do not create a self-blocking Task that must already be checked before this report. Required gaps return to existing Tasks and authorized Apply; substantial planning or required-method changes first need Update's complete preview, review and planning cross-check. Respect the existing recovery limit; switching methods does not reset it.

Verify that an implementation matches the change artifacts (specs, tasks, design).

**Store selection:** If the user names a store (a store is a standalone OpenSpec repo registered on this machine) or the work lives in one, run `openspec store list --json` to discover registered store ids, then pass `--store <id>` on the commands that read or write specs and changes (`new change`, `status`, `instructions`, `list`, `show`, `validate`, `archive`, `doctor`, `context`, `schemas`, `view`). Once selected, treat `--store <id>` as sticky for the rest of the workflow. Every unscoped example of those commands below is shorthand: before running it, append the flag. For example, run `openspec status --change "<name>" --json --store "<id>"`, not the unscoped form shown below. Other commands do not take the flag. Hints printed by commands already carry the flag; keep it on follow-ups. Without a store, commands act on the nearest local `openspec/` root.

**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.

**Steps**

1. **Select the change**

   If a name is provided, use it. Otherwise:
   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `openspec list --json` to get available changes and ask the user to select one

   When prompting, show changes that have implementation tasks (tasks artifact exists).
   Include the schema used for each change if available.
   Mark changes with incomplete tasks as "(In Progress)".

   Always announce: "Using change: <name>" and how to override (e.g., `$openspec-verify-change (Codex) or /openspec-verify-change (other agents) <other>`).

2. **Check status to understand the schema**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to understand:
   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - `planningHome`, `changeRoot`, `artifactPaths`, and `actionContext`: path and scope context
   - Which artifacts exist for this change

3. **Get planning context and load artifacts**

   ```bash
   openspec instructions apply --change "<name>" --json
   ```

   This returns the change directory and `contextFiles` (artifact ID -> array of concrete file paths). Read all available artifacts from `contextFiles`.

4. **Initialize verification report structure**

   Create a report structure with three dimensions:
   - **Completeness**: Track tasks and spec coverage
   - **Correctness**: Track requirement implementation and scenario coverage
   - **Coherence**: Track design adherence and pattern consistency

   Each dimension can have CRITICAL, WARNING, or SUGGESTION issues.

5. **Verify Completeness**

   **Task Completion**:
   - If `contextFiles.tasks` exists, read every file path in it
   - Parse checkboxes: `- [ ]` (incomplete) vs `- [x]` (complete)
   - Count complete vs total tasks
   - If incomplete tasks exist:
     - Add CRITICAL issue for each incomplete task
     - Report the incomplete task and evidence gap; do not mark it done in Verify. Return any justified status correction to the authorized task workflow.

   **Spec Coverage**:
   - If delta specs exist in `contextFiles.specs`:
     - Extract all requirements (marked with "### Requirement:")
     - For each requirement:
       - Search codebase for keywords related to the requirement
       - Assess if implementation likely exists
     - If requirements appear unimplemented:
       - Add CRITICAL issue: "Requirement not found: <requirement name>"
       - Recommendation: "Implement requirement X: <description>"

6. **Verify Correctness**

   **Requirement Implementation Mapping**:
   - For each applicable requirement from main specs and delta semantics:
     - Search codebase for implementation evidence
     - If found, note file paths and line ranges
     - Assess if implementation matches requirement intent
     - If divergence detected:
       - Add WARNING: "Implementation may diverge from spec: <details>"
       - Recommendation: "Review <file>:<lines> against requirement X"

   **Scenario Coverage**:
   - For each applicable scenario from main specs and delta semantics (marked with "#### Scenario:"):
     - Check if conditions are handled in code
     - Check if tests exist covering the scenario
     - If scenario appears uncovered:
       - Add WARNING: "Scenario not covered: <scenario name>"
       - Recommendation: "Add test or implementation for scenario: <description>"

7. **Verify Coherence**

   **Design Adherence**:
   - If `contextFiles.design` exists:
     - Extract key decisions (look for sections like "Decision:", "Approach:", "Architecture:")
     - Verify implementation follows those decisions
     - If contradiction detected:
       - Add WARNING: "Design decision not followed: <decision>"
       - Recommendation: "Update implementation or revise design.md to match reality"
   - If Design is absent, check actual schema and approved scope: report a required missing artifact as a gap, or explain legitimate non-applicability.

   **Code Pattern Consistency**:
   - Review new code for consistency with project patterns
   - Check file naming, directory structure, coding style
   - If significant deviations found:
     - Add SUGGESTION: "Code pattern deviation: <details>"
     - Recommendation: "Consider following project pattern: <example>"

8. **Generate Verification Report**

   **Summary Scorecard**:
   ```markdown
   ## Verification Report: <change-name>

   ### Summary
   | Dimension    | Status           |
   |--------------|------------------|
   | Completeness | X/Y tasks, N reqs|
   | Correctness  | M/N reqs covered |
   | Coherence    | Followed/Issues  |
   ```

   **Issues by Priority**:

   1. **CRITICAL** (Must fix before archive):
      - Incomplete tasks
      - Missing requirement implementations
      - Each with specific, actionable recommendation

   2. **WARNING** (Should fix):
      - Spec/design divergences
      - Missing scenario coverage
      - Each with specific recommendation

   3. **SUGGESTION** (Nice to fix):
      - Pattern inconsistencies
      - Minor improvements
      - Each with specific recommendation

   **Final Assessment**:
   - Classify the required scope as satisfied, required gaps found, unable to judge, or partial audit. These are report conclusions, not new workflow state files.
   - Severity alone never determines acceptance. A WARNING about a required Scenario, Design constraint or missing evidence prevents a satisfied conclusion; uncertainty remains explicit.
   - State remaining task, independent review, final-candidate CI and phase/authorization conditions. A satisfied report does not authorize Archive or delivery.

**Verification Heuristics**

- **Completeness**: Focus on objective checklist items (checkboxes, requirements list)
- **Correctness**: Search locates candidates; substantiate required behavior with implementation and actual valid evidence. Mark inference or uncertainty explicitly.
- **Coherence**: Look for glaring inconsistencies, don't nitpick style
- **Uncertainty**: Explain confidence and missing evidence; lowering issue severity does not discharge a required check.
- **Actionability**: Every issue must have a specific recommendation with file/line references where applicable

**Graceful Degradation**

- Determine required artifacts from the actual schema and approved scope before skipping anything. Required missing specs, Design or evidence are gaps.
- For a legitimate no-delta change, check applicable main specs and approved technical goals; do not fabricate a delta or infer no verification duty.
- Verify all applicable dimensions and explain each legitimate non-applicability; absent files alone do not justify skipping.

**Output Format**

Use clear markdown with:
- Table for summary scorecard
- Grouped lists for issues (CRITICAL/WARNING/SUGGESTION)
- Code references in format: `file.ts:123`
- Specific, actionable recommendations
- No vague suggestions like "consider reviewing"
<!-- /harness-workflows-v3 -->
