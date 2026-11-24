"""Tests for hooks/codex-routing-reminder.py. Run: python3 -m unittest discover -s tests"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "codex-routing-reminder.py"
EXAMPLE = json.loads((ROOT / "examples" / "nextjs-supabase-vercel.config.json").read_text(encoding="utf-8"))


class HookTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_config(self, cfg):
        (self.project / ".harness").mkdir(exist_ok=True)
        (self.project / ".harness" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def call(self, file_path, raw=None):
        stdin = raw if raw is not None else json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": file_path}, "cwd": str(self.project)}
        )
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        proc = subprocess.run(
            [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, env=env, timeout=10
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if not proc.stdout.strip():
            return None
        return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_silent_without_harness(self):
        self.assertIsNone(self.call(str(self.project / "app" / "page.tsx")))

    def test_silent_when_codex_disabled(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["models"]["codex"] = {"enabled": False}
        self.write_config(cfg)
        self.assertIsNone(self.call(str(self.project / "app" / "page.tsx")))

    def test_reminds_on_source_file_with_configured_model(self):
        self.write_config(EXAMPLE)
        ctx = self.call(str(self.project / "src" / "features" / "form.tsx"))
        self.assertIsNotNone(ctx)
        self.assertIn("src/features/form.tsx", ctx)
        self.assertIn(EXAMPLE["models"]["codex"]["model"], ctx)
        self.assertIn("xhigh", ctx)
        self.assertIn("opus → sonnet → haiku", ctx)
        self.assertNotIn("백엔드 민감", ctx)

    def test_relative_path_is_resolved_against_project(self):
        self.write_config(EXAMPLE)
        self.assertIsNotNone(self.call("src/app/page.tsx"))

    def test_backend_path_gets_extra_line(self):
        self.write_config(EXAMPLE)
        ctx = self.call(str(self.project / "supabase" / "migrations" / "0001_init.sql"))
        self.assertIn("백엔드 민감", ctx)
        ctx = self.call(str(self.project / "src" / "features" / "order" / "actions.ts"))
        self.assertIn("백엔드 민감", ctx)

    def test_excluded_and_non_source_files_are_silent(self):
        self.write_config(EXAMPLE)
        for rel in ("docs/example.ts", "README.md", "src/types/global.d.ts", "package.json",
                    ".claude/hooks/x.js", "tests/e2e/home.spec.ts"):
            with self.subTest(rel=rel):
                self.assertIsNone(self.call(str(self.project / rel)))

    def test_file_outside_project_is_silent(self):
        self.write_config(EXAMPLE)
        with tempfile.TemporaryDirectory() as other:
            self.assertIsNone(self.call(str(Path(other) / "app" / "page.tsx")))

    def test_english_messages(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["language"] = "en"
        self.write_config(cfg)
        ctx = self.call(str(self.project / "supabase" / "migrations" / "0001_init.sql"))
        self.assertIn("Codex first", ctx)
        self.assertIn("Backend-sensitive path", ctx)

    def test_defaults_when_routing_missing(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg.pop("codexRouting")
        self.write_config(cfg)
        self.assertIsNotNone(self.call(str(self.project / "server" / "main.go")))
        self.assertIsNone(self.call(str(self.project / "node_modules" / "x" / "index.js")))

    def test_security_path_reminds_even_without_codex(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["models"]["codex"] = {"enabled": False}
        self.write_config(cfg)
        ctx = self.call(str(self.project / "src" / "app" / "login" / "actions.ts"))
        self.assertIn("보안 관문", ctx)
        self.assertNotIn("Codex 우선", ctx)
        self.assertIn("보안 관문", self.call(str(self.project / ".env.local")))
        self.assertIsNone(self.call(str(self.project / ".env.example")))
        self.assertIsNone(self.call(str(self.project / "docs" / "auth-notes.md")))

    def test_security_and_codex_lines_together(self):
        self.write_config(EXAMPLE)
        ctx = self.call(str(self.project / "supabase" / "migrations" / "0003_policies.sql"))
        self.assertIn("Codex 우선", ctx)
        self.assertIn("보안 관문", ctx)

    def test_custom_sensitive_pattern(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["security"] = {"sensitive": [r"^src/church/"]}
        self.write_config(cfg)
        self.assertIn("보안 관문", self.call(str(self.project / "src" / "church" / "notice.ts")))

    def test_bad_regex_and_bad_stdin_never_crash(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["codexRouting"]["code"] = ["(unclosed", r"\.tsx$"]
        self.write_config(cfg)
        self.assertIsNotNone(self.call(str(self.project / "src" / "a.tsx")))
        self.assertIsNone(self.call("", raw="not json"))
        self.assertIsNone(self.call("", raw=json.dumps({"tool_input": {}})))


if __name__ == "__main__":
    unittest.main()
