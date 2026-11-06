"""Prevent documentation-only changes from bypassing required CI checks."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "change_scope", ROOT / "scripts/change_scope.py"
)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


def workflow(name):
    return yaml.load(
        (ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader
    )


class DocumentationScopeTests(unittest.TestCase):
    def test_preserve_documentation_and_firmware_contracts(self):
        jobs = workflow("validate.yml")["jobs"]
        docs = jobs["validate"]
        self.assertNotIn("if", docs)
        steps = docs["steps"]
        self.assertEqual(
            steps[0]["with"], {"persist-credentials": "false", "fetch-depth": "0"}
        )
        commands = [step.get("run") for step in steps]
        for command in (
            "python scripts/check.py",
            "python -m unittest discover -s tests -v",
            "python -m unittest discover -s examples/tests -v",
        ):
            self.assertIn(command, commands)
        self.assertEqual(
            jobs["firmware-build"]["if"],
            "${{ needs.validate.outputs.firmware-required == 'true' }}",
        )
        self.assertEqual(
            jobs["firmware"]["name"], "ESPHome configuration and generation"
        )
        self.assertEqual(jobs["firmware"]["if"], "${{ always() }}")

    def test_gate_requires_success_or_exact_documentation_proof(self):
        gate = workflow("validate.yml")["jobs"]["firmware"]["steps"][0]["run"]
        code = gate.removeprefix("python3 - <<'PY'\n").removesuffix("PY\n")

        def accepts(results):
            return (
                subprocess.run(
                    [os.sys.executable, "-c", code],
                    env={**os.environ, "RESULTS": json.dumps(results)},
                    capture_output=True,
                    check=False,
                ).returncode
                == 0
            )

        for required in ("true", "false"):
            baseline = {
                "validate": {
                    "result": "success",
                    "outputs": {
                        "firmware-required": required,
                        "scope-reason": "documentation-only"
                        if required == "false"
                        else "non-documentation-change",
                    },
                },
                "firmware-build": {
                    "result": "skipped" if required == "false" else "success"
                },
            }
            self.assertTrue(accepts(baseline))
            for job in baseline:
                for result in ("failure", "cancelled", "skipped"):
                    mutated = json.loads(json.dumps(baseline))
                    mutated[job]["result"] = result
                    if mutated == baseline:
                        continue
                    self.assertFalse(accepts(mutated))
            missing = json.loads(json.dumps(baseline))
            del missing["validate"]["outputs"]["firmware-required"]
            self.assertFalse(accepts(missing))
            del missing["firmware-build"]
            self.assertFalse(accepts(missing))
        baseline["validate"]["outputs"]["scope-reason"] = "git-error"
        self.assertFalse(accepts(baseline))

    def test_real_events_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", directory, *args],
                    text=True,
                    env={
                        **os.environ,
                        "GIT_CONFIG_GLOBAL": os.devnull,
                        "GIT_CONFIG_NOSYSTEM": "1",
                    },
                ).strip()

            git("init", "-q")
            git("config", "user.name", "test")
            git("config", "user.email", "test@example.invalid")
            git("config", "commit.gpgsign", "false")
            (root / "README.md").write_text("before\n")
            git("add", ".")
            git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            (root / "README.md").write_text("after\n")
            git("commit", "-qam", "docs")
            docs = git("rev-parse", "HEAD")
            for event, payload in (
                (
                    "pull_request",
                    {"pull_request": {"base": {"sha": base}, "head": {"sha": docs}}},
                ),
                ("push", {"before": base, "after": docs}),
            ):
                self.assertEqual(
                    scope.classify(root, event, payload),
                    {"run": False, "reason": "documentation-only"},
                )
            (root / "firmware.yaml").write_text("esphome: {}\n")
            git("add", ".")
            git("commit", "-qm", "source")
            code = git("rev-parse", "HEAD")
            self.assertTrue(
                scope.classify(root, "push", {"before": base, "after": code})["run"]
            )
            self.assertTrue(scope.classify(root, "pull_request", {})["run"])
            for event in ("workflow_dispatch", "schedule", "workflow_call", "unknown"):
                self.assertTrue(scope.classify(root, event, {})["run"])
