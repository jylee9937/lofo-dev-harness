#!/usr/bin/env python3
"""Render lofo-dev-harness project files from .harness/config.json.

Writes or refreshes, inside a project:
  AGENTS.md            the managed harness block (between the lofo-dev-harness markers)
  CLAUDE.md            makes sure it imports @AGENTS.md
  <docs.devHarness>    the dev-harness doc, as a managed block (default docs/dev-harness.md)
  .gitignore           local-only harness files

Text outside the markers is never touched. Standard library only, Python 3.8+.

Usage:
  python3 render.py [--project DIR] [--check]

  --project DIR  project root (default: current directory)
  --check        write nothing; exit 1 if any file is missing or out of date
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = PLUGIN_ROOT / "templates"
CONFIG_REL = ".harness/config.json"
START = "<!-- lofo-dev-harness:start -->"
END = "<!-- lofo-dev-harness:end -->"
GITIGNORE_LINES = [".harness/config.local.json", ".harness/local/", "*.wireflow.html"]

LANGS = ("ko", "en")
MODES = ("collab", "autonomous")
DBS = ("supabase", "firebase", "postgres", "none", "other")
HOSTINGS = ("vercel", "gcp", "aws", "other")
PACKAGE_MANAGERS = ("pnpm", "npm", "yarn", "bun")
EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
NOTES = ("none", "obsidian", "notion", "other")
DESIGNS = ("none", "figma", "pencil", "other")
TASKS = ("none", "ticktick", "github-issues", "other")
TOP_LEVEL_KEYS = {
    "$schema", "version", "language", "mode", "stack", "models", "gates", "e2e",
    "qa", "codexRouting", "docs", "integrations", "autonomous",
}

DEV_CMD = {"pnpm": "pnpm dev", "npm": "npm run dev", "yarn": "yarn dev", "bun": "bun run dev"}

PROPER_NAMES = {
    "nextjs": "Next.js",
    "supabase": "Supabase",
    "firebase": "Firebase",
    "postgres": "PostgreSQL",
    "vercel": "Vercel",
    "gcp": "Google Cloud",
    "aws": "AWS",
    "obsidian": "Obsidian",
    "notion": "Notion",
    "figma": "Figma",
    "pencil": "Pencil",
    "ticktick": "TickTick",
    "github-issues": "GitHub Issues",
}

LABELS = {
    "ko": {
        "none": "없음",
        "other": "기타",
        "mode": {"collab": "협업", "autonomous": "자율 (준비 중, 협업 규칙 적용)"},
        "e2e_missing": "아직 설정하지 않았다. 설정하기 전까지는 완료 보고에 'e2e 없음'을 적는다",
        "design_source": {
            "figma": "Figma에서 확정한 화면",
            "pencil": "Pencil 디자인 파일에서 확정한 화면",
            "other": "확정한 화면 설계",
            "none": "화면 설계 메모 또는 와이어프레임",
        },
        "design_mirror": {
            "figma": "Figma에 같은 화면, 화살표, 검토 표시를 그린다. 파일에 처음 쓰기 전에 사용자 확인을 받는다.",
            "pencil": "Pencil(.pen)에 같은 화면, 화살표, 검토 표시를 그린다. .pen 파일은 Pencil MCP로만 연다.",
            "other": "디자인 도구에서 화면 이미지를 내보내 보드에서 와이어프레임과 함께 본다.",
            "none": "디자인 도구 없이 HTML 보드에서 검토한다.",
        },
        "notes_where": {
            "none": "`docs/`의 결정 기록",
            "default": "{name} (경로는 `.harness/config.local.json`의 `notesPath`, git에 올리지 않음)",
        },
        "integration": {
            "notes": "맥락·판단 기록: {name}. 경로처럼 내 컴퓨터에만 해당하는 값은 `.harness/config.local.json`에 둔다.",
            "design": "디자인 기준: {name}. 화면 변경은 디자인에서 먼저 확정하고 코드로 옮긴다.",
            "gstack": "검토 게이트: gstack 스킬 (따로 설치). 기획 `/plan-ceo-review`, 화면 `/plan-design-review`, 기술 `/plan-eng-review`.",
            "tasks": "할 일 관리: {name}.",
            "empty": "- 따로 연동한 도구 없음.",
        },
        "managed_note": (
            "<!-- lofo-dev-harness가 .harness/config.json으로 만든 블록입니다. "
            "이 마커 안은 직접 고치지 말고, 설정을 바꾼 뒤 /lofo-dev-harness:init 을 다시 실행하세요. -->"
        ),
        "agents_tail": (
            "# 프로젝트 가이드\n\n"
            "<!-- 명령어, 아키텍처, 절대 규칙처럼 이 프로젝트에만 해당하는 내용은 여기에 적습니다. "
            "다시 렌더링해도 지워지지 않습니다. -->\n"
        ),
        "doc_tail": (
            "## 프로젝트 고유 규칙\n\n"
            "<!-- 이 아래는 직접 적는 곳입니다. 다시 렌더링해도 지워지지 않습니다. -->\n"
        ),
    },
    "en": {
        "none": "none",
        "other": "other",
        "mode": {"collab": "collaborative", "autonomous": "autonomous (coming soon, collaborative rules apply)"},
        "e2e_missing": "not configured yet. Until it is, say \"no e2e\" in completion reports",
        "design_source": {
            "figma": "Screens approved in Figma",
            "pencil": "Screens approved in the Pencil design file",
            "other": "Approved screen design",
            "none": "Screen notes or wireframes",
        },
        "design_mirror": {
            "figma": "Draw the same screens, arrows and review marks in Figma. Confirm with the user before the first write to a file.",
            "pencil": "Draw the same screens, arrows and review marks in Pencil (.pen). Open .pen files only through the Pencil MCP.",
            "other": "Export screen images from the design tool and review them on the board next to the wireframes.",
            "none": "No design tool: review on the HTML board.",
        },
        "notes_where": {
            "none": "decision records in `docs/`",
            "default": "{name} (path in `notesPath` of `.harness/config.local.json`, never committed)",
        },
        "integration": {
            "notes": "Context and decision history: {name}. Machine-specific values such as paths go in `.harness/config.local.json`.",
            "design": "Design source of truth: {name}. Screen changes are approved in the design first, then mirrored in code.",
            "gstack": "Review gates: gstack skills (installed separately). Plans `/plan-ceo-review`, screens `/plan-design-review`, tech `/plan-eng-review`.",
            "tasks": "Task tracking: {name}.",
            "empty": "- No integrations configured.",
        },
        "managed_note": (
            "<!-- Generated by lofo-dev-harness from .harness/config.json. "
            "Do not edit inside these markers; change the config and re-run /lofo-dev-harness:init. -->"
        ),
        "agents_tail": (
            "# Project guide\n\n"
            "<!-- Project-specific content (commands, architecture, hard rules) goes here. "
            "Re-rendering never touches it. -->\n"
        ),
        "doc_tail": (
            "## Project-specific rules\n\n"
            "<!-- Write below this line. Re-rendering never touches it. -->\n"
        ),
    },
}


class HarnessError(Exception):
    pass


# ---------------------------------------------------------------- validation

def validate(cfg: object) -> list[str]:
    """Check the parts of the schema the renderer relies on.

    schemas/harness-config.schema.json is authoritative; this is a dependency-free subset.
    """
    errors: list[str] = []
    if not isinstance(cfg, dict):
        return ["config must be a JSON object"]

    def enum(path: str, value: object, allowed: tuple) -> None:
        if value not in allowed:
            errors.append(f"{path}: {value!r} is not one of {', '.join(allowed)}")

    def nonempty_str(path: str, value: object) -> None:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}: must be a non-empty string")

    for key in sorted(set(cfg) - TOP_LEVEL_KEYS):
        errors.append(f"{key}: unknown top-level key")
    for key in ("version", "language", "mode", "stack", "models", "gates"):
        if key not in cfg:
            errors.append(f"{key}: required")

    if "version" in cfg and cfg["version"] != 1:
        errors.append("version: must be 1")
    if "language" in cfg:
        enum("language", cfg["language"], LANGS)
    if "mode" in cfg:
        enum("mode", cfg["mode"], MODES)
        if cfg["mode"] == "autonomous" and not isinstance(cfg.get("autonomous"), dict):
            errors.append("autonomous: required when mode is autonomous")

    stack = cfg.get("stack")
    if "stack" in cfg:
        if not isinstance(stack, dict):
            errors.append("stack: must be an object")
        else:
            nonempty_str("stack.framework", stack.get("framework"))
            enum("stack.db", stack.get("db"), DBS)
            enum("stack.hosting", stack.get("hosting"), HOSTINGS)
            enum("stack.packageManager", stack.get("packageManager"), PACKAGE_MANAGERS)

    models = cfg.get("models")
    if "models" in cfg:
        if not isinstance(models, dict):
            errors.append("models: must be an object")
        else:
            codex = models.get("codex")
            if not isinstance(codex, dict) or not isinstance(codex.get("enabled"), bool):
                errors.append("models.codex.enabled: required boolean")
            elif codex["enabled"]:
                nonempty_str("models.codex.model", codex.get("model"))
                enum("models.codex.effort", codex.get("effort"), EFFORTS)
            fallback = models.get("claudeFallback")
            if (
                not isinstance(fallback, list)
                or not fallback
                or not all(isinstance(m, str) and m.strip() for m in fallback)
            ):
                errors.append("models.claudeFallback: must be a non-empty list of model names")

    gates = cfg.get("gates")
    if "gates" in cfg:
        if not isinstance(gates, list) or not gates:
            errors.append("gates: must be a non-empty list")
        else:
            for i, gate in enumerate(gates):
                if not isinstance(gate, dict):
                    errors.append(f"gates[{i}]: must be an object")
                    continue
                name = gate.get("name")
                if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9:-]*", name):
                    errors.append(f"gates[{i}].name: lowercase letters, digits, ':' and '-' only")
                nonempty_str(f"gates[{i}].run", gate.get("run"))

    e2e = cfg.get("e2e")
    if e2e is not None and (not isinstance(e2e, dict) or not isinstance(e2e.get("run"), str) or not e2e["run"].strip()):
        errors.append("e2e.run: must be a non-empty string")

    qa = cfg.get("qa") or {}
    port = qa.get("port", 3100) if isinstance(qa, dict) else None
    if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
        errors.append("qa.port: must be an integer between 1024 and 65535")

    integrations = cfg.get("integrations") or {}
    if isinstance(integrations, dict):
        if "notes" in integrations:
            enum("integrations.notes", integrations["notes"], NOTES)
        if "design" in integrations:
            enum("integrations.design", integrations["design"], DESIGNS)
        if "tasks" in integrations:
            enum("integrations.tasks", integrations["tasks"], TASKS)

    routing = cfg.get("codexRouting") or {}
    if isinstance(routing, dict):
        for key in ("code", "exclude", "backend"):
            for i, pattern in enumerate(routing.get(key) or []):
                try:
                    re.compile(pattern)
                except (re.error, TypeError) as exc:
                    errors.append(f"codexRouting.{key}[{i}]: invalid regular expression ({exc})")
    return errors


# ------------------------------------------------------------------ context

def display_name(value: str, labels: dict) -> str:
    if value in ("none", "other"):
        return labels[value]
    return PROPER_NAMES.get(value, value)


def build_context(cfg: dict) -> tuple[str, dict, dict]:
    lang = cfg["language"]
    labels = LABELS[lang]
    stack = cfg["stack"]
    models = cfg["models"]
    codex = models["codex"]
    gates = cfg["gates"]
    e2e = cfg.get("e2e")
    docs = cfg.get("docs") or {}
    qa = cfg.get("qa") or {}
    integrations = cfg.get("integrations") or {}

    notes = integrations.get("notes", "none")
    design = integrations.get("design", "none")
    tasks = integrations.get("tasks", "none")
    gstack = bool(integrations.get("gstack", False))

    lines = []
    if notes != "none":
        lines.append("- " + labels["integration"]["notes"].format(name=display_name(notes, labels)))
    if design != "none":
        lines.append("- " + labels["integration"]["design"].format(name=display_name(design, labels)))
    if gstack:
        lines.append("- " + labels["integration"]["gstack"])
    if tasks != "none":
        lines.append("- " + labels["integration"]["tasks"].format(name=display_name(tasks, labels)))

    notes_where = (
        labels["notes_where"]["none"]
        if notes == "none"
        else labels["notes_where"]["default"].format(name=display_name(notes, labels))
    )

    ctx = {
        "framework_name": display_name(stack["framework"], labels),
        "db_name": display_name(stack["db"], labels),
        "hosting_name": display_name(stack["hosting"], labels),
        "pm": stack["packageManager"],
        "dev_cmd": DEV_CMD[stack["packageManager"]],
        "mode_name": labels["mode"][cfg["mode"]],
        "gates_chain": " && ".join(g["run"] for g in gates),
        "gates_list": "\n".join(f"- `{g['name']}`: `{g['run']}`" for g in gates),
        "e2e_line": f"`{e2e['run']}`" if e2e else labels["e2e_missing"],
        "qa_port": str(qa.get("port", 3100)),
        "fallback_chain": " → ".join(models["claudeFallback"]),
        "dev_harness_path": docs.get("devHarness", "docs/dev-harness.md"),
        "handoff_path": docs.get("handoff", ".harness/handoff.md"),
        "handoff_max_kb": str(docs.get("handoffMaxKb", 40)),
        "design_source": labels["design_source"].get(design, labels["design_source"]["other"]),
        "design_mirror": labels["design_mirror"].get(design, labels["design_mirror"]["other"]),
        "flows_dir": docs.get("flows", "design/flows"),
        "notes_where": notes_where,
        "integrations_list": "\n".join(lines) if lines else labels["integration"]["empty"],
    }
    flags = {
        "codex": bool(codex["enabled"]),
        "collab": cfg["mode"] == "collab",
        "autonomous": cfg["mode"] == "autonomous",
        "gstack": gstack,
        "e2e": bool(e2e),
    }
    return lang, ctx, flags


# --------------------------------------------------------------- templating

def read_fragment(lang: str, rel: str) -> str:
    path = TEMPLATES / lang / rel
    if not path.is_file():
        raise HarnessError(f"missing template: {path.relative_to(PLUGIN_ROOT)}")
    return path.read_text(encoding="utf-8").strip()


def preset_fragment(lang: str, kind: str, value: str) -> str:
    """Use the preset for this value if one exists, otherwise the generic fragment."""
    specific = TEMPLATES / lang / kind / f"{value}.md"
    if value not in ("other",) and specific.is_file():
        return read_fragment(lang, f"{kind}/{value}.md")
    return read_fragment(lang, f"{kind}/_generic.md")


COND = re.compile(r"\{\{([#^])(\w+)\}\}(.*?)\{\{/\2\}\}", re.S)
VAR = re.compile(r"\{\{(\w+)\}\}")
# A section tag alone on its line takes the whole line with it (mustache "standalone" rule),
# so removed sections leave no blank lines behind.
STANDALONE_TAG = re.compile(r"^[ \t]*(\{\{[#^/]\w+\}\})[ \t]*\n", re.M)


def fill(text: str, ctx: dict, flags: dict, sections: dict) -> str:
    for key, value in sections.items():
        text = text.replace("{{" + key + "}}", value)
    text = STANDALONE_TAG.sub(r"\1", text)

    def cond(match: re.Match) -> str:
        negate, key, body = match.group(1) == "^", match.group(2), match.group(3)
        if key not in flags:
            raise HarnessError(f"unknown template flag: {key}")
        return body if bool(flags[key]) != negate else ""

    previous = None
    while previous != text:
        previous = text
        text = COND.sub(cond, text)

    def var(match: re.Match) -> str:
        key = match.group(1)
        if key not in ctx:
            raise HarnessError(f"unknown template variable: {key}")
        return ctx[key]

    text = VAR.sub(var, text)
    if "{{" in text:
        raise HarnessError("unresolved template syntax: " + text[text.index("{{"):][:60])
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_documents(cfg: dict) -> dict:
    lang, ctx, flags = build_context(cfg)
    stack = cfg["stack"]
    sections = {
        "mode_section": read_fragment(lang, f"modes/{cfg['mode']}.md"),
        "framework_section": preset_fragment(lang, "framework", stack["framework"]),
        "db_section": preset_fragment(lang, "db", stack["db"]),
        "hosting_section": preset_fragment(lang, "hosting", stack["hosting"]),
    }
    note = LABELS[lang]["managed_note"]
    agents = fill(read_fragment(lang, "AGENTS.block.md"), ctx, flags, sections)
    doc = fill(read_fragment(lang, "dev-harness.md"), ctx, flags, sections)
    return {
        "lang": lang,
        "agents_block": f"{START}\n{note}\n\n{agents}\n\n{END}",
        "doc_block": f"{START}\n{note}\n\n{doc}\n\n{END}",
        "doc_path": ctx["dev_harness_path"],
    }


# ----------------------------------------------------------------- writing

def upsert_block(existing: str | None, block: str, tail: str) -> tuple[str, str]:
    if existing is None:
        return f"{block}\n\n{tail}", "created"
    has_start, has_end = START in existing, END in existing
    if has_start != has_end or (has_start and existing.index(START) > existing.index(END)):
        raise HarnessError("found only one lofo-dev-harness marker, or they are out of order; fix the file by hand")
    if has_start:
        before = existing[: existing.index(START)]
        after = existing[existing.index(END) + len(END):]
        updated = f"{before}{block}{after}"
        return updated, ("unchanged" if updated == existing else "updated")
    return f"{block}\n\n{existing.lstrip()}", "inserted"


def plan_claude_md(existing: str | None) -> tuple[str, str]:
    if existing is None:
        return "@AGENTS.md\n", "created"
    if re.search(r"^@AGENTS\.md\s*$", existing, re.M):
        return existing, "unchanged"
    return f"@AGENTS.md\n\n{existing.lstrip()}", "inserted"


def plan_gitignore(existing: str | None) -> tuple[str, str]:
    present = set((existing or "").splitlines())
    missing = [line for line in GITIGNORE_LINES if line not in present]
    if not missing:
        return existing or "", "unchanged"
    addition = "# lofo-dev-harness (local only)\n" + "\n".join(missing) + "\n"
    if existing is None:
        return addition, "created"
    separator = "" if existing.endswith("\n") or not existing else "\n"
    return f"{existing}{separator}\n{addition}", "updated"


def read_or_none(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def run(project: Path, check: bool) -> int:
    config_path = project / CONFIG_REL
    if not config_path.is_file():
        print(f"error: {CONFIG_REL} not found in {project}. Run /lofo-dev-harness:init first.", file=sys.stderr)
        return 2
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: {CONFIG_REL} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    errors = validate(cfg)
    if errors:
        print(f"error: {CONFIG_REL} is invalid:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    try:
        docs = render_documents(cfg)
        labels = LABELS[docs["lang"]]
        doc_rel = docs["doc_path"]
        project_root = project.resolve()
        plans = []
        for rel, planner in (
            ("AGENTS.md", lambda text: upsert_block(text, docs["agents_block"], labels["agents_tail"])),
            ("CLAUDE.md", plan_claude_md),
            (doc_rel, lambda text: upsert_block(text, docs["doc_block"], labels["doc_tail"])),
            (".gitignore", plan_gitignore),
        ):
            path = (project_root / rel).resolve()
            if Path(rel).is_absolute() or project_root not in path.parents:
                raise HarnessError(f"{rel}: path must stay inside the project")
            try:
                new_text, status = planner(read_or_none(path))
            except HarnessError as exc:
                raise HarnessError(f"{rel}: {exc}") from None
            plans.append((rel, path, new_text, status))
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    stale = False
    for rel, path, new_text, status in plans:
        if status != "unchanged":
            stale = True
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new_text, encoding="utf-8")
        shown = status if not check or status == "unchanged" else f"would be {status}"
        print(f"{shown:<18} {rel}")
    return 1 if check and stale else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project", default=".", help="project root (default: current directory)")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if out of date")
    args = parser.parse_args(argv)
    return run(Path(args.project).resolve(), args.check)


if __name__ == "__main__":
    sys.exit(main())
