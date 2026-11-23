# lofo-dev-harness

A reusable development harness for building software with **Claude Code as the orchestrator** and **Codex as the implementation and review worker**.

It is distilled from the harnesses of three production side projects. The main goal is to stop copied rules, hooks, skills and scripts from drifting apart across projects.

> **Status: design phase.** Nothing is installable yet. The current design is in [`docs/design.ko.md`](docs/design.ko.md) (Korean). [한국어 README](README.ko.md)

## Planned shape

- **Claude Code plugin marketplace.** Skills, hooks and agents live in one place, so an update reaches every project.
- **`harness-init` skill.** It asks you one question at a time (doc language, mode, framework, database, hosting, gate commands, integrations, Codex model) and generates `AGENTS.md`, `CLAUDE.md` and `docs/` in your project. Codex reads the same `AGENTS.md`.
- **Two modes on a shared core.**
  - *Collaborative*: commits and PRs only when you ask.
  - *Autonomous*: night-shift work, a morning decision queue, and AI-run merges behind a mandatory Codex security gate.
- **Stack-neutral core plus presets.** The first preset is Next.js + Supabase + Vercel. Firebase, GCP and AWS are planned.
- **One config file** (`.harness/config.json`) for model names, gate commands, QA port and backend path patterns.

## License

To be decided.
