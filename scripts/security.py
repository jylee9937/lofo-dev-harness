#!/usr/bin/env python3
"""Security gate helpers for lofo-dev-harness.

Usage:
  python3 security.py scope   [--base REF] [--json]
  python3 security.py scan    [--base REF | --all] [--json]
  python3 security.py audit   [--json]
  python3 security.py prompt  --slug NAME [--base REF] [--reviewer codex|claude]
  python3 security.py verdict FILE

Exit codes:
  scope    0 gate not required, 1 gate required
  scan     0 nothing blocking, 1 block or high findings
  audit    0 below the threshold, 1 at or above it, 3 the audit could not run
  prompt   0 review folder written
  verdict  0 GO, 1 NO-GO, 2 no verdict line
  any      2 usage or input error

`scan` is a set of heuristics. It points reviewers at likely problems; it does not prove safety.
A finding that was reviewed and accepted is silenced with a comment in the same file:
  // security-ok: <rule-id> <reason>
Standard library only, Python 3.8+.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE = PLUGIN_ROOT / "templates" / "security" / "review-prompt.md"

SEVERITY_ORDER = {"block": 0, "high": 1, "review": 2}
AUDIT_LEVELS = ("low", "moderate", "high", "critical")
GATE_CATEGORIES = ("auth", "authz", "money", "secrets", "personal-data", "upload", "webhook", "migrations", "custom")

CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rb", ".php", ".java", ".kt",
            ".sql", ".vue", ".svelte", ".swift", ".rs", ".cs"}
SKIP_PATH = re.compile(r"(^|/)(node_modules|\.next|dist|build|coverage|vendor|\.git|\.harness/local)/")
LOCKFILE = re.compile(r"(^|/)(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb?)$")
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|e2e|spec|fixtures)/|\.(test|spec)\.[a-z]+$")
ENV_FILE = re.compile(r"(^|/)\.env(\.[^/]*)?$")
ENV_EXAMPLE = re.compile(r"\.(example|sample|template|dist)$")

CATEGORY_PATHS = {
    "auth": r"(^|/)(auth|login|logout|sign-?in|sign-?up|session|password|oauth|callback)(/|\.|-|_)|(^|/)(middleware|proxy)\.(ts|js)$",
    "authz": r"(^|/)(polic(y|ies)|rls|roles?|permissions?|admin)(/|\.|-|_)",
    "money": r"(payment|checkout|billing|donat|invoice|refund|subscription|stripe|toss|portone|iamport|offering)",
    "secrets": r"(^|/)\.env|secret|credential",
    "personal-data": r"(profile|member|personal|privacy)",
    "upload": r"(upload|attachment|avatar)",
    "webhook": r"webhook",
    "migrations": r"(^|/)(supabase/migrations|migrations|prisma)/|(^|/)(firestore|storage|database)\.rules(\.json)?$",
    "dependencies": r"(^|/)(package\.json|pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb?)$",
}
CATEGORY_CONTENT = {
    "auth": r"signInWith|signUp\(|signOut\(|getSession\(|verifyPassword|bcrypt|argon2|jsonwebtoken|jwt\.sign|createSession",
    "authz": r"(?i)create policy|alter policy|row level security|security definer|\bgrant\s|\brevoke\s|service_role|is_admin|has_role|requireAdmin|requireRole",
    "money": r"(?i)\bstripe\b|payment|checkout\.session|\brefund|\bcurrency\b|donation|헌금|결제|환불",
    "secrets": r"SERVICE_ROLE|_SECRET|PRIVATE_KEY|API_KEY|ACCESS_TOKEN",
    "personal-data": r"(?i)\bphone\b|birth|resident_?no|주민|연락처|전화번호|계좌|account_number|bank_account",
    "upload": r"(?i)multipart/form-data|instanceof File|as File\b|\.upload\(|multer|busboy|formidable|PutObjectCommand",
    "webhook": r"(?i)webhook",
}

SECRET_PATTERNS = re.compile(
    r"AKIA[0-9A-Z]{16}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
    r"|\b(?:sk|rk)_live_[0-9A-Za-z]{16,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{30,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{40,}"
    r"|\bxox[abprs]-[A-Za-z0-9-]{10,}"
    r"|\bAIza[0-9A-Za-z_\-]{35}"
)
JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.(eyJ[A-Za-z0-9_-]{8,})\.[A-Za-z0-9_-]{8,}")
HARDCODED = re.compile(
    r"(?i)\b(secret|password|passwd|api[_-]?key|access[_-]?token|private[_-]?key|client[_-]?secret|auth[_-]?token)\b"
    r"[\"']?\s*[:=]\s*[\"']([^\"'\s]{12,})[\"']"
)
PLACEHOLDER = re.compile(r"(?i)your|example|changeme|placeholder|dummy|sample|test|xxx|\*\*\*|<|\$\{|process\.env|todo|redacted")

# security-ok: xss-sink these are detection patterns, not HTML sinks
LINE_RULES = [
    ("public-env-secret", "high", "any",
     re.compile(r"\b(?:NEXT_PUBLIC|VITE|EXPO_PUBLIC|PUBLIC|REACT_APP)_[A-Z0-9_]*(?:SECRET|SERVICE_ROLE|PRIVATE|PASSWORD)[A-Z0-9_]*")),
    ("sql-interpolation", "high", "code",
     re.compile(r"\b(?:query|execute|raw|unsafe|queryRawUnsafe|executeRawUnsafe|exec)\s*\(\s*`[^`]*\$\{")),
    ("sql-concat", "high", "code",
     re.compile(r"(?i)[\"'`]\s*(?:select\s|insert\s+into|update\s+\w+\s+set|delete\s+from)[^\"'`]*[\"'`]\s*\+")),
    ("postgrest-filter", "high", "code",
     re.compile(r"\.(?:or|filter|not|textSearch)\(\s*`[^`]*\$\{")),
    ("sql-dynamic", "high", "sql",
     re.compile(r"(?i)\bexecute\s+(?:'[^']*'\s*\|\||format\([^)]*%s)")),
    ("password-log", "high", "code",
     re.compile(r"(?i)console\.(?:log|info|debug|warn|error)\([^)]*\bpassword\b|logger\.\w+\([^)]*\bpassword\b")),
    ("xss-sink", "review", "code",
     re.compile(r"dangerouslySetInnerHTML|\.innerHTML\s*=|\bv-html\b|\beval\s*\(|new Function\s*\(")),
    ("cors-wildcard", "review", "code",
     re.compile(r"(?i)access-control-allow-origin['\"]?\s*[:,=]\s*['\"]\*['\"]|\borigin\s*:\s*['\"]\*['\"]")),
    ("open-redirect", "review", "code",
     re.compile(r"redirect\(\s*(?:searchParams|params|req|request|url|query)\s*[\.\[]"
                r"|redirect\([^)]*\.get\(\s*['\"](?:next|redirect|returnTo|return_to|callbackUrl|url)['\"]")),
]
WEAK_HASH = re.compile(r"(?i)createHash\(\s*['\"](?:md5|sha1)['\"]|\bmd5\s*\(|\bsha1\s*\(")

USE_CLIENT = re.compile(r"^\s*['\"]use client['\"]", re.M)
USE_SERVER = re.compile(r"^\s*['\"]use server['\"]", re.M)
SERVER_ENTRY_PATH = re.compile(r"(^|/)app/(.+/)?route\.(ts|js)$|(^|/)pages/api/|(^|/)functions/src/")
CLIENT_SECRET = re.compile(r"SERVICE_ROLE|service_role|createAdminClient|supabaseAdmin|SECRET_KEY|PRIVATE_KEY"
                           r"|process\.env\.(?!NEXT_PUBLIC_)[A-Z0-9_]*(?:SECRET|KEY|TOKEN)")
AUTH_SIGNALS = re.compile(r"getUser\(|getClaims\(|\bauth\(\)|getSession\(|getServerSession|currentUser|requireUser"
                          r"|requireAuth|requireAdmin|requireRole|assertAdmin|assertRole|verifyIdToken|verifyToken"
                          r"|isAdmin|checkPermission|withAuth|authorize\(")
READS_INPUT = re.compile(r"formData|request\.json\(|req\.body|\.json\(\)|searchParams|params\b|req\.query")
VALIDATION_SIGNALS = re.compile(r"\bzod\b|\bz\.(?:object|string|number|enum|array)|safeParse|\.parse\(|\byup\b|valibot"
                                r"|\bjoi\b|\bajv\b|validate")
UPLOAD_SIGNALS = re.compile(r"instanceof File|as File\b|File\[\]|\.upload\(|multer|busboy|formidable|multipart/form-data"
                            r"|uploadFile|putObject|PutObjectCommand")
SIZE_SIGNALS = re.compile(r"\.size\b|maxSize|max_size|maxFileSize|fileSizeLimit|file_size_limit|MAX_[A-Z_]*SIZE"
                          r"|limits\s*:|bodySizeLimit|content-length", re.I)
TYPE_SIGNALS = re.compile(r"\.type\b|mimetype|mimeType|allowedMimeTypes|allowed_mime_types|file-type|fileTypeFrom"
                          r"|magic|\baccept\b|contentType|ALLOWED_[A-Z_]*TYPES")
LOGIN_SIGNALS = re.compile(r"signInWithPassword|signInWithOtp|verifyOtp|resetPasswordForEmail|bcrypt\.compare"
                           r"|argon2\.verify|verifyPassword|['\"]/login['\"]|\bsignIn\(")
RATE_SIGNALS = re.compile(r"rateLimit|ratelimit|RateLimit|limiter|captcha|turnstile|hcaptcha|recaptcha|lockout"
                          r"|attempt|tooMany|\b429\b|throttle")
SIGNATURE_SIGNALS = re.compile(r"constructEvent|verifySignature|verifyWebhook|signature|createHmac|\bhmac\b"
                               r"|timingSafeEqual|svix", re.I)
CREATE_TABLE = re.compile(r"(?i)create\s+table\s+(?:if\s+not\s+exists\s+)?(?:(\w+)\.)?\"?(\w+)\"?")
GRANT_ANON = re.compile(r"(?is)grant\s+(?:all|insert|update|delete|truncate)\b[^;]*\bto\s+[^;]*\banon\b")
PUBLIC_BUCKET = re.compile(r"(?is)insert\s+into\s+storage\.buckets[^;]*\btrue\b")

MESSAGES = {
    "ko": {
        "secret-key": "비밀 키로 보이는 값이 들어 있다. 지우고, 이미 커밋했다면 키를 폐기·교체한다.",
        "secret-service-role": "service_role 키(RLS를 우회하는 관리자 키)가 들어 있다. 지우고 키를 교체한다.",
        "secret-hardcoded": "비밀값이 코드에 직접 적혀 있는 것 같다({name}). 환경 변수나 비밀 관리 서비스로 옮긴다.",
        "secret-env-file": ".env 파일이 git에 올라가 있다. git에서 빼고(.gitignore), 들어 있던 값은 교체한다.",
        "public-env-secret": "공개 접두사(NEXT_PUBLIC_ 등) 환경 변수에 비밀값 이름이 붙어 있다. 공개 변수는 브라우저에 그대로 노출된다.",
        "client-secret": "클라이언트 컴포넌트에서 관리자 키나 비밀 환경 변수를 쓴다. 서버 코드로 옮긴다.",
        "sql-interpolation": "SQL을 문자열 보간으로 만든다(SQL 인젝션). 매개변수 바인딩이나 쿼리 빌더를 쓴다.",
        "sql-concat": "SQL을 문자열 더하기로 만든다(SQL 인젝션). 매개변수 바인딩을 쓴다.",
        "postgrest-filter": "Supabase 필터 문자열을 입력값 보간으로 만든다(필터 인젝션). .eq() 같은 메서드나 값 이스케이프를 쓴다.",
        "sql-dynamic": "plpgsql에서 동적 SQL을 문자열로 이어 붙인다. format()의 %I(식별자), %L(값)이나 USING을 쓴다.",
        "weak-hash": "비밀번호에 md5·sha1 같은 빠른 해시를 쓴다. 인증 서비스에 맡기거나 argon2id·bcrypt·scrypt를 쓴다.",
        "weak-hash-other": "md5·sha1을 쓴다. 보안 용도(토큰, 서명, 비밀번호)라면 더 강한 방식으로 바꾼다.",
        "password-log": "비밀번호를 로그에 남길 수 있다. 로그에서 빼거나 가린다.",
        "xss-sink": "HTML을 그대로 넣는 코드다(XSS). 사용자 입력이 들어가지 않는지 확인하고, 필요하면 정화(sanitize)한다.",
        "cors-wildcard": "CORS를 모든 출처(*)에 연다. 인증이 필요한 API라면 허용 출처를 좁힌다.",
        "open-redirect": "요청 값으로 리다이렉트한다(열린 리다이렉트). 같은 사이트 경로나 허용 목록만 받는다.",
        "authz-missing": "서버 진입점(서버 액션·라우트)에 인증·권한 확인이 보이지 않는다. 공개가 의도인지 확인하고, 아니면 맨 앞에서 사용자와 권한을 확인한다.",
        "input-validation": "서버 진입점이 입력을 받는데 서버 쪽 검증(스키마)이 보이지 않는다. zod 같은 스키마로 서버에서 검사한다.",
        "upload-unchecked": "파일 업로드에 크기 제한도 종류 제한도 보이지 않는다. 서버(또는 버킷 설정)에서 크기와 허용 형식을 제한한다.",
        "upload-partial": "파일 업로드에 {missing} 제한이 보이지 않는다. 서버(또는 버킷 설정)에서 제한한다.",
        "upload-client": "브라우저에서 저장소로 바로 올린다. 버킷 설정(file_size_limit, allowed_mime_types)과 저장소 정책으로 크기·형식·권한을 제한한다.",
        "bruteforce": "로그인·인증 코드에 시도 횟수 제한이나 CAPTCHA가 보이지 않는다. 인증 서비스의 제한 설정을 확인하거나 실패 횟수 제한(예: 5회 후 잠시 잠금)을 둔다.",
        "webhook-unsigned": "webhook이 서명을 검증하지 않는 것 같다. 보낸 곳의 서명을 검증하고 재전송 공격(시간 창)을 막는다.",
        "rls-missing": "public 테이블을 만들면서 같은 마이그레이션에서 RLS를 켜지 않았다: {table}",
        "definer-search-path": "security definer 함수에 search_path 고정(set search_path)이 없다. 권한 상승 경로가 될 수 있다.",
        "grant-anon": "익명(anon) 역할에 쓰기 권한을 준다. 정말 필요한지, RLS로 막히는지 확인한다.",
        "public-bucket": "공개 저장소 버킷을 만든다. 올라간 파일이 누구에게나 보여도 되는지 확인한다.",
    },
    "en": {
        "secret-key": "Looks like a secret key. Remove it, and revoke and rotate it if it was ever committed.",
        "secret-service-role": "Contains a service_role key (an admin key that bypasses RLS). Remove it and rotate the key.",
        "secret-hardcoded": "'{name}' seems to hold a hardcoded secret. Move it to an environment variable or a secret manager.",
        "secret-env-file": "An .env file is tracked by git. Untrack it (.gitignore) and rotate the values it held.",
        "public-env-secret": "A public-prefixed env var (NEXT_PUBLIC_ etc.) has a secret-like name. Public vars ship to the browser as-is.",
        "client-secret": "A client component uses an admin key or a secret env var. Move this to server code.",
        "sql-interpolation": "SQL built with string interpolation (SQL injection). Use bound parameters or a query builder.",
        "sql-concat": "SQL built with string concatenation (SQL injection). Use bound parameters.",
        "postgrest-filter": "Supabase filter string built from interpolated input (filter injection). Use methods like .eq() or escape values.",
        "sql-dynamic": "Dynamic SQL concatenated as a string in plpgsql. Use format() with %I (identifiers) and %L (values), or USING.",
        "weak-hash": "A fast hash (md5, sha1) is used for passwords. Leave it to the auth provider or use argon2id, bcrypt or scrypt.",
        "weak-hash-other": "md5 or sha1 in use. For security purposes (tokens, signatures, passwords), switch to a stronger scheme.",
        "password-log": "A password may end up in logs. Remove or mask it.",
        "xss-sink": "Raw HTML injection point (XSS). Make sure user input never reaches it, or sanitize it.",
        "cors-wildcard": "CORS open to every origin (*). For authenticated APIs, narrow the allowed origins.",
        "open-redirect": "Redirects to a request-supplied value (open redirect). Accept same-site paths or an allowlist only.",
        "authz-missing": "Server entry point (server action or route) with no visible authentication or authorization check. Confirm it is meant to be public; otherwise check the user and role first.",
        "input-validation": "Server entry point reads input with no visible server-side schema validation. Validate on the server, for example with zod.",
        "upload-unchecked": "File upload with no visible size or type limit. Limit size and allowed formats on the server (or in bucket settings).",
        "upload-partial": "File upload with no visible {missing} limit. Enforce it on the server (or in bucket settings).",
        "upload-client": "Uploads go straight from the browser to storage. Limit size, type and access with bucket settings (file_size_limit, allowed_mime_types) and storage policies.",
        "bruteforce": "Login or verification code with no visible attempt limit or CAPTCHA. Check the auth provider's rate limits, or add a failure limit (for example, a short lockout after 5 tries).",
        "webhook-unsigned": "The webhook does not seem to verify signatures. Verify the sender's signature and reject replays (time window).",
        "rls-missing": "Public table '{table}' is created without enabling RLS in the same migration.",
        "definer-search-path": "A security definer function without a fixed search_path (set search_path). This can become a privilege escalation path.",
        "grant-anon": "Grants write access to the anonymous (anon) role. Confirm it is needed and that RLS still blocks misuse.",
        "public-bucket": "Creates a public storage bucket. Confirm every uploaded file may be visible to anyone.",
    },
}

SUMMARY = {
    "ko": {
        "scope_head": "보안 관문: {state}",
        "required": "필요",
        "not_required": "필요 없음",
        "files": "바뀐 파일 {count}개 (기준 {base})",
        "deps": "의존성이 바뀌었다: `security.py audit`를 돌린다.",
        "scan_head": "보안 검사 ({mode}, 파일 {count}개)",
        "mode_all": "전체",
        "mode_diff": "{base} 대비 변경",
        "none": "찾은 것 없음.",
        "suppressed": "security-ok로 넘긴 것 {count}건",
        "blocking": "결과: 막힘 (block/high {count}건). 고치거나, 검토 후 security-ok 주석에 이유를 남긴다.",
        "clear": "결과: block/high 없음. review 항목은 검토자가 확인한다.",
        "audit_head": "의존성 감사 ({cmd}): {counts}",
        "audit_fail": "의존성 감사를 실행하지 못했다 ({cmd}): {reason}",
        "audit_block": "결과: {level} 이상 {count}건. 업데이트하거나 영향이 없다는 근거를 남긴다.",
        "audit_ok": "결과: {level} 이상 없음.",
    },
    "en": {
        "scope_head": "Security gate: {state}",
        "required": "required",
        "not_required": "not required",
        "files": "{count} changed files (base {base})",
        "deps": "Dependencies changed: run `security.py audit`.",
        "scan_head": "Security scan ({mode}, {count} files)",
        "mode_all": "whole repository",
        "mode_diff": "changes since {base}",
        "none": "Nothing found.",
        "suppressed": "{count} silenced with security-ok",
        "blocking": "Result: blocked ({count} block/high). Fix them, or after review leave a reason in a security-ok comment.",
        "clear": "Result: no block/high findings. Reviewers check the review items.",
        "audit_head": "Dependency audit ({cmd}): {counts}",
        "audit_fail": "Dependency audit could not run ({cmd}): {reason}",
        "audit_block": "Result: {count} at {level} or above. Update them, or record why they do not apply.",
        "audit_ok": "Result: nothing at {level} or above.",
    },
}


class GateError(Exception):
    pass


# ---------------------------------------------------------------------- git

def git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GateError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def project_root() -> Path:
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise GateError("not inside a git repository")
    return Path(proc.stdout.strip())


def default_base(root: Path) -> str | None:
    ref = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if ref:
        return ref
    for candidate in ("main", "master"):
        if git(root, "rev-parse", "--verify", "--quiet", candidate, check=False).strip():
            return candidate
    return None


def changed_lines(root: Path, base: str | None) -> tuple[str, dict[str, list[tuple[int, str]]]]:
    """Added lines per file since the merge base, including uncommitted and untracked files."""
    files: dict[str, list[tuple[int, str]]] = {}
    whole: set[str] = set()  # files whose every line counts as added
    label = base or "(empty tree)"
    if base:
        merge_base = git(root, "merge-base", base, "HEAD", check=False).strip()
        if not merge_base:
            raise GateError(f"no merge base between {base} and HEAD")
        diff = git(root, "diff", "--unified=0", "--no-color", "--no-ext-diff", merge_base)
        current = None
        line_no = 0
        for raw in diff.splitlines():
            if raw.startswith("+++ "):
                path = raw[4:]
                current = None if path == "/dev/null" else path[2:] if path.startswith("b/") else path
                if current is not None:
                    files.setdefault(current, [])
            elif raw.startswith("@@"):
                match = re.search(r"\+(\d+)", raw)
                line_no = int(match.group(1)) if match else 0
            elif raw.startswith("+") and current is not None:
                files[current].append((line_no, raw[1:]))
                line_no += 1
        for path in git(root, "diff", "--name-only", merge_base).splitlines():
            files.setdefault(path, [])
    else:
        for path in git(root, "ls-files").splitlines():
            files[path] = []
            whole.add(path)
    for path in git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        files[path] = []
        whole.add(path)
    for path in whole:
        text = read_text(root / path)
        if text is not None:
            files[path] = list(enumerate(text.splitlines(), start=1))
    return label, files


def read_text(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > 1_000_000:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


# ------------------------------------------------------------------- config

def load_config(root: Path) -> dict:
    path = root / ".harness" / "config.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = {}
    security = cfg.get("security") or {}
    return {
        "language": cfg.get("language") if cfg.get("language") in ("ko", "en") else "en",
        "packageManager": (cfg.get("stack") or {}).get("packageManager"),
        "codex": bool(((cfg.get("models") or {}).get("codex") or {}).get("enabled")),
        "reviewsDir": security.get("reviewsDir", "docs/security/reviews"),
        "decisions": security.get("decisions", "docs/security/decisions.md"),
        "audit": security.get("audit"),
        "auditLevel": security.get("auditLevel", "high"),
        "sensitive": security.get("sensitive") or [],
        "substitute": security.get("substitute", "hold"),
    }


# -------------------------------------------------------------------- scope

def classify(path: str, lines: list[tuple[int, str]], extra: list[str]) -> list[str]:
    cats = []
    added = "\n".join(text for _, text in lines)
    for cat, pattern in CATEGORY_PATHS.items():
        if re.search(pattern, path, re.I):
            cats.append(cat)
    if not LOCKFILE.search(path):
        for cat, pattern in CATEGORY_CONTENT.items():
            if cat not in cats and re.search(pattern, added):
                cats.append(cat)
    for pattern in extra:
        try:
            if re.search(pattern, path) and "custom" not in cats:
                cats.append("custom")
        except re.error:
            continue
    return cats


def scope(root: Path, base: str | None, cfg: dict) -> dict:
    label, files = changed_lines(root, base)
    by_category: dict[str, list[str]] = {}
    for path, lines in sorted(files.items()):
        if SKIP_PATH.search(path):
            continue
        for cat in classify(path, lines, cfg["sensitive"]):
            by_category.setdefault(cat, []).append(path)
    gate = sorted(c for c in by_category if c in GATE_CATEGORIES)
    return {
        "base": label,
        "files": sorted(p for p in files if not SKIP_PATH.search(p)),
        "categories": by_category,
        "gateCategories": gate,
        "required": bool(gate),
        "dependenciesChanged": "dependencies" in by_category,
    }


# --------------------------------------------------------------------- scan

ENV_ASSIGNMENT = re.compile(r"(?i)\b([A-Z0-9_]*(?:SECRET|KEY|TOKEN|PASSWORD|PASSWD)[A-Z0-9_]*)\s*=\s*[^\s'\"]+")


def redact(text: str) -> str:
    """Hide secret values in snippets. Findings are committed with review records."""
    text = SECRET_PATTERNS.sub("[REDACTED]", text)
    text = JWT.sub("[REDACTED-JWT]", text)
    text = HARDCODED.sub(lambda m: m.group(0).replace(m.group(2), "[REDACTED]"), text)
    return ENV_ASSIGNMENT.sub(r"\1=[REDACTED]", text)


def jwt_role(token_payload: str) -> str | None:
    try:
        padded = token_payload + "=" * (-len(token_payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded)).get("role")
    except Exception:
        return None


def scan(root: Path, base: str | None, everything: bool, lang: str) -> dict:
    label, files = changed_lines(root, None if everything else base)
    msg = MESSAGES[lang]
    findings: list[dict] = []
    suppressed: list[dict] = []

    def add(rule: str, severity: str, path: str, line: int, text: str, **fmt) -> None:
        findings.append({"rule": rule, "severity": severity, "file": path, "line": line,
                         "message": msg[rule].format(**fmt), "snippet": redact(text.strip())[:160]})

    tracked = set(git(root, "ls-files").splitlines())
    scanned = 0
    for path, lines in sorted(files.items()):
        if SKIP_PATH.search(path) or LOCKFILE.search(path):
            continue
        full = read_text(root / path)
        if full is None:
            continue
        scanned += 1
        ext = Path(path).suffix.lower()
        is_code = ext in CODE_EXT
        is_sql = ext == ".sql"
        is_test = bool(TEST_PATH.search(path))

        if ENV_FILE.search(path) and not ENV_EXAMPLE.search(path) and path in tracked:
            add("secret-env-file", "block", path, 1, path)

        for line_no, text in lines:
            if SECRET_PATTERNS.search(text):
                add("secret-key", "block", path, line_no, text)
            for token in JWT.finditer(text):
                if jwt_role(token.group(1)) == "service_role":
                    add("secret-service-role", "block", path, line_no, text)
            if is_test:
                continue  # test code is not shipped: only the secret checks above apply
            hard = HARDCODED.search(text)
            if hard and not PLACEHOLDER.search(hard.group(2)):
                add("secret-hardcoded", "high", path, line_no, text, name=hard.group(1))
            for rule, severity, scope_kind, pattern in LINE_RULES:
                if scope_kind == "code" and not is_code:
                    continue
                if scope_kind == "sql" and not is_sql:
                    continue
                if pattern.search(text):
                    add(rule, severity, path, line_no, text)
            if is_code and WEAK_HASH.search(text):
                if re.search(r"(?i)passw", text):
                    add("weak-hash", "high", path, line_no, text)
                else:
                    add("weak-hash-other", "review", path, line_no, text)

        if not is_code or is_test:
            continue
        first = lambda pattern: next((n for n, t in enumerate(full.splitlines(), 1) if pattern.search(t)), 1)  # noqa: E731
        client = bool(USE_CLIENT.search(full))
        server_entry = bool(USE_SERVER.search(full)) or bool(SERVER_ENTRY_PATH.search(path))

        if client and CLIENT_SECRET.search(full):
            add("client-secret", "high", path, first(CLIENT_SECRET), "")
        if server_entry and not client:
            if not AUTH_SIGNALS.search(full):
                add("authz-missing", "review", path, 1, "")
            if READS_INPUT.search(full) and not VALIDATION_SIGNALS.search(full):
                add("input-validation", "review", path, first(READS_INPUT), "")
        if UPLOAD_SIGNALS.search(full):
            line = first(UPLOAD_SIGNALS)
            if client:
                add("upload-client", "review", path, line, "")
            else:
                has_size, has_type = bool(SIZE_SIGNALS.search(full)), bool(TYPE_SIGNALS.search(full))
                if not has_size and not has_type:
                    add("upload-unchecked", "high", path, line, "")
                elif not has_size or not has_type:
                    missing = ("크기" if lang == "ko" else "size") if not has_size else ("형식" if lang == "ko" else "type")
                    add("upload-partial", "review", path, line, "", missing=missing)
        if LOGIN_SIGNALS.search(full) and not RATE_SIGNALS.search(full):
            add("bruteforce", "review", path, first(LOGIN_SIGNALS), "")
        if (re.search(r"webhook", path, re.I) or (server_entry and re.search(r"(?i)webhook", full))) \
                and not SIGNATURE_SIGNALS.search(full):
            add("webhook-unsigned", "high", path, 1, "")
        if is_sql:
            lower = full.lower()
            for match in CREATE_TABLE.finditer(full):
                schema, table = (match.group(1) or "public").lower(), match.group(2).lower()
                if schema != "public":
                    continue
                enable = re.search(rf"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?\"?{re.escape(table)}\"?"
                                   rf"\s+enable\s+row\s+level\s+security", lower)
                if not enable:
                    line = full[: match.start()].count("\n") + 1
                    add("rls-missing", "high", path, line, match.group(0), table=table)
            if lower.count("security definer") > lower.count("search_path"):
                add("definer-search-path", "high", path, first(re.compile(r"(?i)security\s+definer")), "")
            for match in GRANT_ANON.finditer(full):
                add("grant-anon", "high", path, full[: match.start()].count("\n") + 1, match.group(0))
            if PUBLIC_BUCKET.search(full):
                add("public-bucket", "review", path, first(re.compile(r"(?i)storage\.buckets")), "")

    kept = []
    for finding in findings:
        text = read_text(root / finding["file"]) or ""
        marker = re.search(rf"security-ok:\s*{re.escape(finding['rule'])}\b(.*)", text)
        if marker:
            suppressed.append({**finding, "reason": marker.group(1).strip()})
        else:
            kept.append(finding)
    kept.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["file"], f["line"]))
    return {
        "mode": "all" if everything else "diff",
        "base": label,
        "scanned": scanned,
        "findings": kept,
        "suppressed": suppressed,
        "blocking": sum(1 for f in kept if f["severity"] in ("block", "high")),
    }


# -------------------------------------------------------------------- audit

def audit_command(root: Path, cfg: dict) -> list[str]:
    if cfg["audit"]:
        return shlex.split(cfg["audit"])
    pm = cfg["packageManager"]
    if not pm:
        for name, lock in (("pnpm", "pnpm-lock.yaml"), ("npm", "package-lock.json"), ("yarn", "yarn.lock"),
                           ("bun", "bun.lock"), ("bun", "bun.lockb")):
            if (root / lock).exists():
                pm = name
                break
    return {
        "pnpm": ["pnpm", "audit", "--prod", "--json"],
        "npm": ["npm", "audit", "--omit=dev", "--json"],
        "yarn": ["yarn", "npm", "audit", "--environment", "production", "--json"],
        "bun": ["bun", "audit", "--json"],
    }.get(pm or "npm", ["npm", "audit", "--omit=dev", "--json"])


def parse_audit(output: str) -> dict | None:
    """Read npm or pnpm audit JSON. Returns None when the output is not a known format."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None
    counts = (data.get("metadata") or {}).get("vulnerabilities")
    if not isinstance(counts, dict):
        return None
    advisories = []
    for adv in (data.get("advisories") or {}).values():
        advisories.append({"package": adv.get("module_name"), "severity": adv.get("severity"),
                           "title": adv.get("title"), "url": adv.get("url"),
                           "fix": adv.get("patched_versions")})
    for name, vuln in (data.get("vulnerabilities") or {}).items():
        via = next((v for v in vuln.get("via") or [] if isinstance(v, dict)), {})
        fix = vuln.get("fixAvailable")
        advisories.append({"package": name, "severity": vuln.get("severity"), "title": via.get("title"),
                           "url": via.get("url"),
                           "fix": fix.get("version") if isinstance(fix, dict) else bool(fix)})
    return {"counts": {k: int(counts.get(k, 0)) for k in ("info",) + AUDIT_LEVELS}, "advisories": advisories}


