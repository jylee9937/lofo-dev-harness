#!/usr/bin/env python3
"""PreToolUse hook: remind the orchestrator to delegate source edits to Codex.

Runs on Edit/Write/MultiEdit. When the target is a source file in a project whose
.harness/config.json enables Codex, it adds a reminder to Claude's context:
delegate implementation, review and diagnosis to Codex first, with the configured
model and effort.

Non-blocking on purpose: when Codex is unavailable or rate-limited the harness lets
Claude edit directly, so a hard deny would contradict it. Always exits 0 and stays
silent in projects without the harness, with Codex disabled, or for non-source files.
"""
import json
import os
import re
import sys

DEFAULT_CODE = [r"\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|kt|swift|rb|php|sql)$"]
DEFAULT_EXCLUDE = [
    r"(^|/)(docs|\.harness|\.claude|\.agents|node_modules|\.next|dist|build|coverage)/",
    r"\.d\.ts$",
]
DEFAULT_BACKEND = [
    r"(^|/)(supabase|migrations|prisma)/",
    r"\.sql$",
    r"/api/",
    r"actions?\.(ts|js)$",
    r"server-only",
    r"webhook",
    r"(^|/)functions/",
]

MESSAGES = {
    "ko": {
        "head": "⚠️ Codex 우선 (lofo-dev-harness): 이 소스 파일을 직접 고치기 전에 확인하세요.",
        "target": "대상: {path}",
        "route": "구현·리뷰·진단은 먼저 Codex에 맡기고 결과를 검수·통합하세요. /lofo-dev-harness:codex-delegate, 모델 {model}, effort {effort} (모델을 빼면 Codex 전역 기본값으로 바뀝니다).",
        "backend": "백엔드 민감 경로입니다. 개념과 선택지를 먼저 설명하고 사용자와 함께 정한 뒤 진행하세요.",
        "allow": "그대로 진행해도 되는 경우: 작은 연결·통합 수정, Codex 결과의 정합 수정, Codex를 쓸 수 없을 때 (대체 순서: {fallback}).",
    },
    "en": {
        "head": "⚠️ Codex first (lofo-dev-harness): check before editing this source file directly.",
        "target": "Target: {path}",
        "route": "Delegate implementation, review and diagnosis to Codex first, then verify and integrate the result. Use /lofo-dev-harness:codex-delegate with model {model} and effort {effort} (omitting the model falls back to Codex's global default).",
        "backend": "Backend-sensitive path. Explain the concepts and options first and decide together with the user before proceeding.",
        "allow": "Fine to proceed directly for: small wiring or integration edits, fixing up Codex output, or when Codex is unavailable (fallback order: {fallback}).",
    },
}


def matches(patterns, path):
    for pattern in patterns:
        try:
            if re.search(pattern, path):
                return True
        except (re.error, TypeError):
            continue
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        return

    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    try:
        with open(os.path.join(root, ".harness", "config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        return
    if not isinstance(cfg, dict):
        return
    codex = (cfg.get("models") or {}).get("codex") or {}
    if codex.get("enabled") is not True:
        return

    root_real = os.path.realpath(root)
    target = file_path if os.path.isabs(file_path) else os.path.join(root, file_path)
    rel = os.path.relpath(os.path.realpath(target), root_real).replace(os.sep, "/")
    if rel == ".." or rel.startswith("../"):
        return

    routing = cfg.get("codexRouting") or {}
    if not matches(routing.get("code") or DEFAULT_CODE, rel):
        return
    if matches(routing.get("exclude") or DEFAULT_EXCLUDE, rel):
        return
    is_backend = matches(routing.get("backend") or DEFAULT_BACKEND, rel)

    msg = MESSAGES.get(cfg.get("language"), MESSAGES["en"])
    fallback = " → ".join((cfg.get("models") or {}).get("claudeFallback") or []) or "Claude"
    lines = [
        msg["head"],
        msg["target"].format(path=rel),
        msg["route"].format(model=codex.get("model", "?"), effort=codex.get("effort", "?")),
    ]
    if is_backend:
        lines.append(msg["backend"])
    lines.append(msg["allow"].format(fallback=fallback))

    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n".join(lines)}},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
