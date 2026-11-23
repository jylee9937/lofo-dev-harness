# Working harness (shared by Claude Code and Codex)

Claude enters through `CLAUDE.md → @AGENTS.md`, and Codex reads this same file as its rules. This block takes precedence over the rest of the project's guides. The detailed source of truth is `{{dev_harness_path}}`.

- Stack: {{framework_name}} · {{db_name}} · {{hosting_name}} · {{pm}}
- Mode: {{mode_name}}

## Starting work
- Start a new task in this order: update `main` → create a work branch → read the harness. In Claude Code, `/lofo-dev-harness:start-task <task>` does this.
- Before working, check `git status --short`, the current branch and the handoff file (`{{handoff_path}}`, if present).
- If a work branch has uncommitted work left over, keep going on it. Do not switch branches or stash it away.
- Pull `main` and create a new branch only when the user explicitly starts a new task.

## Reading order
1. `{{dev_harness_path}}`: roles, process, backend collaboration, gates, records
2. `.harness/config.json`: models, gate commands, QA port (model names live only in this file)
3. `{{handoff_path}}`: where the last session left off (if present)

## Roles
{{#codex}}
- **Codex** goes first on implementation, code review and bug diagnosis. Always pass the model and effort from `models.codex` in `.harness/config.json` explicitly.
- **Claude** splits the work, decides, verifies and integrates Codex output, explains, and keeps records.
- When Codex is unavailable or rate-limited, Claude continues instead of stopping. Order: {{fallback_chain}}.
{{/codex}}
{{^codex}}
- This project does not use Codex. Claude implements as well. Model order: {{fallback_chain}} (hard calls go to the first, mechanical work and docs to the last).
{{/codex}}

## Rules
{{#collab}}
- Commit, push, open PRs and merge only when the user asks.
{{/collab}}
{{#autonomous}}
- Autonomous mode is not in this version of lofo-dev-harness yet. Until it ships, commit, push, open PRs and merge only when the user asks.
{{/autonomous}}
- Never commit directly to `main`. Always create a branch first.
- No external writes, deploys or hosted database changes without the user's confirmation.
- Never print secrets or tokens, and never put them in files or commits.
- For backend work (access rules, migrations, admin keys, server boundaries), explain the concepts and options first and decide together with the user before implementing.
- When a decision is needed, ask one question at a time with the recommended option first.

## Definition of done
- All gates pass: `{{gates_chain}}`
- e2e: {{e2e_line}}
- For anything you could not verify, say why and give the command to run next.
- End the completion report with how the user can check it themselves: `{{dev_cmd}}` → the URL to open.
