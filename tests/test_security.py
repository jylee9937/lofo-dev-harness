"""Tests for scripts/security.py. Run: python3 -m unittest discover -s tests"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import security as sg  # noqa: E402

EXAMPLE_CONFIG = json.loads((ROOT / "examples" / "nextjs-supabase-vercel.config.json").read_text(encoding="utf-8"))

# Fake keys are assembled at runtime so this file never contains a literal secret.
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
SERVICE_ROLE_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + \
    "eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UifQ" + ".c2lnbmF0dXJlLXBsYWNlaG9sZGVy"
ANON_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." + \
    "eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlIn0" + ".c2lnbmF0dXJlLXBsYWNlaG9sZGVy"

BAD_FILES = {
    "src/app/login/actions.ts": '''"use server"
export async function login(formData: FormData) {
  const email = formData.get("email") as string
  const { data } = await supabase.auth.signInWithPassword({ email, password: formData.get("password") as string })
  console.log("login", email, password)
  const rows = await db.query(`select * from users where email = '${email}'`)
  return data
}
''',
    "src/app/api/upload/route.ts": '''export async function POST(request: Request) {
  const form = await request.formData()
  const file = form.get("file") as File
  await supabase.storage.from("docs").upload(file.name, file)
  return Response.json({ ok: true })
}
''',
    "src/app/api/webhook/route.ts": '''export async function POST(req: Request) {
  const body = await req.json()
  await handlePayment(body.amount)
  return new Response("ok")
}
''',
    "src/components/admin-panel.tsx": """'use client'
const key = process.env.SUPABASE_SERVICE_ROLE_KEY
export const search = (q: string) => supabase.from("posts").select().or(`title.ilike.%${q}%`)
""",
    "supabase/migrations/0002_members.sql": """create table public.members (id uuid primary key, phone text);
create function public.promote(uid uuid) returns void language sql security definer as $$ select 1 $$;
grant insert on public.members to anon;
""",
    "src/lib/hash.ts": "export const h = (password: string) => createHash('md5').update(password).digest('hex')\n",
    "src/lib/keys.ts": f"export const aws = '{FAKE_AWS}'\nexport const admin = '{SERVICE_ROLE_JWT}'\nexport const anon = '{ANON_JWT}'\n",
    "src/lib/config.ts": "export const config = { apiKey: 'live-9f8e7d6c5b4a3210', stripeSecret: process.env.STRIPE_SECRET }\n",
}

GOOD_FILES = {
    "src/app/api/upload/route.ts": '''import { z } from "zod"
const MAX_SIZE = 5 * 1024 * 1024
const ALLOWED_TYPES = ["image/png", "image/jpeg"]
export async function POST(request: Request) {
  const user = await getUser()
  const form = await request.formData()
  const file = form.get("file") as File
  if (file.size > MAX_SIZE || !ALLOWED_TYPES.includes(file.type)) return new Response("bad", { status: 400 })
  z.string().parse(file.name)
  await supabase.storage.from("docs").upload(crypto.randomUUID(), file)
  return Response.json({ ok: true })
}
''',
    "src/app/api/webhook/route.ts": '''export async function POST(req: Request) {
  const event = stripe.webhooks.constructEvent(await req.text(), req.headers.get("stripe-signature"), secret)
  await handlePayment(event)
  return new Response("ok")
}
''',
    "supabase/migrations/0002_members.sql": """create table public.members (id uuid primary key, phone text);
