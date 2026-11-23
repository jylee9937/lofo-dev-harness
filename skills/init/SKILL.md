---
name: init
description: Set up or refresh lofo-dev-harness in the current project. Asks the user one question at a time (doc language, mode, framework, database, hosting, gate commands, integrations, Codex), writes .harness/config.json, then generates the AGENTS.md harness block, CLAUDE.md and the dev-harness doc. Use for "set up the harness", "install the harness in this project", "하네스 설치", "하네스 세팅", "하네스 초기화", or after .harness/config.json was edited by hand.
argument-hint: "[--refresh]"
---

# init

Sets up lofo-dev-harness in the current project, or refreshes the files it generates.

Talk to the user in their language. Once `.harness/config.json` exists, use its `language`.

## 0. Preconditions

- Work from the project root: `git rev-parse --show-toplevel`. If this is not a git repository, ask whether to run `git init`; do not run it without a yes.
- `python3 --version` must succeed. If it fails, stop and tell the user Python 3 is required.
- The renderer is `${CLAUDE_PLUGIN_ROOT}/scripts/render.py`.

## 1. Refresh or set up

- `.harness/config.json` exists and the argument is `--refresh`: go to step 5.
- It exists without `--refresh`: ask one question. Options: refresh from the current config (Recommended), or go through the questions again with the current values as the recommended options.
- It does not exist: continue.

## 2. Detect before asking

Look at the project first. Detected values become the recommended option of each question.

| Signal | Suggests |
|---|---|
| `next` in `package.json` dependencies | framework `nextjs` |
| `pnpm-lock.yaml` / `package-lock.json` / `yarn.lock` / `bun.lock` or `bun.lockb` | packageManager |
| `supabase/` directory or an `@supabase/*` dependency | db `supabase` |
| `firebase.json`, `.firebaserc` or a `firebase` / `firebase-admin` dependency | db `firebase` |
| `prisma/`, `drizzle.config.*`, or a `pg` / `postgres` dependency | db `postgres` |
| `vercel.json` or `.vercel/` | hosting `vercel` |
| `app.yaml`, `cloudbuild.yaml`, `Dockerfile` with Cloud Run notes | hosting `gcp` |
| `serverless.yml`, `cdk.json`, `amplify/`, `template.yaml` | hosting `aws` |
| `package.json` scripts (`lint`, `typecheck`, `test`, `build`, `check:*`) | gate commands |
| `playwright.config.*` and an e2e script | e2e command |
| `codex --version` succeeds | Codex available |
| `model` and `model_reasoning_effort` in `~/.codex/config.toml` | Codex model and effort |
| existing `AGENTS.md` / `CLAUDE.md` | rules to keep (step 6) |

An empty project (no `package.json`) is fine: recommend the user's likely stack and say nothing was detected.

## 3. Interview: one question per AskUserQuestion call

- Exactly one question per call. Wait for the answer before asking the next.
- The recommended option goes first, labelled "(Recommended)" (in Korean, "(추천)"). Normally that is the detected value.
- Each question stands alone: say what it decides and what you detected.
- A free-text answer ("Other") maps to the nearest schema value. If none fits, use `other` and keep the user's words for the summary.

Ask in this order:

1. **Doc language**: `ko` or `en`. Recommend the language the user writes in.
2. **Mode**:
   - collaborative: commits and PRs only on request (Recommended)
   - autonomous: unattended work in a time window
   Autonomous is not available in this version. Say so in its option description. If the user picks it anyway, ask for a timezone and use these defaults: window 00:00–08:00, wrap-up 07:50, decisions 09:00, stop at 95% weekly usage. Tell the user the generated rules follow collaborative mode until the module ships.
3. **Framework**: the detected one / Next.js / other.
4. **Database and backend**: Supabase / Firebase / PostgreSQL (self-managed or another host) / none. Only Supabase has a full preset in this version. The others get generic rules; say so.
5. **Server and deployment**: Vercel / Google Cloud / AWS / other. Only Vercel has a full preset; say so.
6. **Gate commands**: propose a set built from the `package.json` scripts, in the order lint, typecheck, test, build, then `check:*`. The proposed set is the recommended option; adding or removing is "Other". Give each gate a short lowercase name. Then confirm the e2e command if one was found, or record that there is none.
7. **Integrations** (`multiSelect: true`): notes app (Obsidian or Notion), design source (Figma or Pencil), gstack review skills, task app (TickTick or GitHub Issues). If a notes app is chosen and the user gives a vault or workspace path, that path is personal. It goes in `.harness/config.local.json` as `"notesPath"`, never in `config.json`.
8. **Codex**: use Codex (Recommended when `codex` is installed) / do not use Codex. If used, ask for the model next: the value from `~/.codex/config.toml` is the recommended option. Then ask for effort: `xhigh` (Recommended) / `high`. Fallback order defaults to `["opus", "sonnet", "haiku"]`.

These are not asked. Mention them in the summary so the user can change them:
- QA port 3100
- viewports 390, 768, 1440
- docs paths and `handoffMaxKb` 40
- `codexRouting`: copy it from `${CLAUDE_PLUGIN_ROOT}/examples/nextjs-supabase-vercel.config.json` for Next.js. Otherwise leave it out, and the hook uses its built-in defaults.

## 4. Write the config

- Write `.harness/config.json` with these fields first, then the answers:
  - `"$schema": "https://raw.githubusercontent.com/jylee9937/lofo-dev-harness/main/schemas/harness-config.schema.json"`
  - `"version": 1`
- Reference examples are in `${CLAUDE_PLUGIN_ROOT}/examples/`. The schema is `${CLAUDE_PLUGIN_ROOT}/schemas/harness-config.schema.json`.
- If a notes path was given, write `.harness/config.local.json` containing `{"notesPath": "<path>"}`.
- Show the user a short summary of the config before rendering.

## 5. Render

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" --project "$(git rev-parse --show-toplevel)"
```

The output lists each file as `created`, `updated`, `inserted` or `unchanged`.
- Validation errors: fix the config and run it again. If the fix is a choice, ask the user.
- Marker errors: tell the user which file to fix. Do not rewrite it yourself.

The renderer only touches text between `<!-- lofo-dev-harness:start -->` and `<!-- lofo-dev-harness:end -->`, an `@AGENTS.md` line in `CLAUDE.md`, and two lines in `.gitignore`.

## 6. Overlapping rules

If `AGENTS.md`, `CLAUDE.md` or `docs/` already had harness rules, list each overlap with the new block and ask whether to remove the old version. Look for:
- another `*:HARNESS:START` block
- model routing sections
- hardcoded model names
- gate command lists

Never delete anything without a yes.

## 7. Report

- Files written, with their status.
- Config summary: stack, mode, Codex model and effort, gates, e2e.
- Defaults you applied, and which parts are generic because no preset exists yet.
- Next step: `/lofo-dev-harness:start-task <task>`.
- Do not commit. Offer to commit the generated files on a branch.
