"""Tests for scripts/flow.py. Run: python3 -m unittest discover -s tests"""
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import flow as wf  # noqa: E402

EXAMPLE = json.loads((ROOT / "examples" / "flows" / "study-group.flow.json").read_text(encoding="utf-8"))


def screen(f, sid):
    return next(s for s in f["screens"] if s["id"] == sid)


def codes(findings):
    return {(x["code"], x["screen"]) for x in findings}


class Validation(unittest.TestCase):
    def test_example_is_valid_and_clean(self):
        self.assertEqual(wf.validate(EXAMPLE), [])
        findings = wf.find_problems(EXAMPLE)
        self.assertEqual(findings, [])
        self.assertFalse(wf.blocking(EXAMPLE, findings))

    def test_reference_errors_are_reported(self):
        f = copy.deepcopy(EXAMPLE)
        f["start"] = "nowhere"
        screen(f, "group-list")["stage"] = "no-stage"
        screen(f, "group-detail")["wireframe"][-1]["action"] = "no-action"
        f["issues"][0]["screen"] = "ghost"
        f["requests"][0]["action"] = "ghost-action"
        f["screens"].append(copy.deepcopy(screen(f, "apply-done")))
        f["extra"] = 1
        errors = "\n".join(wf.validate(f))
        for expected in ("start: unknown screen", "stage: unknown stage", "no action 'no-action'",
                         "issues[0].screen: unknown screen", "requests[0].action", "duplicate screen ID",
                         "extra: unknown top-level key"):
            self.assertIn(expected, errors)

    def test_enums_and_required_fields(self):
        f = copy.deepcopy(EXAMPLE)
        screen(f, "group-list")["origin"] = "maybe"
        screen(f, "group-list")["actions"][0].pop("to")
        f["issues"][0]["severity"] = "S9"
        f["decisions"][0]["status"] = "pending"
        errors = "\n".join(wf.validate(f))
        self.assertIn("origin", errors)
        self.assertIn(".to: required", errors)
        self.assertIn("severity", errors)
        self.assertIn("decisions[0].status", errors)


class Findings(unittest.TestCase):
    def check(self, mutate):
        f = copy.deepcopy(EXAMPLE)
        mutate(f)
        self.assertEqual(wf.validate(f), [], "mutation must keep the flow valid")
        return f, wf.find_problems(f)

    def test_broken_link_and_missing_destination(self):
        def mutate(f):
            screen(f, "group-list")["actions"][2]["to"] = "settings"
            screen(f, "group-detail")["actions"][0]["to"] = None
        f, found = self.check(mutate)
        self.assertIn(("broken-link", "group-list"), codes(found))
        self.assertIn(("missing-destination", "group-detail"), codes(found))
        self.assertIn(("unreachable", "apply-form"), codes(found))
        self.assertIn(("scenario-missing", "group-detail"), codes(found))
        self.assertTrue(wf.blocking(f, found))

    def test_dead_end_and_trap(self):
        def mutate(f):
            screen(f, "apply-failed")["actions"] = []
            screen(f, "apply-failed")["wireframe"] = []
            screen(f, "group-list-empty")["actions"][0]["to"] = "group-list-empty"
        _, found = self.check(mutate)
        self.assertIn(("dead-end", "apply-failed"), codes(found))
        self.assertIn(("trap", "group-list-empty"), codes(found))

    def test_error_screen_without_recovery(self):
        def mutate(f):
            screen(f, "apply-invalid")["actions"][0]["to"] = "apply-invalid"
        _, found = self.check(mutate)
        self.assertIn(("no-recovery", "apply-invalid"), codes(found))

    def test_missing_variant_states(self):
        def mutate(f):
            f["screens"] = [s for s in f["screens"] if s["id"] not in ("group-list-empty", "apply-invalid")]
            f["issues"] = [i for i in f["issues"] if i["screen"] != "group-list-empty"]
            screen(f, "group-list")["actions"].pop(1)
            screen(f, "apply-form")["actions"].pop(1)
            f["scenarios"] = [s for s in f["scenarios"] if s["id"] in ("join", "retry-after-failure")]
        _, found = self.check(mutate)
        self.assertIn(("missing-empty-state", "group-list"), codes(found))
        self.assertIn(("missing-error-state", "apply-form"), codes(found))

    def test_scenario_mismatch(self):
        def mutate(f):
            f["scenarios"][0]["steps"][1] = {"screen": "apply-form", "action": "submit"}
            f["scenarios"][2]["steps"][0]["action"] = "back"
            f["scenarios"][2]["steps"][1] = {"screen": "apply-invalid", "action": "fix"}
        _, found = self.check(mutate)
        self.assertIn("scenario-screen", {x["code"] for x in found})

    def test_scenario_unknown_action(self):
        def mutate(f):
            f["scenarios"][3]["steps"][0]["action"] = "nope"
        _, found = self.check(mutate)
        self.assertIn(("scenario-action", "group-list"), codes(found))

    def test_no_end_and_no_scenarios(self):
        def mutate(f):
            for s in f["screens"]:
                s.pop("end", None)
            f.pop("scenarios")
        _, found = self.check(mutate)
        self.assertIn(("no-end", None), codes(found))
        self.assertIn(("no-scenario", None), codes(found))

    def test_open_s2_issue_blocks_until_fixed(self):
        f = copy.deepcopy(EXAMPLE)
        f["issues"][0]["severity"] = "S2"
        self.assertTrue(wf.blocking(f, wf.find_problems(f)))
        f["issues"][0]["status"] = "fixed"
        self.assertFalse(wf.blocking(f, wf.find_problems(f)))

    def test_english_messages(self):
        f = copy.deepcopy(EXAMPLE)
        f["language"] = "en"
        screen(f, "group-detail")["actions"][0]["to"] = None
        found = wf.find_problems(f)
        self.assertTrue(any("has no destination yet" in x["message"] for x in found))

    def test_findings_sorted_by_severity(self):
        def mutate(f):
            screen(f, "group-list")["actions"][2]["to"] = "settings"
            f.pop("scenarios")
        _, found = self.check(mutate)
        order = [x["severity"] for x in found]
        self.assertEqual(order, sorted(order))