alter table public.members enable row level security;
create function public.promote(uid uuid) returns void language sql security definer set search_path = '' as $$ select 1 $$;
""",
    "src/lib/query.ts": "export const find = (email: string) => supabase.from('users').select().eq('email', email)\n",
}


def run(cmd, cwd):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


class Repo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        run(["git", "init", "-q", "-b", "main"], self.root)
        run(["git", "config", "user.email", "test@example.invalid"], self.root)
        run(["git", "config", "user.name", "test"], self.root)
        (self.root / ".harness").mkdir()
        (self.root / ".harness" / "config.json").write_text(json.dumps(EXAMPLE_CONFIG), encoding="utf-8")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-qm", "base"], self.root)
        run(["git", "checkout", "-qb", "feature"], self.root)
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def write(self, files):
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = sg.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def rules(self, result):
        return {(f["rule"], f["file"]) for f in result["findings"]}


class Scope(Repo):
    def test_categories_and_required(self):
        self.write(BAD_FILES)
        sc = sg.scope(self.root, "main", sg.load_config(self.root))
        self.assertTrue(sc["required"])
        for cat in ("auth", "upload", "webhook", "migrations", "secrets", "money"):
            self.assertIn(cat, sc["gateCategories"])
        self.assertIn("src/app/login/actions.ts", sc["categories"]["auth"])

    def test_plain_ui_change_not_required(self):
        self.write({"src/components/button.tsx": "export const Button = () => <button>Hi</button>\n"})
        code, out, _ = self.cli("scope", "--base", "main")
        self.assertEqual(code, 0)
        self.assertIn("필요 없음", out)

    def test_dependency_change_flagged(self):
        self.write({"package.json": '{"dependencies": {"left-pad": "1.3.0"}}\n'})
        sc = sg.scope(self.root, "main", sg.load_config(self.root))
        self.assertTrue(sc["dependenciesChanged"])
        self.assertFalse(sc["required"])

    def test_custom_sensitive_pattern(self):
        cfg = dict(EXAMPLE_CONFIG, security={"sensitive": [r"^src/church/"]})
        (self.root / ".harness" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.write({"src/church/notice.ts": "export const x = 1\n"})
        sc = sg.scope(self.root, "main", sg.load_config(self.root))
        self.assertIn("custom", sc["gateCategories"])


class Scan(Repo):
    def test_planted_problems_are_found(self):
        self.write(BAD_FILES)
        result = sg.scan(self.root, "main", False, "ko")
        found = self.rules(result)
        expected = {
            ("sql-interpolation", "src/app/login/actions.ts"),
            ("password-log", "src/app/login/actions.ts"),
            ("bruteforce", "src/app/login/actions.ts"),
            ("input-validation", "src/app/login/actions.ts"),
            ("upload-unchecked", "src/app/api/upload/route.ts"),
            ("authz-missing", "src/app/api/upload/route.ts"),
            ("webhook-unsigned", "src/app/api/webhook/route.ts"),
            ("client-secret", "src/components/admin-panel.tsx"),
            ("postgrest-filter", "src/components/admin-panel.tsx"),
            ("rls-missing", "supabase/migrations/0002_members.sql"),
            ("definer-search-path", "supabase/migrations/0002_members.sql"),
            ("grant-anon", "supabase/migrations/0002_members.sql"),
            ("weak-hash", "src/lib/hash.ts"),
            ("secret-key", "src/lib/keys.ts"),
            ("secret-service-role", "src/lib/keys.ts"),
            ("secret-hardcoded", "src/lib/config.ts"),
        }
        self.assertEqual(expected - found, set(), "missed findings")
        service_role_lines = [f for f in result["findings"] if f["rule"] == "secret-service-role"]
        self.assertEqual(len(service_role_lines), 1, "the anon key is public by design and must not be flagged")
        self.assertGreater(result["blocking"], 0)

    def test_clean_code_has_no_blocking_findings(self):
        self.write(GOOD_FILES)
        result = sg.scan(self.root, "main", False, "en")
        self.assertEqual([f for f in result["findings"] if f["severity"] in ("block", "high")], [])
        self.assertNotIn(("authz-missing", "src/app/api/upload/route.ts"), self.rules(result))

    def test_only_changed_lines_count_for_line_rules(self):
        self.write({"src/lib/old.ts": "export const legacy = (q) => db.query(`select ${q}`)\n"})
        run(["git", "add", "-A"], self.root)
        run(["git", "commit", "-qm", "legacy"], self.root)
        run(["git", "checkout", "-q", "main"], self.root)
        run(["git", "merge", "-q", "feature"], self.root)
        run(["git", "checkout", "-qb", "next"], self.root)
        self.write({"src/lib/old.ts": "export const legacy = (q) => db.query(`select ${q}`)\nexport const ok = 1\n"})
        diff_result = sg.scan(self.root, "main", False, "en")
        self.assertNotIn(("sql-interpolation", "src/lib/old.ts"), self.rules(diff_result))
        all_result = sg.scan(self.root, "main", True, "en")
        self.assertIn(("sql-interpolation", "src/lib/old.ts"), self.rules(all_result))

    def test_security_ok_marker_silences_only_that_rule(self):
        files = dict(BAD_FILES)
        files["src/app/api/upload/route.ts"] = "// security-ok: upload-unchecked bucket enforces 5MB and images only\n" + \
            files["src/app/api/upload/route.ts"]
        self.write(files)
        result = sg.scan(self.root, "main", False, "en")
        self.assertNotIn(("upload-unchecked", "src/app/api/upload/route.ts"), self.rules(result))
        self.assertIn(("authz-missing", "src/app/api/upload/route.ts"), self.rules(result))
        self.assertTrue(any(s["rule"] == "upload-unchecked" and "5MB" in s["reason"] for s in result["suppressed"]))

    def test_tracked_env_file_blocks_but_example_does_not(self):
        self.write({".env.local": "SECRET=abc\n", ".env.example": "SECRET=\n"})
        run(["git", "add", "-f", ".env.local", ".env.example"], self.root)
        result = sg.scan(self.root, "main", False, "en")
        self.assertIn(("secret-env-file", ".env.local"), self.rules(result))
        self.assertNotIn(("secret-env-file", ".env.example"), self.rules(result))

    def test_cli_exit_codes_and_json(self):
        self.write(GOOD_FILES)
        code, out, _ = self.cli("scan", "--base", "main", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["blocking"], 0)
        self.write(BAD_FILES)
        code, out, _ = self.cli("scan", "--base", "main")
        self.assertEqual(code, 1)
        self.assertIn("결과: 막힘", out)


class Prompt(Repo):
    def test_prompt_folder(self):
        self.write(BAD_FILES)
        code, out, _ = self.cli("prompt", "--slug", "login-upload", "--reviewer", "claude", "--base", "main")
        self.assertEqual(code, 0)
        folder = self.root / out.strip()
        prompt = (folder / "prompt.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", prompt)
        self.assertIn("판정: GO", prompt)
        self.assertIn("provisional", prompt)
        self.assertIn("src/app/login/actions.ts", prompt)
        self.assertNotIn(FAKE_AWS, prompt, "secret values must not be copied into review files")
        scan_data = json.loads((folder / "scan.json").read_text(encoding="utf-8"))
        self.assertTrue(scan_data["scope"]["required"])
        scan_text = (folder / "scan.json").read_text(encoding="utf-8")
        for secret in (FAKE_AWS, SERVICE_ROLE_JWT, "live-9f8e7d6c5b4a3210"):
            self.assertNotIn(secret, scan_text, "secret values must be redacted in review records")
        self.assertIn("[REDACTED", scan_text)

    def test_redact(self):
        self.assertEqual(sg.redact(f"key = '{FAKE_AWS}'"), "key = '[REDACTED]'")
        self.assertNotIn("abc123", sg.redact("SUPABASE_SERVICE_ROLE_KEY=abc123"))
        self.assertIn("[REDACTED-JWT]", sg.redact(SERVICE_ROLE_JWT))

    def test_bad_slug_and_outside_dir(self):
        code, _, err = self.cli("prompt", "--slug", "Bad Slug")
        self.assertEqual(code, 2)
        cfg = dict(EXAMPLE_CONFIG, security={"reviewsDir": "../outside"})
        (self.root / ".harness" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        code, _, err = self.cli("prompt", "--slug", "x")
        self.assertEqual(code, 2)
        self.assertIn("inside the project", err)


class Verdict(unittest.TestCase):
    def test_reads_last_verdict(self):
        self.assertEqual(sg.read_verdict("blah\n판정: NO-GO\n...\n판정: GO\n"), "GO")
        self.assertEqual(sg.read_verdict("**VERDICT: NO-GO**"), "NO-GO")
        self.assertEqual(sg.read_verdict("> 판정: `GO`"), "GO")
        self.assertIsNone(sg.read_verdict("looks fine to me"))

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "codex.md"
            for text, code in (("x\nVERDICT: GO\n", 0), ("판정: NO-GO", 1), ("no verdict", 2)):
                path.write_text(text, encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(sg.main(["verdict", str(path)]), code)


class Audit(unittest.TestCase):
    PNPM = {"advisories": {"1": {"module_name": "lodash", "severity": "high", "title": "Command Injection",
                                 "url": "https://example.invalid/a", "patched_versions": ">=4.17.21"}},
            "metadata": {"vulnerabilities": {"info": 0, "low": 0, "moderate": 2, "high": 3, "critical": 1}}}
    NPM = {"auditReportVersion": 2,
           "vulnerabilities": {"lodash": {"name": "lodash", "severity": "critical",
                                          "via": [{"title": "Prototype Pollution", "url": "https://example.invalid/b"}],
                                          "fixAvailable": {"name": "lodash", "version": "4.18.1"}}},
           "metadata": {"vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 1, "total": 1}}}

    def test_parse_pnpm_and_npm(self):
        pnpm = sg.parse_audit(json.dumps(self.PNPM))
        self.assertEqual(pnpm["counts"]["high"], 3)
        self.assertEqual(pnpm["advisories"][0]["package"], "lodash")
        self.assertEqual(sg.at_or_above(pnpm["counts"], "high"), 4)
        self.assertEqual(sg.at_or_above(pnpm["counts"], "critical"), 1)
        self.assertEqual(sg.at_or_above(pnpm["counts"], "moderate"), 6)
        npm = sg.parse_audit(json.dumps(self.NPM))
        self.assertEqual(npm["advisories"][0]["fix"], "4.18.1")
        self.assertIsNone(sg.parse_audit("not json"))
        self.assertIsNone(sg.parse_audit("{}"))

    def test_command_selection(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cfg = {"audit": None, "packageManager": None}
            self.assertEqual(sg.audit_command(root, cfg)[0], "npm")
            (root / "pnpm-lock.yaml").write_text("", encoding="utf-8")
            self.assertEqual(sg.audit_command(root, cfg)[:2], ["pnpm", "audit"])
            self.assertEqual(sg.audit_command(root, {"audit": "osv-scanner --lockfile=x", "packageManager": None}),
                             ["osv-scanner", "--lockfile=x"])

    @unittest.skipUnless(shutil.which("git"), "git required")
    def test_audit_that_cannot_run(self):
        with tempfile.TemporaryDirectory() as d:
            result = sg.run_audit(Path(d), {"audit": "definitely-not-a-real-command-xyz", "auditLevel": "high",
                                            "packageManager": None})
            self.assertFalse(result["ran"])


if __name__ == "__main__":
    unittest.main()
