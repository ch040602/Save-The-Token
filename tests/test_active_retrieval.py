from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.active_retrieval import plan_active_retrieval
from save_the_token.cli import main
from save_the_token.diagnostics import build_diagnostic_report
from save_the_token.models import ConfigSource, McpServerConfig, ScanResult


class ActiveRetrievalTests(unittest.TestCase):
    def test_plans_bounded_followups_from_missing_facts(self) -> None:
        server = _server("github")
        report = build_diagnostic_report(
            ScanResult(sources=(server.source,), servers=(server,), findings=()),
            probes=(),
            budgets=(),
        )

        followups = plan_active_retrieval(
            report, original_task="triage issues", max_iterations=1
        )

        self.assertEqual(followups.original_task, "triage issues")
        self.assertEqual(followups.stop_reason, "iteration_budget_exhausted")
        self.assertEqual(followups.final_status, "insufficient")
        self.assertEqual(len(followups.steps), 1)
        self.assertIn("Runtime probe evidence", followups.steps[0].missing_fact)
        self.assertEqual(followups.steps[0].target_corpus, "runtime")
        self.assertTrue(followups.steps[0].follow_up_query)
        self.assertFalse(followups.steps[0].retrieved_evidence_ids)

    def test_stops_without_followups_for_sufficient_or_unanswerable_reports(
        self,
    ) -> None:
        unanswerable = build_diagnostic_report(
            ScanResult(sources=(), servers=(), findings=()), (), ()
        )
        followups = plan_active_retrieval(
            unanswerable, original_task="", max_iterations=3
        )

        self.assertEqual(followups.stop_reason, "unanswerable")
        self.assertEqual(followups.steps, ())
        self.assertEqual(followups.final_status, "unanswerable")

    def test_report_cli_emits_active_retrieval_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            codex = home / ".codex"
            codex.mkdir(parents=True)
            (codex / "config.toml").write_text(
                '[mcp_servers.github]\ncommand = "missing-command-for-test"\n',
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--root",
                        str(root),
                        "--home",
                        str(home),
                        "--timeout",
                        "0.1",
                        "--task",
                        "triage issues",
                        "--active-retrieval",
                        "1",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "insufficient")
        self.assertIn("active_retrieval", payload)
        self.assertEqual(payload["active_retrieval"]["final_status"], "insufficient")
        self.assertEqual(len(payload["active_retrieval"]["steps"]), 1)
        self.assertIn("missing_fact", payload["active_retrieval"]["steps"][0])


def _server(server_id: str) -> McpServerConfig:
    return McpServerConfig(
        source=ConfigSource(Path("config.toml"), "codex", "project"),
        server_id=server_id,
        command="fake",
    )


if __name__ == "__main__":
    unittest.main()
