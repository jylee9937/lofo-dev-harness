---
name: start-task
description: Start a new task. Checks for uncommitted work, updates the default branch, proposes and creates a work branch, then loads this project's harness (AGENTS.md block, dev-harness doc, .harness/config.json, handoff) and says which process stage the task starts at. Use for "start a task", "start coding", "작업 시작", "작업 준비", "main pull 받고 작업 시작", "새 브랜치 파서 작업".
argument-hint: "<task description>"
---

# start-task

Answer in the project's language (`language` in `.harness/config.json`), or in the user's language when there is no config.

## 1. Task description

Take it from the arguments. If there are none, ask one question: what task to start.

## 2. Uncommitted work

```bash
git status --short
git branch --show-current
```

- Clean tree: continue.
- Changes present: show them and ask one question:
  - continue, and the changes come along to the new branch
  - cancel, and the user commits or stashes first
  On cancel, stop.
- Already on a work branch with uncommitted work, and the user did not clearly ask for a *new* task: recommend continuing on the current branch instead of creating a new one.

## 3. Branch name

Format `<type>/<slug>`:
- `type`: `feat` (feature), `fix` (bug), `refactor`, `chore` (config, tooling), `docs`, `test`.
- `slug`: English kebab-case, 2–4 key words, at most 40 characters. Translate a description in another language by meaning, not word for word.

| Task description | Branch |
|---|---|
| Reset scroll position after submitting the form | `fix/form-submit-scroll-reset` |
| Add infinite scroll to the article list | `feat/article-infinite-scroll` |
| 상단 내비게이션 컴포넌트 정리 | `refactor/top-navigation` |

Confirm with one question:
- use the proposed name (Recommended)
- another name, as "Other"
- cancel

If the branch already exists, propose the name with `-2`, then `-3`.

## 4. Update the default branch and create the work branch

```bash
DEFAULT=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
DEFAULT=${DEFAULT:-main}
git checkout "$DEFAULT"
git pull --ff-only origin "$DEFAULT"
git checkout -b "<branch>"
```

- If there is no `origin` remote, skip the pull and branch from the local default branch.
- Stop on any error and show it: conflicts, a pull that is not fast-forward, or a missing default branch (list `git branch -a`).

## 5. Load the harness

If `.harness/config.json` exists, read these:
- `AGENTS.md`: the block between the lofo-dev-harness markers, plus the project guide below it
- the dev-harness doc: `docs.devHarness` in the config, default `docs/dev-harness.md`
- the handoff file: `docs.handoff`, default `.harness/handoff.md`. Read the "START HERE" part.
- the config itself: mode, Codex model and effort, gates, e2e

If there is no config, say "the harness is not set up here; run `/lofo-dev-harness:init`". Load `AGENTS.md` and `CLAUDE.md` if they exist and continue.

Then decide:
- **Starting stage**, using §2 of the dev-harness doc:
  - a new feature without written requirements → stage 1
  - requirements exist but there is no design → stage 2 or 3. A new screen or a changed user flow starts at stage 2 with `/lofo-dev-harness:wireflow`.
  - a bug fix or small change → stage 5. With Codex enabled, start with a read-only Codex diagnosis.
- **Backend-sensitive work**: the task touches the database, auth, server boundaries or migrations, or the likely files match `codexRouting.backend`. Plan to explain concepts and options before implementing (§6 of the doc), and say so.
- **Security gate**: say up front when the task touches auth, permissions, money, secrets, personal data, uploads, webhooks or permission migrations. It will need GO from `/lofo-dev-harness:security-gate` before merge, so plan time for that review.
- **Codex**: if `models.codex.enabled`, say that implementation, review and diagnosis go to Codex through `/lofo-dev-harness:codex-delegate`, with the configured model and effort.

## 6. Report

```
Ready.

Branch:  <branch>
Base:    <git log --oneline -1 of the default branch>
Harness: <e.g. "collaborative · Codex <model> <effort> · gates: lint, typecheck, build" | "not set up: run /lofo-dev-harness:init">
Start:   <stage and why>
Notes:   <backend-sensitive? handoff blockers?>
```

Write the report in the project's language.

## Errors

| Situation | What to do |
|---|---|
| No default branch found | Show `git branch -a` and ask which branch to start from |
| Pull conflict or not fast-forward | Stop, show the files, and ask the user to resolve |
| Branch name taken | Propose `-2`, `-3` |
| No `origin` remote | Create the branch locally |
