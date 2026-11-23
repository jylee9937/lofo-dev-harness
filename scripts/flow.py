#!/usr/bin/env python3
"""Check and render a lofo-dev-harness wireflow (design/flows/<id>.flow.json).

Usage:
  python3 flow.py check FLOW.json [--json]
  python3 flow.py build FLOW.json [OUT.html] [--embed-images]

check exit codes:
  0  no blocking problems
  1  blocking problems: S1/S2 structural findings, or open S1/S2 UX issues
  2  invalid input
build writes a self-contained HTML review board (default: <flow id>.wireflow.html next to the flow)
and exits 0 for any valid flow, even with findings, so problems can be reviewed on the board.

Standard library only, Python 3.8+. The JSON Schema in schemas/flow.schema.json is the reference;
this script checks the parts it relies on plus cross-references the schema cannot express.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
from collections import deque
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BOARD_TEMPLATE = PLUGIN_ROOT / "templates" / "wireflow" / "board.html"

ID = re.compile(r"[a-z0-9][a-z0-9-]*")
TOP_KEYS = {"$schema", "version", "id", "title", "goal", "language", "device", "source", "design",
            "stages", "start", "entries", "screens", "scenarios", "decisions", "issues", "requests"}
SCREEN_KEYS = {"id", "number", "title", "stage", "state", "origin", "rationale", "conditions",
               "wireframe", "image", "actions", "end"}
STATES = ("default", "empty", "loading", "error", "success", "modal")
ORIGINS = ("source", "inferred")
BLOCKS = ("header", "title", "text", "search", "input", "button", "list", "card", "image", "tabs",
          "notice", "toggle", "divider")
KINDS = ("primary", "secondary", "back", "close", "tab", "system")
SEVERITIES = ("S1", "S2", "S3", "S4")
CATEGORIES = ("flow", "navigation", "feedback", "error-recovery", "empty-state", "consistency", "copy",
              "accessibility", "other")
ISSUE_ORIGINS = ("ai-review", "codex", "user", "qa")
ISSUE_STATUSES = ("open", "accepted", "fixed", "wontfix")
DECISION_STATUSES = ("open", "decided", "deferred")
REQUEST_STATUSES = ("open", "done", "rejected")
SCENARIO_KINDS = ("main", "recovery", "edge")
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
               ".gif": "image/gif", ".svg": "image/svg+xml"}

MESSAGES = {
    "ko": {
        "broken-link": "'{action}' 동작이 없는 화면 '{to}'로 연결된다.",
        "missing-destination": "'{action}' 동작의 도착 화면이 아직 없다.",
        "unreachable": "시작 화면에서 이 화면으로 오는 경로가 없다.",
        "dead-end": "나가는 동작이 없는데 종료 화면으로 표시되지 않았다.",
        "trap": "여기서 종료 화면까지 가는 경로가 없다.",
        "no-end": "종료 화면(end: true)이 하나도 없다.",
        "no-recovery": "오류 화면인데 오류 상태를 벗어나는 동작(다시 시도, 뒤로)이 없다.",
        "missing-empty-state": "목록·검색이 있지만 이 단계에 빈 상태 화면이 없다.",
        "missing-error-state": "입력이 있는데 입력 오류(검증 실패) 화면으로 가는 동작이 없다.",
        "no-scenario": "시나리오가 없다. 주요 경로를 시나리오로 적어야 경로 강조와 검사가 된다.",
        "scenario-screen": "시나리오 '{scenario}' {step}단계: '{expected}' 화면이어야 하는데 '{actual}'에 있다.",
        "scenario-action": "시나리오 '{scenario}' {step}단계: '{screen}' 화면에 '{action}' 동작이 없다.",
        "scenario-missing": "시나리오 '{scenario}' {step}단계: '{action}' 동작의 도착 화면이 없다.",
        "image-missing": "시안 이미지 '{image}'를 찾을 수 없다.",
    },
    "en": {
        "broken-link": "Action '{action}' points to unknown screen '{to}'.",
        "missing-destination": "Action '{action}' has no destination yet.",
        "unreachable": "No path leads here from the start screen.",
        "dead-end": "No way out, and the screen is not marked as an end screen.",
        "trap": "No path from here reaches an end screen.",
        "no-end": "There is no end screen (end: true).",
        "no-recovery": "Error screen with no action that leaves the error state (retry, back).",
        "missing-empty-state": "Has a list or search, but this stage has no empty-state screen.",
        "missing-error-state": "Has inputs, but no action leads to an input error (validation failure) screen.",
        "no-scenario": "No scenarios. Write the main journeys as scenarios to get path highlighting and checks.",
        "scenario-screen": "Scenario '{scenario}' step {step}: expected screen '{expected}' but is on '{actual}'.",
        "scenario-action": "Scenario '{scenario}' step {step}: screen '{screen}' has no action '{action}'.",
        "scenario-missing": "Scenario '{scenario}' step {step}: action '{action}' has no destination.",
        "image-missing": "Design image '{image}' not found.",
    },
}

SUMMARY = {
    "ko": {
        "head": "{title} ({id}): 화면 {screens}개, 시나리오 {scenarios}개",
        "clean": "구조 문제 없음.",
        "findings": "구조 검사 {count}건:",
        "issues": "열린 UX 이슈: {counts}",
        "decisions": "결정 대기 {count}건",
        "requests": "처리 안 된 수정 요청 {count}건",
        "blocking": "통과 못 함: S1/S2 문제가 남아 있다.",
        "pass": "통과: S1/S2 문제 없음.",
    },
    "en": {
        "head": "{title} ({id}): {screens} screens, {scenarios} scenarios",
        "clean": "No structural problems.",
        "findings": "{count} structural findings:",
        "issues": "Open UX issues: {counts}",
        "decisions": "{count} open decisions",
        "requests": "{count} unresolved change requests",
        "blocking": "Not passing: S1/S2 problems remain.",
        "pass": "Passing: no S1/S2 problems.",
    },
}


class FlowError(Exception):
    pass


# ---------------------------------------------------------------- validation

def validate(flow: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(flow, dict):
        return ["flow must be a JSON object"]

    def is_id(value: object) -> bool:
        return isinstance(value, str) and ID.fullmatch(value) is not None

    def text(path: str, value: object, required: bool = True) -> None:
        if value is None and not required:
            return
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}: must be a non-empty string")

    def enum(path: str, value: object, allowed: tuple, required: bool = True) -> None:
        if value is None and not required:
            return
        if value not in allowed:
            errors.append(f"{path}: {value!r} is not one of {', '.join(allowed)}")

    for key in sorted(set(flow) - TOP_KEYS):
        errors.append(f"{key}: unknown top-level key")
    missing = [key for key in ("version", "id", "title", "goal", "language", "stages", "start", "screens")
               if key not in flow]
    if missing:
        return errors + [f"{key}: required" for key in missing]

    if flow["version"] != 1:
        errors.append("version: must be 1")
    if not is_id(flow["id"]):
        errors.append("id: lowercase letters, digits and '-' only")
    text("title", flow["title"])
    text("goal", flow["goal"])
    enum("language", flow["language"], ("ko", "en"))
    enum("device", flow.get("device"), ("mobile", "tablet", "desktop"), required=False)

    stages = flow["stages"]
    stage_ids: set[str] = set()
    if not isinstance(stages, list) or not stages:
        errors.append("stages: must be a non-empty list")
        stages = []
    for i, stage in enumerate(stages):
        if not isinstance(stage, dict) or not is_id(stage.get("id")):
            errors.append(f"stages[{i}].id: required ID")
            continue
        if stage["id"] in stage_ids:
            errors.append(f"stages[{i}].id: duplicate '{stage['id']}'")
        stage_ids.add(stage["id"])
        text(f"stages[{i}].title", stage.get("title"))

    screens = flow["screens"]
    screen_ids: set[str] = set()
    actions_by_screen: dict[str, set[str]] = {}
    if not isinstance(screens, list) or not screens:
        errors.append("screens: must be a non-empty list")
        screens = []
    for i, screen in enumerate(screens):
        where = f"screens[{i}]"
        if not isinstance(screen, dict) or not is_id(screen.get("id")):
            errors.append(f"{where}.id: required ID")
            continue
        sid = screen["id"]
        where = f"screens[{i}] '{sid}'"
        for key in sorted(set(screen) - SCREEN_KEYS):
            errors.append(f"{where}: unknown key '{key}'")
        if sid in screen_ids:
            errors.append(f"{where}: duplicate screen ID")
        screen_ids.add(sid)
        text(f"{where}.title", screen.get("title"))
        if screen.get("stage") not in stage_ids:
            errors.append(f"{where}.stage: unknown stage {screen.get('stage')!r}")
        enum(f"{where}.state", screen.get("state"), STATES, required=False)
        enum(f"{where}.origin", screen.get("origin"), ORIGINS)
        if "number" in screen and not (isinstance(screen["number"], str)
                                       and re.fullmatch(r"[0-9]+(\.[0-9]+)*", screen["number"])):
            errors.append(f"{where}.number: digits and dots only, like 02.01")
        if "conditions" in screen and not (isinstance(screen["conditions"], list)
                                           and all(isinstance(c, str) for c in screen["conditions"])):
            errors.append(f"{where}.conditions: must be a list of strings")
        if "end" in screen and not isinstance(screen["end"], bool):
            errors.append(f"{where}.end: must be true or false")
        if "image" in screen:
            text(f"{where}.image", screen["image"])

        action_ids: set[str] = set()
        actions = screen.get("actions")
        if not isinstance(actions, list):
            errors.append(f"{where}.actions: required list (may be empty)")
            actions = []
        for j, action in enumerate(actions):
            awhere = f"{where}.actions[{j}]"
            if not isinstance(action, dict) or not is_id(action.get("id")):
                errors.append(f"{awhere}.id: required ID")
                continue
            if action["id"] in action_ids:
                errors.append(f"{awhere}: duplicate action ID '{action['id']}'")
            action_ids.add(action["id"])
            text(f"{awhere}.label", action.get("label"))
            if "to" not in action:
                errors.append(f"{awhere}.to: required (screen ID or null)")
            elif action["to"] is not None and not is_id(action["to"]):
                errors.append(f"{awhere}.to: must be a screen ID or null")
            enum(f"{awhere}.kind", action.get("kind"), KINDS, required=False)
        actions_by_screen[sid] = action_ids

        blocks = screen.get("wireframe", [])
        if not isinstance(blocks, list):
            errors.append(f"{where}.wireframe: must be a list")
            blocks = []
        for j, block in enumerate(blocks):
            bwhere = f"{where}.wireframe[{j}]"
            if not isinstance(block, dict):
                errors.append(f"{bwhere}: must be an object")
                continue
            enum(f"{bwhere}.type", block.get("type"), BLOCKS)
            if "action" in block and block["action"] not in action_ids:
                errors.append(f"{bwhere}.action: no action '{block['action']}' on this screen")
            if "items" in block and not (isinstance(block["items"], list)
                                         and all(isinstance(x, str) for x in block["items"])):
                errors.append(f"{bwhere}.items: must be a list of strings")

    if flow["start"] not in screen_ids:
        errors.append(f"start: unknown screen {flow['start']!r}")
    for i, entry in enumerate(flow.get("entries") or []):
        if entry not in screen_ids:
            errors.append(f"entries[{i}]: unknown screen {entry!r}")

    def check_refs(kind: str, items: object, extra) -> None:
        if items is None:
            return
        if not isinstance(items, list):
            errors.append(f"{kind}: must be a list")
            return
        seen: set[str] = set()
        for i, item in enumerate(items):
            where = f"{kind}[{i}]"
            if not isinstance(item, dict) or not is_id(item.get("id")):
                errors.append(f"{where}.id: required ID")
                continue
            if item["id"] in seen:
                errors.append(f"{where}: duplicate ID '{item['id']}'")
            seen.add(item["id"])
            screen = item.get("screen")
            if screen is not None and screen not in screen_ids:
                errors.append(f"{where}.screen: unknown screen {screen!r}")
            action = item.get("action")
            if action is not None and screen in actions_by_screen and action not in actions_by_screen[screen]:
                errors.append(f"{where}.action: screen '{screen}' has no action '{action}'")
            extra(where, item)

    def scenario_extra(where: str, item: dict) -> None:
        text(f"{where}.title", item.get("title"))
        enum(f"{where}.kind", item.get("kind"), SCENARIO_KINDS, required=False)
        if "start" in item and item["start"] not in screen_ids:
            errors.append(f"{where}.start: unknown screen {item['start']!r}")
        steps = item.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{where}.steps: must be a non-empty list")
            return
        for k, step in enumerate(steps):
            if not isinstance(step, dict) or not is_id(step.get("screen")) or not is_id(step.get("action")):
                errors.append(f"{where}.steps[{k}]: needs screen and action IDs")
            elif step["screen"] not in screen_ids:
                errors.append(f"{where}.steps[{k}].screen: unknown screen {step['screen']!r}")

    def decision_extra(where: str, item: dict) -> None:
        text(f"{where}.question", item.get("question"))
        enum(f"{where}.status", item.get("status"), DECISION_STATUSES)

    def issue_extra(where: str, item: dict) -> None:
        if item.get("screen") is None:
            errors.append(f"{where}.screen: required")
        enum(f"{where}.severity", item.get("severity"), SEVERITIES)
        enum(f"{where}.category", item.get("category"), CATEGORIES)
        text(f"{where}.title", item.get("title"))
        enum(f"{where}.origin", item.get("origin"), ISSUE_ORIGINS)
        enum(f"{where}.status", item.get("status"), ISSUE_STATUSES)

    def request_extra(where: str, item: dict) -> None:
        if item.get("screen") is None:
            errors.append(f"{where}.screen: required")
        text(f"{where}.text", item.get("text"))
        enum(f"{where}.status", item.get("status"), REQUEST_STATUSES)

    check_refs("scenarios", flow.get("scenarios"), scenario_extra)
    check_refs("decisions", flow.get("decisions"), decision_extra)
    check_refs("issues", flow.get("issues"), issue_extra)
    check_refs("requests", flow.get("requests"), request_extra)
    return errors


# ----------------------------------------------------------------- analysis

def display_numbers(flow: dict) -> dict[str, str]:
    order = {stage["id"]: i for i, stage in enumerate(flow["stages"])}
    counters: dict[str, int] = {}
    numbers: dict[str, str] = {}
    for screen in flow["screens"]:
        counters[screen["stage"]] = counters.get(screen["stage"], 0) + 1
        numbers[screen["id"]] = screen.get("number") or f"{order[screen['stage']] + 1:02d}.{counters[screen['stage']]:02d}"
    return numbers


def find_problems(flow: dict, base_dir: Path | None = None) -> list[dict]:
    msg = MESSAGES[flow["language"]]
    screens = {s["id"]: s for s in flow["screens"]}
    findings: list[dict] = []

    # Positional-only on purpose: message fields are also called "screen" and "action".
    def add(code: str, severity: str, screen_id: str | None = None, action_id: str | None = None, /, **fmt) -> None:
        findings.append({
            "code": code,
            "severity": severity,
            "screen": screen_id,
            "action": action_id,
            "message": msg[code].format(**fmt),
        })

    edges: dict[str, list[str]] = {sid: [] for sid in screens}
    for sid, screen in screens.items():
        for action in screen["actions"]:
            to = action["to"]
            if to is None:
                add("missing-destination", "S2", sid, action["id"], action=action["label"])
            elif to not in screens:
                add("broken-link", "S1", sid, action["id"], action=action["label"], to=to)
            else:
                edges[sid].append(to)

    def reach(starts) -> set[str]:
        seen = set(starts)
        queue = deque(starts)
        while queue:
            for nxt in edges[queue.popleft()]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    reachable = reach([flow["start"], *(flow.get("entries") or [])])
    for sid in screens:
        if sid not in reachable:
            add("unreachable", "S2", sid)

    ends = {sid for sid, s in screens.items() if s.get("end")}
    for sid, screen in screens.items():
        if not screen["actions"] and not screen.get("end"):
            add("dead-end", "S2", sid)
    if not ends:
        add("no-end", "S3")
    else:
        for sid in sorted(reachable):
            if sid in ends or not screens[sid]["actions"]:
                continue
            if not (reach([sid]) & ends):
                add("trap", "S2", sid)

    for sid, screen in screens.items():
        if screen.get("state") == "error":
            exits = [a for a in screen["actions"]
                     if a["to"] in screens and a["to"] != sid and screens[a["to"]].get("state") != "error"]
            if screen["actions"] and not exits:
                add("no-recovery", "S2", sid)

    by_stage: dict[str, list[dict]] = {}
    for screen in flow["screens"]:
        by_stage.setdefault(screen["stage"], []).append(screen)
    for stage_screens in by_stage.values():
        states = {s.get("state", "default") for s in stage_screens}
        for screen in stage_screens:
            types = {b.get("type") for b in screen.get("wireframe") or []}
            if screen.get("state", "default") == "default":
                if types & {"list", "search"} and "empty" not in states:
                    add("missing-empty-state", "S3", screen["id"])
                # A form needs its own validation-failure path; a later network error does not count.
                leads_to_error = any(a["to"] in screens and screens[a["to"]].get("state") == "error"
                                     for a in screen["actions"])
                if "input" in types and not leads_to_error:
                    add("missing-error-state", "S3", screen["id"])

    scenarios = flow.get("scenarios") or []
    if not scenarios:
        add("no-scenario", "S3")
    for scenario in scenarios:
        current = scenario.get("start") or flow["start"]
        for number, step in enumerate(scenario["steps"], start=1):
            if step["screen"] != current:
                add("scenario-screen", "S1", step["screen"], step["action"], scenario=scenario["title"],
                    step=number, expected=current, actual=step["screen"])
                break
            action = next((a for a in screens[current]["actions"] if a["id"] == step["action"]), None)
            if action is None:
                add("scenario-action", "S1", current, step["action"], scenario=scenario["title"],
                    step=number, screen=current, action=step["action"])
                break
            if action["to"] not in screens:
                add("scenario-missing", "S1", current, action["id"], scenario=scenario["title"],
                    step=number, action=action["label"])
                break
            current = action["to"]

    if base_dir is not None:
        for sid, screen in screens.items():
            if screen.get("image") and not (base_dir / screen["image"]).is_file():
                add("image-missing", "S3", sid, image=screen["image"])

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: order[f["severity"]])
    return findings


def blocking(flow: dict, findings: list[dict]) -> bool:
    if any(f["severity"] in ("S1", "S2") for f in findings):
        return True
    return any(i["severity"] in ("S1", "S2") and i["status"] in ("open", "accepted")
               for i in flow.get("issues") or [])


def summary_text(flow: dict, findings: list[dict]) -> str:
    s = SUMMARY[flow["language"]]
    numbers = display_numbers(flow)
    lines = [s["head"].format(title=flow["title"], id=flow["id"], screens=len(flow["screens"]),
                              scenarios=len(flow.get("scenarios") or []))]
    if findings:
        lines.append(s["findings"].format(count=len(findings)))
        for f in findings:
            where = f"{numbers.get(f['screen'], '--')} {f['screen']}" if f["screen"] else "flow"
            lines.append(f"  [{f['severity']}] {f['code']:<20} {where}: {f['message']}")
    else:
        lines.append(s["clean"])
    open_issues = [i for i in flow.get("issues") or [] if i["status"] in ("open", "accepted")]
    if open_issues:
        counts = ", ".join(f"{sev} {n}" for sev in SEVERITIES
                           if (n := sum(1 for i in open_issues if i["severity"] == sev)))
        lines.append(s["issues"].format(counts=counts))
    open_decisions = [d for d in flow.get("decisions") or [] if d["status"] == "open"]
    if open_decisions:
        lines.append(s["decisions"].format(count=len(open_decisions)))
    open_requests = [r for r in flow.get("requests") or [] if r["status"] == "open"]
    if open_requests:
        lines.append(s["requests"].format(count=len(open_requests)))
    lines.append(s["blocking"] if blocking(flow, findings) else s["pass"])
    return "\n".join(lines)


# -------------------------------------------------------------------- build

def image_source(screen_image: str, flow_dir: Path, out_dir: Path, embed: bool) -> str | None:
    path = (flow_dir / screen_image).resolve()
    if not path.is_file():
        return None
    if embed:
        mime = IMAGE_TYPES.get(path.suffix.lower())
        if mime is None:
            return None
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return Path(os.path.relpath(path, out_dir.resolve())).as_posix()


def build_html(flow: dict, findings: list[dict], flow_path: Path, out_path: Path, embed: bool) -> str:
    if not BOARD_TEMPLATE.is_file():
        raise FlowError(f"missing board template: {BOARD_TEMPLATE}")
    flow_dir = flow_path.parent
    images = {}
    for screen in flow["screens"]:
        if screen.get("image"):
            src = image_source(screen["image"], flow_dir, out_path.parent, embed)
            if src:
                images[screen["id"]] = src
    try:
        shown_path = flow_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        shown_path = flow_path.name
    data = {
        "flow": flow,
        "findings": findings,
        "numbers": display_numbers(flow),
        "images": images,
        "meta": {"flowPath": shown_path, "generator": "lofo-dev-harness flow.py"},
    }
    payload = json.dumps(data, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = BOARD_TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("__WIREFLOW_LANG__", flow["language"])
    page = page.replace("__WIREFLOW_TITLE__", html.escape(flow["title"]))
    page = page.replace("__WIREFLOW_DATA__", payload)
    return page


# ---------------------------------------------------------------------- cli

def load(path: Path) -> dict:
    try:
        flow = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FlowError(f"{path}: not found") from None
    except json.JSONDecodeError as exc:
        raise FlowError(f"{path}: not valid JSON: {exc}") from None
    errors = validate(flow)
    if errors:
        raise FlowError(f"{path} is invalid:\n" + "\n".join(f"  - {e}" for e in errors))
    return flow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check and render a lofo-dev-harness wireflow.")
    sub = parser.add_subparsers(dest="command", required=True)
    check_p = sub.add_parser("check", help="report structural problems and open review items")
    check_p.add_argument("flow")
    check_p.add_argument("--json", action="store_true", help="print findings as JSON")
    build_p = sub.add_parser("build", help="write the HTML review board")
    build_p.add_argument("flow")
    build_p.add_argument("out", nargs="?")
    build_p.add_argument("--embed-images", action="store_true", help="inline design images as data URIs")
    args = parser.parse_args(argv)

    flow_path = Path(args.flow)
    try:
        flow = load(flow_path)
    except FlowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = find_problems(flow, flow_path.parent)

    if args.command == "check":
        if args.json:
            print(json.dumps({"flow": flow["id"], "blocking": blocking(flow, findings), "findings": findings},
                             ensure_ascii=False, indent=2))
        else:
            print(summary_text(flow, findings))
        return 1 if blocking(flow, findings) else 0

    out_path = Path(args.out) if args.out else flow_path.with_name(f"{flow['id']}.wireflow.html")
    try:
        page = build_html(flow, findings, flow_path, out_path, args.embed_images)
    except FlowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    print(summary_text(flow, findings))
    print(f"board: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
