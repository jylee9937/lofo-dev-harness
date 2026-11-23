"""Tests for scripts/render.py. Run: python3 -m unittest discover -s tests"""
import copy
import io
import itertools
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import render  # noqa: E402

EXAMPLE = json.loads((ROOT / "examples" / "nextjs-supabase-vercel.config.json").read_text(encoding="utf-8"))
AUTONOMOUS = json.loads((ROOT / "examples" / "autonomous.config.json").read_text(encoding="utf-8"))


class ProjectTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / ".harness").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write_config(self, cfg):
        (self.project / ".harness" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def run_render(self, check=False):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = render.run(self.project, check)
        return code, out.getvalue(), err.getvalue()

    def read(self, rel):
        return (self.project / rel).read_text(encoding="utf-8")


class RenderBasics(ProjectTestCase):
    def test_creates_all_files_from_example(self):
        self.write_config(EXAMPLE)
        code, out, err = self.run_render()
        self.assertEqual(code, 0, err)
        for rel in ("AGENTS.md", "CLAUDE.md", "docs/dev-harness.md", ".gitignore"):
            self.assertIn(f"created            {rel}", out)
        agents = self.read("AGENTS.md")
        self.assertTrue(agents.startswith(render.START))
        self.assertIn(render.END, agents)
        self.assertIn("pnpm lint && pnpm typecheck && pnpm build", agents)
        self.assertNotIn("gpt-", agents, "model names must stay in config.json only")
        self.assertEqual(self.read("CLAUDE.md"), "@AGENTS.md\n")
        self.assertIn(".harness/config.local.json", self.read(".gitignore"))

    def test_rerun_is_idempotent_and_check_reports(self):
        self.write_config(EXAMPLE)
        self.assertEqual(self.run_render(check=True)[0], 1)
        self.assertEqual(self.run_render()[0], 0)
        code, out, _ = self.run_render()
        self.assertEqual(code, 0)
        self.assertEqual(out.count("unchanged"), 4)
        self.assertEqual(self.run_render(check=True)[0], 0)

    def test_check_writes_nothing(self):
        self.write_config(EXAMPLE)
        self.run_render(check=True)
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_custom_doc_path(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["docs"]["devHarness"] = "docs/개발-하네스.md"
        self.write_config(cfg)
        self.assertEqual(self.run_render()[0], 0)
        self.assertTrue((self.project / "docs" / "개발-하네스.md").is_file())
        self.assertIn("`docs/개발-하네스.md`", self.read("AGENTS.md"))


class PreservesUserContent(ProjectTestCase):
    def test_inserts_block_above_existing_agents_md(self):
        self.write_config(EXAMPLE)
        (self.project / "AGENTS.md").write_text("# My project\n\nKeep me.\n", encoding="utf-8")
        code, out, _ = self.run_render()
        self.assertEqual(code, 0)
        self.assertIn("inserted           AGENTS.md", out)
        agents = self.read("AGENTS.md")
        self.assertTrue(agents.startswith(render.START))
        self.assertTrue(agents.rstrip().endswith("Keep me."))

    def test_edits_inside_block_are_replaced_outside_kept(self):
        self.write_config(EXAMPLE)
        self.run_render()
        agents = self.read("AGENTS.md")
        tampered = agents.replace("## 완료 기준", "## 완료 기준 (edited)") + "\nMy own rule.\n"
        (self.project / "AGENTS.md").write_text(tampered, encoding="utf-8")
        code, out, _ = self.run_render()
        self.assertEqual(code, 0)
        self.assertIn("updated            AGENTS.md", out)
        result = self.read("AGENTS.md")
        self.assertNotIn("(edited)", result)
        self.assertIn("My own rule.", result)

    def test_claude_md_gets_import_prepended(self):
        self.write_config(EXAMPLE)
        (self.project / "CLAUDE.md").write_text("Some notes.\n", encoding="utf-8")
        self.run_render()
        self.assertEqual(self.read("CLAUDE.md"), "@AGENTS.md\n\nSome notes.\n")

    def test_claude_md_with_import_is_untouched(self):
        self.write_config(EXAMPLE)
        (self.project / "CLAUDE.md").write_text("Intro\n@AGENTS.md\nMore\n", encoding="utf-8")
        code, out, _ = self.run_render()
        self.assertIn("unchanged          CLAUDE.md", out)
        self.assertEqual(self.read("CLAUDE.md"), "Intro\n@AGENTS.md\nMore\n")

    def test_gitignore_without_trailing_newline(self):
        self.write_config(EXAMPLE)
        (self.project / ".gitignore").write_text("node_modules", encoding="utf-8")
        self.run_render()
        lines = self.read(".gitignore").splitlines()
        self.assertEqual(lines[0], "node_modules")
        self.assertIn(".harness/config.local.json", lines)
        self.assertIn(".harness/local/", lines)


class Errors(ProjectTestCase):
    def test_missing_config(self):
        code, _, err = self.run_render()
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_invalid_json(self):
        (self.project / ".harness" / "config.json").write_text("{nope", encoding="utf-8")
        code, _, err = self.run_render()
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)

    def test_invalid_config_lists_errors_and_writes_nothing(self):
        cfg = copy.deepcopy(EXAMPLE)
        del cfg["models"]["codex"]["model"]
        cfg["stack"]["db"] = "mongodb"
        cfg["extra"] = True
        self.write_config(cfg)
        code, _, err = self.run_render()
        self.assertEqual(code, 2)
        self.assertIn("models.codex.model", err)
        self.assertIn("stack.db", err)
        self.assertIn("extra: unknown top-level key", err)
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_autonomous_requires_block(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg["mode"] = "autonomous"
        self.write_config(cfg)
        code, _, err = self.run_render()
        self.assertEqual(code, 2)
        self.assertIn("autonomous: required", err)

    def test_doc_path_outside_project_is_refused(self):
        for bad in ("../outside.md", "docs/../../outside.md", "/tmp/outside.md"):
            with self.subTest(path=bad):
                cfg = copy.deepcopy(EXAMPLE)
                cfg["docs"]["devHarness"] = bad
                self.write_config(cfg)
                code, _, err = self.run_render()
                self.assertEqual(code, 2)
                self.assertIn("inside the project", err)
                self.assertFalse((self.project.parent / "outside.md").exists())
                self.assertFalse((self.project / "AGENTS.md").exists())

    def test_single_marker_is_refused(self):
        self.write_config(EXAMPLE)
        (self.project / "AGENTS.md").write_text(f"{render.START}\nhalf a block\n", encoding="utf-8")
        code, _, err = self.run_render()
        self.assertEqual(code, 2)
        self.assertIn("AGENTS.md", err)
        self.assertEqual(self.read("AGENTS.md"), f"{render.START}\nhalf a block\n")


class Variants(ProjectTestCase):
    def test_generic_presets_and_solo_mode_en(self):
        cfg = copy.deepcopy(EXAMPLE)
        cfg.update(language="en")
        cfg["stack"].update(framework="other", db="firebase", hosting="gcp", packageManager="npm")
        cfg["models"]["codex"] = {"enabled": False}
        cfg.pop("e2e")
        cfg.pop("codexRouting")
        cfg["integrations"] = {"notes": "none", "design": "none", "gstack": False, "tasks": "none"}
        self.write_config(cfg)
        code, _, err = self.run_render()
        self.assertEqual(code, 0, err)
        doc = self.read("docs/dev-harness.md")
        self.assertIn("There is no preset for this framework yet", doc)
        self.assertIn("There is no preset for this database or backend yet", doc)
        self.assertIn("There is no preset for this hosting environment yet", doc)
        self.assertIn("This project does not use Codex", doc)
        self.assertIn("Firebase", doc)
        self.assertIn("Google Cloud", doc)
        self.assertIn("not configured yet", doc)
        self.assertIn("No integrations configured", doc)
        self.assertIn("`npm run dev`", self.read("AGENTS.md"))
        self.assertNotIn("codex-delegate", self.read("AGENTS.md"))

    def test_autonomous_example_renders_coming_soon(self):
        self.write_config(AUTONOMOUS)
        code, _, err = self.run_render()
        self.assertEqual(code, 0, err)
        self.assertIn("coming soon", self.read("docs/dev-harness.md"))

    def test_every_combination_renders_cleanly(self):
        combos = itertools.product(
            render.LANGS, render.MODES, ("nextjs", "other"), render.DBS, render.HOSTINGS, (True, False)
        )
        for lang, mode, framework, db, hosting, codex in combos:
            cfg = copy.deepcopy(AUTONOMOUS if mode == "autonomous" else EXAMPLE)
            cfg["language"] = lang
            cfg["stack"].update(framework=framework, db=db, hosting=hosting)
            cfg["models"]["codex"] = (
                {"enabled": True, "model": "m", "effort": "xhigh"} if codex else {"enabled": False}
            )
            with self.subTest(lang=lang, mode=mode, framework=framework, db=db, hosting=hosting, codex=codex):
                self.assertEqual(render.validate(cfg), [])
                docs = render.render_documents(cfg)
                for key in ("agents_block", "doc_block"):
                    text = docs[key]
                    self.assertNotIn("{{", text)
                    self.assertNotIn("\n\n\n", text)
                    self.assertEqual(text.count(render.START), 1)


class TemplateParity(unittest.TestCase):
    def test_both_languages_have_the_same_templates(self):
        def names(lang):
            base = ROOT / "templates" / lang
            return sorted(str(p.relative_to(base)) for p in base.rglob("*.md"))

        self.assertEqual(names("ko"), names("en"))


if __name__ == "__main__":
    unittest.main()
