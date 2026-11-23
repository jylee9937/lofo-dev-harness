---
name: wireflow
description: Plan and review screens before building them. Turns requirements, existing screens or design-tool frames into a wireflow at design/flows/<id>.flow.json. The wireflow holds screens, arrows, scenarios, planning rationale, UX conditions, open decisions, UX issues and change requests. The skill checks it for broken links, dead ends and missing recovery paths, runs a UX review, renders an HTML review board, and mirrors the same screens and review marks into Figma, Pencil or any other design tool. Use at the screen-design stage, for "와이어프레임", "와이어플로우", "화면 흐름", "UX 검토", "수정 요청 반영", "wireflow", "UX review", or when the user pastes a "[wireflow 수정 요청]" / "[wireflow change requests]" block.
argument-hint: "[flow id | requirements doc | pasted change requests]"
---

# wireflow

The flow JSON is the source of truth for screens and their review marks. The HTML board and the design tool both show the same content.

Talk to the user in the project language (`language` in `.harness/config.json`). Write all flow text in that language too.

## Files

| What | Where |
|---|---|
| Flow (commit it) | `<docs.flows>/<id>.flow.json`. `docs.flows` defaults to `design/flows`. |
| Board (generated, gitignored) | `<docs.flows>/<id>.wireflow.html` |
| Design images (optional) | `<docs.flows>/images/<id>/<screen id>.png`, exported from any design tool |
| Schema and example | `${CLAUDE_PLUGIN_ROOT}/schemas/flow.schema.json`, `${CLAUDE_PLUGIN_ROOT}/examples/flows/study-group.flow.json` |

## 1. Gather the source

- Read the requirements: docs, an issue, or the user's message.
- If screens already exist, in code or in the design tool, read those too. When an existing implementation misses a required step, model the current, broken flow first. Then propose the fix as an issue.
- Keep track of what the source requires and what you are inferring.

## 2. Write the flow

- **Scope**: one flow per user goal. Stages are the steps of that task.
- **Variants**: give each main screen the variants it needs. These are empty, loading, error and success states. Separate input validation errors from failures like a network error. Put each variant in the same stage, next to its main screen.
- **Actions**: every screen lists every way out, including back, close, tabs and `system` transitions (server response, timeout). For a destination that is not designed yet, use `to: null`. Never invent one silently.
- **Provenance**:
  - `origin: "source"` only when the requirements ask for the screen. Otherwise use `"inferred"`.
  - `rationale` quotes or summarizes the source (기획 근거).
  - `conditions` lists the UX conditions and branches.
- **Decisions**: an unresolved policy question becomes a `decisions` entry with options and `status: "open"`. Do not guess.
- **Scenarios**:
  - at least one main journey
  - recovery journeys: failure then retry, invalid input then fix, back then return with input kept
  - edge cases such as empty results
- **Wireframe blocks**: low fidelity, but use real UI copy. Set `action` on the block that triggers an action, so arrows start there.
- **IDs**: keep them stable once created. Change requests refer to them.

## 3. Check

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow.py" check <flow>
```

Exit codes are 0 (pass), 1 (S1/S2 problems) and 2 (invalid file). For each S1/S2 finding, either fix the flow, or, when it is a real gap in the requirements, keep the gap visible (`to: null`) and add a decision. Re-run until only intended items remain.

## 4. UX review

1. Review every screen and scenario against [references/ux-checklist.md](references/ux-checklist.md).
2. Record each finding in `issues` with:
   - `severity`:
     - **S1** blocks the task or loses data
     - **S2** major friction or missing recovery
     - **S3** confusing or inconsistent
     - **S4** polish
   - `category`
   - a concrete `suggestion`
   - `origin: "ai-review"`
   - `status: "open"`
3. **Get an independent second look** from a reviewer that did not write the flow. Give it only the requirements and the flow file. Use either:
   - a Claude subagent
   - Codex read-only through `/lofo-dev-harness:codex-delegate` when Codex is enabled. Its issues use `origin: "codex"`.
   Merge duplicates.
4. Never fix issues silently. Either change the flow and mark the issue `fixed`, or leave it `open` for the user.

## 5. Build and show the board

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow.py" build <flow> [--embed-images]
```

- Open the board for the user (`open` on macOS, `xdg-open` on Linux), or give the path. Use `--embed-images` when the board will be sent to someone as a single file.
- Tell the user how to review on the board:
  - pick a scenario to highlight its path
  - click a screen to see rationale, conditions, checks, decisions and issues
  - write change requests per screen
  - press "수정 요청 복사" / "Copy change requests" and paste the result into the chat

## 6. Mirror to the design tool

Use `integrations.design` from `.harness/config.json`, or ask the user once. Follow [references/design-tools.md](references/design-tools.md). The design tool shows the same screens, numbers, arrows and review marks; the flow JSON stays the source of truth.

Writing to a cloud design file, such as Figma, is an external write. Confirm with the user before the first write to a file.

## 7. Apply pasted change requests

When the user pastes a `[wireflow 수정 요청]` or `[wireflow change requests]` block:

1. Check that the `flow:` path and flow ID match the file you are editing.
2. Add each request to `requests` with its screen and action IDs and `status: "open"`.
3. Apply the change to the flow, and to the design tool if it is mirrored. Keep IDs stable and leave unrelated screens alone. If a request conflicts with the requirements or a decision, ask the user before applying it.
4. Mark each request `done` with a one-line `resolution`, or `rejected` with the reason.
5. Run check and build again. Report what changed by screen number. Tell the user they can clear the requests the board stored locally: right-click the copy button.

## 8. Stage gate

The screen-design stage passes when all of these hold:
- `flow.py check` exits 0, so no S1/S2 findings and no open S1/S2 issues remain
- every decision is `decided`, or `deferred` by the user
- the user has reviewed the board (and the design-tool frames, if any) with no open change requests

Link the approved flow from the technical design doc. It is the screen spec that development follows.

## Report

- flow file and board path
- screen and scenario counts
- structural findings, open issues by severity, open decisions
- what the user should look at first
