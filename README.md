# lofo-dev-harness

A reusable development harness for building software with **Claude Code as the orchestrator** and **Codex as the implementation and review worker**.

It is distilled from the harnesses of three production side projects. The main goal is to stop copied rules, hooks, skills and scripts from drifting apart across projects.

> **Status: early skeleton.** The plugin installs, but it has no skills or hooks yet. The current design is in [`docs/design.ko.md`](docs/design.ko.md) (Korean). [한국어 README](README.ko.md)

## Install

In Claude Code 2.1.275 or later:

```
/plugin install lofo-dev-harness --marketplace jylee9937/lofo-dev-harness
```

Older versions:

```
/plugin marketplace add jylee9937/lofo-dev-harness
/plugin install lofo-dev-harness@lofo-dev-harness
```

Skills will be called as `/lofo-dev-harness:<skill>`, for example `/lofo-dev-harness:init`.

## Planned shape

- **Claude Code plugin marketplace.** Skills, hooks and agents live in one place, so an update reaches every project.
- **`init` skill.** It asks you one question at a time (doc language, mode, framework, database, hosting, gate commands, integrations, Codex model). Then it generates `AGENTS.md`, `CLAUDE.md`, `docs/` and `.harness/config.json` in your project. Codex reads the same `AGENTS.md`.
- **Two modes on a shared core.**
  - *Collaborative*: commits and PRs only when you ask.
  - *Autonomous*: unattended work in a time window, a decision queue for the owner, and merges only after a Codex security gate.
- **Stack-neutral core plus presets.** The first preset is Next.js + Supabase + Vercel. Firebase, GCP and AWS are planned.

## Configuration

Each project keeps one committed file, `.harness/config.json`, that every skill, hook and script reads. Model names, gate commands, the QA port and backend path patterns live there, so changing a model means editing one line.

- Schema: [`schemas/harness-config.schema.json`](schemas/harness-config.schema.json)
- Examples: [collaborative, Next.js + Supabase + Vercel](examples/nextjs-supabase-vercel.config.json) and [autonomous](examples/autonomous.config.json)

Machine-specific values such as local paths never go in this file. They belong in `.harness/config.local.json`, which is gitignored.

## License

[MIT](LICENSE)
