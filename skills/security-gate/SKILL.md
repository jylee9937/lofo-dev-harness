---
name: security-gate
description: Security gate for risky changes and for pre-launch checks. It decides whether a change touches authentication, authorization (RLS, roles), money, secrets, personal data, file uploads, webhooks or permission and schema migrations. It runs automated checks (secrets, SQL and filter injection, upload limits, login attempt limits, authorization, weak hashing, RLS, dependency audit) and walks the security checklist. Then it gets an independent read-only review, Codex first, that ends in GO or NO-GO, records everything, and blocks merge and deploy until GO. Use before merging or deploying such changes, when the routing hook flags a security path, before launch, or for "보안 점검", "보안 검토", "출시 전 보안", "security review", "security gate".
argument-hint: "[--launch] [slug]"
---

# security-gate

Talk to the user in the project language (`language` in `.harness/config.json`). The user comes from frontend work, so explain each risk in plain words: what an attacker could do, and what the fix changes.

Scripts: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security.py" <scope|scan|audit|prompt|verdict>`. Settings live in `security` in `.harness/config.json`. The defaults are:

| Setting | Default |
|---|---|
| `reviewsDir` | `docs/security/reviews` |
| `decisions` | `docs/security/decisions.md` |
| `auditLevel` | `high` |
| `substitute` | `hold` |

## Rules

- A change in scope gets **GO before it is merged or deployed**. The only exception is the user explicitly approving that specific change, and the approval is recorded.
- The reviewer is independent, and Codex goes first. The reviewer never shares context with whoever wrote the change.
- Each review is read-only and covers one change. Point it at the riskiest files, and tell it not to call helper agents.
- Do not paraphrase invariants and accepted risks. Point to the spec section or to the decisions file.
- Never put secret values into prompts, review files or chat. A secret that reached git is compromised: rotate it first, then clean up the history together with the user.

## 1. Scope

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security.py" scope        # exit 1 = gate required
```

- **Gate required** when the change touches any of these:
  - auth
  - authz
  - money
  - secrets
  - personal data
  - upload
  - webhook
  - migrations
  - patterns in `security.sensitive`
- **Not required, and no dependencies changed**: say so, still run `scan` once, and stop there.
- **Pre-launch mode** (`--launch`, or "출시 전"): skip `scope`.
  - Run `scan --all` and `audit`.
  - Walk the whole checklist.
  - Review the app's risky areas, one review per area.

## 2. Automated checks

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security.py" scan          # changes since the default branch; --all for everything
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security.py" audit         # when dependencies changed, and before launch
```

- **`block`** (secrets): remove the secret and tell the user to rotate it. Never silence a `block`.
- **`high`**: fix it, through `/lofo-dev-harness:codex-delegate` or directly. If it is a false positive, or a risk the user accepts:
  1. Add `security-ok: <rule-id> <reason>` as a comment in that file.
  2. For an accepted risk, also add a dated entry to the decisions file that the user approved.
- **`review`**: confirm each item during the checklist pass.
- **Audit at or above the level**: update the package and show the lockfile diff. Never use `--force` without asking. If the advisory does not apply, record why. Exit code 3 means the audit could not run (for example, offline). Report it as "not verified" and run it in CI or later.

## 3. Checklist

Use [references/checklist.md](references/checklist.md).
- Always cover **the five essentials**, plus the sections for every category in scope.
- Mark each item ✅, ⚠️ or N/A, with one line of evidence such as `file:line` or a setting.

## 4. Independent review

1. Write the review folder:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security.py" prompt --slug <short-name> [--reviewer codex|claude]
   ```
   This writes `<reviewsDir>/<date>-<slug>/prompt.md` and `scan.json`. Before running the review, add two things to `prompt.md`:
   - pointers to the spec sections whose invariants matter, linked as they are, not paraphrased
   - your ⚠️ checklist items
2. **Codex** (when `models.codex.enabled`):
   - Run it read-only, following `/lofo-dev-harness:codex-delegate`, with the configured model and effort. The brief is the content of `prompt.md`.
   - Save Codex's full final answer as `codex.md` in the folder. Later rounds go in `codex-r2.md`, `codex-r3.md` and so on.
3. Read the verdict:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/security.py" verdict <folder>/codex.md   # 0 GO · 1 NO-GO · 2 no verdict line
   ```
   With no verdict line, ask the reviewer for one. Never infer a verdict.
4. **Codex unavailable** (rate limit, error, not installed). Follow `security.substitute`:
   - **`hold`** (default):
     - Run a Claude reviewer as a fresh subagent that did not write the change, using `prompt --reviewer claude`. Save its answer as `claude.md`.
     - Its GO is **provisional**. Report it as "임시 GO" / "provisional GO".
     - Do not merge or deploy until Codex gives GO, or until the user explicitly approves merging this specific change.
     - If the user approves, write `owner-decision.md` in the folder (date, what was approved and why) and plan a Codex re-review.
   - **`wait`**: stop. Tell the user the change is blocked until Codex is available.
   - **`allow`**: the Claude reviewer's GO counts. Record it as `claude.md`.
   - If Codex is disabled in the config, the Claude independent reviewer's verdict is final.
5. **NO-GO**:
   1. Fix the blocker and major findings.
   2. Run `scan` again.
   3. Review the fix in a new round.
   After three NO-GO rounds, stop and ask the user.

## 5. Record

The review folder holds:
- `prompt.md`
- `scan.json`
- `codex.md` or `claude.md`, plus later rounds
- `owner-decision.md`, if any
- `summary.md`, which you write. It covers:
  - the verdict
  - each finding and its fix, with `file:line`
  - accepted risks, linked to the decisions file
  - the audit result
  - what could not be verified

Commit the folder together with the change. Check it holds no secret values first.

## 6. Report

In plain language, tell the user:
- what was risky
- what was found
- what changed
- the verdict, and whether it is provisional
- the remaining risk
- the next step: whether merging is allowed, or whether it is waiting for Codex
