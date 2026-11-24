---
name: codex-delegate
description: Delegate implementation, code review or bug diagnosis to Codex with the model and effort from .harness/config.json, then collect the real result, verify it and integrate it. Use when the harness says Codex goes first (heavy coding, review, root-cause diagnosis), when the routing hook reminds you, or for "Codex한테 맡겨", "코덱스로 리뷰", "ask Codex", "have Codex implement".
argument-hint: "<implement|review|diagnose> <task>"
---

# codex-delegate

Codex does the heavy coding, review and diagnosis. Claude writes the brief, checks the result and integrates it.

## 1. Read the settings

From `.harness/config.json`:
- `models.codex`: `enabled`, `model`, `effort`
- `models.claudeFallback`
- `gates`, `e2e`

Rules:
- If `enabled` is false, or there is no config, do not delegate. Do the work with Claude, following the fallback order, and say why.
- **Pass the model and effort explicitly on every call.** Without them Codex silently uses its global default model.
- Never edit `~/.codex/config.toml`. Other projects share it.

## 2. Pick the sandbox

| Kind of work | Sandbox | Note |
|---|---|---|
| diagnose, review, check a design | read-only | Also write "do not modify any files" in the prompt |
| implement, fix | workspace-write | Only on the current work branch, never on the default branch |

In every prompt, tell Codex not to commit, push, open PRs, deploy or touch hosted databases.

## 3. Write the brief

```
Goal: <one sentence>
Context: <relevant files and why; rules from AGENTS.md and the dev-harness doc that apply>
Scope: <in scope> / Out of scope: <what not to touch>
Done when: <gate commands from the config, e2e if relevant>
Constraints:
- Do not commit, push, open PRs or deploy.
- Never print or write secrets.
- Do not change unrelated files.
- If blocked, stop and report why.
Report:
- changed files, and what changed and why
- commands run and their results
- open questions
```

For a review, ask for findings with `file:line`, severity and a concrete failure scenario. For backend or security reviews, ask Codex to end with a verdict line, `VERDICT: GO` or `VERDICT: NO-GO`.

For security-gate reviews, do not write the brief yourself. Use the `prompt.md` that `security.py prompt` generates (see `/lofo-dev-harness:security-gate`) as the brief, read-only, and save the full answer as `codex.md` in that review folder.

## 4. Run it

**Route A: the Codex plugin for Claude Code.** Use this when the `codex:codex-rescue` agent is available.

```
Agent(subagent_type: "codex:codex-rescue",
      prompt: "--model <model> --effort <effort> <brief>")
```

- Add `--background` for long tasks.
- The rescue agent writes by default. For read-only work, the brief must say "read-only: do not modify files", and you still check `git status` afterwards.

**Route B: the Codex CLI.**

```bash
codex exec -m "<model>" -c model_reasoning_effort="<effort>" \
  -s <read-only|workspace-write> -C "$(git rev-parse --show-toplevel)" \
  -o "<scratch dir>/codex-last.md" "<brief>"
```

- For long tasks, run it in the background and send output to a log file in a scratch directory outside the repository.

**Neither route works, or Codex hits its limit.** Follow `claudeFallback`:
- hard calls go to the first model
- mechanical work to the middle model
- docs to the last model

Tell the user that Codex was skipped and why.

## 5. Get the real result

- Codex's final message is often an empty "done". Read the full output (the log, `--json` events or the transcript) and pull out the actual findings and changes.
- After a write-mode run, check that only the expected files changed and that nothing was committed or pushed:

```bash
git status --short
git diff --stat
git log --oneline <default-branch>..HEAD
```

## 6. Verify and integrate

- Review the diff yourself. Codex output is a draft, not a verdict.
- Run the gates from the config, plus e2e when the change affects behaviour.
- For backend changes, explain to the user in plain language what changed and why. Claude does the explaining even when Codex wrote the code.
- Report three things: what Codex did, what you changed on top of it, and the gate results.
