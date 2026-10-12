from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sky.cli import main  # noqa: E402


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()


class RunsCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = os.environ.get("SKY_STATE_DIR")
        os.environ["SKY_STATE_DIR"] = self.tmp.name
        self.root = Path(self.tmp.name) / "runs"

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("SKY_STATE_DIR", None)
        else:
            os.environ["SKY_STATE_DIR"] = self.saved
        self.tmp.cleanup()

    def write_run(self, run_id, events):
        directory = self.root / run_id
        directory.mkdir(parents=True)
        (directory / "events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
        )

    def start(self, run_id, task, timestamp, outcome=None):
        events = [{"t": timestamp, "kind": "run.start", "role": "reviewer",
                   "task": task, "kb": "local"}]
        if outcome is not None:
            events.append({"t": timestamp + 1, "kind": "run.finish", "outcome": outcome})
        self.write_run(run_id, events)

    def test_empty_history(self):
        code, out, err = run_cli("runs")
        self.assertEqual((code, out, err), (0, "no run records\n", ""))

    def test_lists_newest_first_and_shows_summary(self):
        self.start("run-old", "old task", 1, "success")
        self.start("run-new", "new task", 2, "failed")
        code, out, err = run_cli("runs")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertLess(out.index("run-new"), out.index("run-old"))
        self.assertIn("reviewer  new task  local  failed", out)

    def test_show_prints_events_in_order(self):
        self.start("run-one", "task", 1, "success")
        code, out, err = run_cli("runs", "show", "run-one")
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertLess(out.index('"kind": "run.start"'), out.index('"kind": "run.finish"'))

    def test_unfinished_run_is_explicit(self):
        self.start("run-open", "still running", 1)
        code, out, _ = run_cli("runs")
        self.assertEqual(code, 0)
        self.assertIn("unfinished", out)

    def test_unknown_id_and_path_traversal_are_rejected(self):
        code, _, err = run_cli("runs", "show", "missing")
        self.assertEqual(code, 1)
        self.assertIn("run not found", err)
        code, _, err = run_cli("runs", "show", "../events.jsonl")
        self.assertEqual(code, 1)
        self.assertIn("invalid run id", err)

    def test_malformed_record_is_reported(self):
        self.write_run("run-bad", [{"kind": "run.start"}])
        (self.root / "run-bad" / "events.jsonl").write_text("not json\n", encoding="utf-8")
        code, _, err = run_cli("runs")
        self.assertEqual(code, 1)
        self.assertIn("malformed event", err)


if __name__ == "__main__":
    unittest.main()