class Cli(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, f, name="x.flow.json"):
        path = self.dir / name
        path.write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
        return path

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = wf.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_check_exit_codes(self):
        code, out, _ = self.run_cli("check", str(self.write(EXAMPLE)))
        self.assertEqual(code, 0)
        self.assertIn("통과", out)
        broken = copy.deepcopy(EXAMPLE)
        screen(broken, "group-detail")["actions"][0]["to"] = None
        code, out, _ = self.run_cli("check", str(self.write(broken)))
        self.assertEqual(code, 1)
        self.assertIn("missing-destination", out)
        code, _, err = self.run_cli("check", str(self.write({"version": 1})))
        self.assertEqual(code, 2)
        self.assertIn("required", err)

    def test_check_json(self):
        code, out, _ = self.run_cli("check", "--json", str(self.write(EXAMPLE)))
        data = json.loads(out)
        self.assertEqual(data["flow"], "study-group")
        self.assertFalse(data["blocking"])

    def test_build_embeds_safe_data(self):
        f = copy.deepcopy(EXAMPLE)
        f["title"] = "Title </script><script>alert(1)</script> & co"
        screen(f, "group-list")["rationale"] = "</script><!-- sneaky -->"
        path = self.write(f)
        out = self.dir / "board.html"
        code, _, err = self.run_cli("build", str(path), str(out))
        self.assertEqual(code, 0, err)
        page = out.read_text(encoding="utf-8")
        self.assertEqual(page.count("</script>"), 2, "data must not close the script tag")
        self.assertNotIn("<!-- sneaky", page)
        self.assertIn("<title>Title &lt;/script&gt;", page)
        data = re.search(r'<script type="application/json" id="wireflow-data">(.*?)</script>', page, re.S).group(1)
        parsed = json.loads(data)
        self.assertEqual(parsed["flow"]["title"], f["title"])
        self.assertEqual(parsed["numbers"]["apply-form"], "03.01")
        for placeholder in ("__WIREFLOW_DATA__", "__WIREFLOW_LANG__", "__WIREFLOW_TITLE__"):
            self.assertNotIn(placeholder, page)

    def test_build_default_output_and_images(self):
        f = copy.deepcopy(EXAMPLE)
        (self.dir / "mock").mkdir()
        (self.dir / "mock" / "form.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
        screen(f, "apply-form")["image"] = "mock/form.svg"
        screen(f, "group-detail")["image"] = "mock/missing.png"
        path = self.write(f, "study.flow.json")
        code, out, _ = self.run_cli("build", str(path))
        self.assertEqual(code, 0)
        board = self.dir / "study-group.wireflow.html"
        self.assertTrue(board.is_file())
        self.assertIn("image-missing", out)
        data = json.loads(re.search(r'id="wireflow-data">(.*?)</script>', board.read_text(encoding="utf-8"), re.S).group(1))
        self.assertEqual(data["images"], {"apply-form": "mock/form.svg"})
        embedded = self.dir / "embedded.html"
        self.run_cli("build", str(path), str(embedded), "--embed-images")
        data = json.loads(re.search(r'id="wireflow-data">(.*?)</script>', embedded.read_text(encoding="utf-8"), re.S).group(1))
        self.assertTrue(data["images"]["apply-form"].startswith("data:image/svg+xml;base64,"))

    def test_build_refuses_invalid_flow(self):
        code, _, err = self.run_cli("build", str(self.write({"version": 2})))
        self.assertEqual(code, 2)
        self.assertFalse((self.dir / "x.wireflow.html").exists())


if __name__ == "__main__":
    unittest.main()