def at_or_above(counts: dict, level: str) -> int:
    return sum(counts.get(name, 0) for name in AUDIT_LEVELS[AUDIT_LEVELS.index(level):])


def run_audit(root: Path, cfg: dict) -> dict:
    cmd = audit_command(root, cfg)
    level = cfg["auditLevel"] if cfg["auditLevel"] in AUDIT_LEVELS else "high"
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": " ".join(cmd), "ran": False, "reason": str(exc), "level": level}
    parsed = parse_audit(proc.stdout)
    if parsed is None:
        if proc.returncode == 0:
            return {"command": " ".join(cmd), "ran": True, "level": level, "counts": {}, "advisories": [],
                    "atOrAbove": 0}
        reason = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["unknown error"]
        return {"command": " ".join(cmd), "ran": False, "reason": reason[0][:300], "level": level}
    return {"command": " ".join(cmd), "ran": True, "level": level, **parsed,
            "atOrAbove": at_or_above(parsed["counts"], level)}


# ------------------------------------------------------------------- prompt

def write_prompt(root: Path, cfg: dict, slug: str, base: str | None, reviewer: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise GateError("slug: lowercase letters, digits and '-' only")
    if not PROMPT_TEMPLATE.is_file():
        raise GateError(f"missing template: {PROMPT_TEMPLATE}")
    sc = scope(root, base, cfg)
    sn = scan(root, base, False, cfg["language"])
    folder = (root / cfg["reviewsDir"] / f"{dt.date.today().isoformat()}-{slug}").resolve()
    if root.resolve() not in folder.parents:
        raise GateError("reviewsDir must stay inside the project")
    folder.mkdir(parents=True, exist_ok=True)

    risky = []
    for finding in sn["findings"]:
        if finding["file"] not in risky:
            risky.append(finding["file"])
    for cat in ("migrations", "authz", "auth", "money", "secrets", "upload", "webhook", "personal-data", "custom"):
        for path in sc["categories"].get(cat, []):
            if path not in risky:
                risky.append(path)
    rest = [p for p in sc["files"] if p not in risky]
    file_lines = [f"- `{p}`" for p in risky] + [f"- `{p}` (other change)" for p in rest]
    scan_lines = [f"- [{f['severity']}] `{f['rule']}` {f['file']}:{f['line']} — {f['message']}" for f in sn["findings"]]
    decisions = root / cfg["decisions"]
    head = git(root, "rev-parse", "--short", "HEAD").strip()
    dirty = bool(git(root, "status", "--porcelain").strip())
    values = {
        "project": root.name,
        "base": sc["base"],
        "head": head + (" plus uncommitted changes" if dirty else ""),
        "categories": ", ".join(sc["gateCategories"]) or "none detected (review requested anyway)",
        "files": "\n".join(file_lines) or "- (no changed files)",
        "scan": "\n".join(scan_lines) or "- nothing flagged",
        "decisions": f"see `{cfg['decisions']}`" if decisions.is_file() else "none recorded",
        "language": "Korean" if cfg["language"] == "ko" else "English",
        "verdict": "판정" if cfg["language"] == "ko" else "VERDICT",
        "reviewer_note": REVIEWER_NOTES[reviewer],
    }
    text = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    (folder / "prompt.md").write_text(text, encoding="utf-8")
    (folder / "scan.json").write_text(json.dumps({"scope": sc, "scan": sn}, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


REVIEWER_NOTES = {
    "codex": "",
    "claude": (
        "You are a substitute for the usual Codex review, so your verdict is provisional. Earlier substitute reviews "
        "missed real blockers by trusting what the UI shows. Look past visible text: URL attributes, slugs, URL and "
        "JSON columns, query strings, direct database API writes that skip the UI, other entry points (server actions, "
        "route handlers, RPC functions, storage policies), and race conditions between check and use."
    ),
}


# ------------------------------------------------------------------ verdict

VERDICT = re.compile(r"^[\s>*_`#-]*(?:판정|VERDICT)\s*[:：]\s*[*_`]*\s*(NO-GO|GO)\b", re.I | re.M)


def read_verdict(text: str) -> str | None:
    matches = VERDICT.findall(text)
    return matches[-1].upper() if matches else None


# ---------------------------------------------------------------------- cli

def print_scope(sc: dict, lang: str) -> None:
    s = SUMMARY[lang]
    print(s["scope_head"].format(state=s["required"] if sc["required"] else s["not_required"])
          + (f" ({', '.join(sc['gateCategories'])})" if sc["gateCategories"] else ""))
    print(s["files"].format(count=len(sc["files"]), base=sc["base"]))
    for cat, paths in sorted(sc["categories"].items()):
        shown = ", ".join(paths[:6]) + (f" … +{len(paths) - 6}" if len(paths) > 6 else "")
        print(f"  {cat}: {shown}")
    if sc["dependenciesChanged"]:
        print(s["deps"])


def print_scan(sn: dict, lang: str) -> None:
    s = SUMMARY[lang]
    mode = s["mode_all"] if sn["mode"] == "all" else s["mode_diff"].format(base=sn["base"])
    print(s["scan_head"].format(mode=mode, count=sn["scanned"]))
    if not sn["findings"]:
        print(s["none"])
    for f in sn["findings"]:
        print(f"  [{f['severity'].upper():<6}] {f['rule']:<20} {f['file']}:{f['line']}  {f['message']}")
    if sn["suppressed"]:
        print(s["suppressed"].format(count=len(sn["suppressed"])))
    print(s["blocking"].format(count=sn["blocking"]) if sn["blocking"] else s["clear"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Security gate helpers for lofo-dev-harness.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_scope = sub.add_parser("scope", help="classify changed files and decide whether the gate applies")
    p_scope.add_argument("--base")
    p_scope.add_argument("--json", action="store_true")
    p_scan = sub.add_parser("scan", help="heuristic checks on changed (or all) files")
    p_scan.add_argument("--base")
    p_scan.add_argument("--all", action="store_true", help="scan every tracked and untracked file")
    p_scan.add_argument("--json", action="store_true")
    p_audit = sub.add_parser("audit", help="dependency vulnerability audit")
    p_audit.add_argument("--json", action="store_true")
    p_prompt = sub.add_parser("prompt", help="write a review folder with prompt.md and scan.json")
    p_prompt.add_argument("--slug", required=True)
    p_prompt.add_argument("--base")
    p_prompt.add_argument("--reviewer", choices=("codex", "claude"), default="codex")
    p_verdict = sub.add_parser("verdict", help="read the verdict line of a review result")
    p_verdict.add_argument("file")
    args = parser.parse_args(argv)

    try:
        if args.command == "verdict":
            try:
                text = Path(args.file).read_text(encoding="utf-8")
            except OSError as exc:
                raise GateError(str(exc)) from None
            verdict = read_verdict(text)
            print(verdict or "no verdict line")
            return {"GO": 0, "NO-GO": 1}.get(verdict or "", 2)

        root = project_root()
        cfg = load_config(root)
        lang = cfg["language"]
        base = getattr(args, "base", None) or default_base(root)

        if args.command == "scope":
            sc = scope(root, base, cfg)
            print(json.dumps(sc, ensure_ascii=False, indent=2)) if args.json else print_scope(sc, lang)
            return 1 if sc["required"] else 0
        if args.command == "scan":
            sn = scan(root, base, args.all, lang)
            print(json.dumps(sn, ensure_ascii=False, indent=2)) if args.json else print_scan(sn, lang)
            return 1 if sn["blocking"] else 0
        if args.command == "audit":
            result = run_audit(root, cfg)
            s = SUMMARY[lang]
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif not result["ran"]:
                print(s["audit_fail"].format(cmd=result["command"], reason=result["reason"]))
            else:
                counts = ", ".join(f"{k} {v}" for k, v in result["counts"].items() if v) or "0"
                print(s["audit_head"].format(cmd=result["command"], counts=counts))
                for adv in result["advisories"][:20]:
                    print(f"  [{adv['severity']}] {adv['package']}: {adv['title']} (fix: {adv['fix']}) {adv['url'] or ''}")
                print(s["audit_block"].format(level=result["level"], count=result["atOrAbove"])
                      if result["atOrAbove"] else s["audit_ok"].format(level=result["level"]))
            if not result["ran"]:
                return 3
            return 1 if result["atOrAbove"] else 0
        if args.command == "prompt":
            folder = write_prompt(root, cfg, args.slug, base, args.reviewer)
            print(folder.relative_to(root.resolve()) if root.resolve() in folder.parents else folder)
            return 0
    except GateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
