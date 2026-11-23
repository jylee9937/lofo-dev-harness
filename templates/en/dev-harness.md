# Development harness

> The source of truth for **how** this project is built. The summary is the harness block in `AGENTS.md`.
> Model names, gate commands and ports live only in `.harness/config.json`. To change them, edit the config and re-run `/lofo-dev-harness:init`.

## 0. At a glance

- Stack: {{framework_name}} · {{db_name}} · {{hosting_name}} · {{pm}}
- Mode: {{mode_name}} (§4)
- One feature = one branch = one PR.
- Backend work is explained first and decided together, then implemented (§6).
- Done means gates and e2e pass, not a manual check (§7).

## 1. Roles

{{#codex}}
| Who | Does |
|---|---|
| Codex | First-pass implementation, code review, bug diagnosis and root cause, backend drafts, migrations |
| Claude (main session) | Splitting work, running the process, final calls, frontend wiring and integration, verifying Codex output, explaining backend choices, records |
| Claude subagents | Delegated planning, requirements analysis, architecture and code review, code search |

Principle: send implementation, review and diagnosis to Codex first whenever Codex can do it. Claude decides what and why, then verifies, integrates and explains the result. Small mechanical edits Claude does directly.

### Delegating to Codex

- Follow the `/lofo-dev-harness:codex-delegate` skill.
- Read the model and effort from `models.codex` in `.harness/config.json` and **pass them every time**. Without them Codex silently falls back to its global default model.
- Do not change the global Codex config (`~/.codex/config.toml`). Other projects share it.
- For diagnosis or review only, delegate read-only. After a write-mode run, check what changed with `git status` and `git log main..HEAD`.
- If Codex's final message is an empty "done", find the real result in the run log.

### When Codex is unavailable

When Codex is rate-limited or missing, Claude continues instead of stopping. Order: {{fallback_chain}}.

- Hard calls such as architecture, security and access rules: the first model
- Repetitive or mechanical implementation, UI: the middle model
- Docs and commit message drafts: the last model
{{/codex}}
{{^codex}}
This project does not use Codex. Claude implements as well. Model order: {{fallback_chain}}.

- Hard calls such as architecture, security and access rules: the first model
- Repetitive or mechanical implementation, UI: the middle model
- Docs and commit message drafts: the last model
{{/codex}}

## 2. Process

Pre-development artifacts go through **write → review → approve** before the next stage. Small bug fixes and changes only go through stages 5–7.

| # | Stage | Artifact | Review |
|---|---|---|---|
| 1 | Planning and requirements | Requirements with acceptance criteria | Product and scope review |
| 2 | Screen design | {{design_source}} | Screen review |
| 3 | Technical design (when needed) | `docs/<feature>-tech-design.md` | Architecture review |
| 4 | Data consistency check | Schema and access rules checked against the real database | Migration diff, access rules tested for real |
| 5 | Development | Code on a work branch | — |
| 6 | QA | Gate and e2e results, code review | §7 |
| 7 | Release | PR merge and deploy | §3, §5 |

How to review: {{#gstack}}gstack skills (plans `/plan-ceo-review`, screens `/plan-design-review`, tech `/plan-eng-review`).{{/gstack}}{{^gstack}}give Claude subagents analyst, architect and critic roles{{#codex}}, and get a second opinion from Codex{{/codex}}.{{/gstack}}

### Required sections of a technical design doc

1. **Data model**: tables, columns, indexes, constraints, access rules (public read / owner only / staff), exposure, migration plan
2. **Server boundary and authorization**: where admin keys are used, server actions or route handlers, and what the guards cover
3. **API and queries**: public and admin queries, pagination, caching
4. **Code layout**: new modules and routes
5. **External services and compliance**: payments, personal data, consent
6. **Risks and alternatives**: trade-offs, MVP scope

## 3. One feature = one PR

```
update main
  → work branch (feat/… · fix/… · refactor/… · chore/… · docs/…)
  → data consistency check → development
  → gates + e2e + code review
  → commit → PR → self-review
  → merge to main → update records (§8)
```

{{mode_section}}

## 5. Stack rules

### Framework: {{framework_name}}

{{framework_section}}

### Database and backend: {{db_name}}

{{db_section}}

### Hosting and deployment: {{hosting_name}}

{{hosting_section}}

## 6. Backend collaboration

When touching the backend, Claude **first explains the concepts, options and trade-offs, and decides together with the user**, then implements. Even when Codex writes the code, Claude does the explaining.

Covers:
- Access rules (RLS, security rules): public read / owner only / staff roles
- Migrations: columns, indexes, grants, exposure
- Where credentials that bypass access rules, such as admin keys, are used
- Server boundaries: server actions or route handlers, and what the guards cover
- External services such as payments and webhooks

An explanation covers the concept, why this choice, and the alternatives. Decisions and trade-offs go into the technical design doc (§2).

## 7. Gates (required before done and before a PR)

{{gates_list}}

As one line: `{{gates_chain}}`

- e2e: {{e2e_line}}. e2e is the standard of proof; a manual smoke check does not count.
- QA runs its dev server on a dedicated port (`{{qa_port}}`), so it never tests a dev server from another worktree by mistake.
- For anything you could not verify, say why and give the command to run next.
- End the completion report with how the user can check it themselves (`{{dev_cmd}}` → the URL to open).

## 8. Docs and records

| Layer | Where | Holds |
|---|---|---|
| Work in progress | `{{handoff_path}}` | Handoff between sessions, open work, blockers |
| Approved specs | `docs/`, migrations (git) | Code rules, technical designs |
| Context and decisions | {{notes_where}} | Why things were decided, history |

- Only approved content moves into `docs/`. Work-in-progress thinking stays in the handoff.
- The top of the handoff file is the next session's starting point ("START HERE").
- Keep the handoff file at {{handoff_max_kb}} KB or less. Move older entries to an archive when it grows past that.

## 9. Integrations

{{integrations_list}}
