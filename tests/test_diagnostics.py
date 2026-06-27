from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.budget import analyze_tool_budget
from save_the_token.context_budget import plan_context_budget
from save_the_token.cli import main
from save_the_token.diagnostics import build_diagnostic_report
from save_the_token.models import (
    ConfigSource,
    McpServerConfig,
    ProbeResult,
    ScanResult,
    ToolSchema,
)


class DiagnosticsTests(unittest.TestCase):
    def test_report_is_sufficient_when_config_probe_and_budget_evidence_exist(
        self,
    ) -> None:
        server = _server("github")
        tools = (ToolSchema(name="issues_list", input_schema={"type": "object"}),)
        probe = ProbeResult(server=server, ok=True, initialized=True, tools=tools)
        budget = analyze_tool_budget(server, tools, budget_tokens=100)
        scan = ScanResult(sources=(server.source,), servers=(server,), findings=())

        report = build_diagnostic_report(scan, (probe,), (budget,))

        self.assertEqual(report.status, "sufficient")
        self.assertFalse(report.missing_facts)
        self.assertTrue(report.claims)
        self.assertTrue(all(claim.evidence_ids for claim in report.claims))

    def test_report_marks_missing_runtime_evidence_as_insufficient(self) -> None:
        server = _server("github")
        scan = ScanResult(sources=(server.source,), servers=(server,), findings=())

        report = build_diagnostic_report(scan, (), ())

        self.assertEqual(report.status, "insufficient")
        self.assertIn(
            "Runtime probe evidence is missing for github.", report.missing_facts
        )

    def test_report_includes_missing_instruction_evidence_when_context_budget_is_insufficient(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Policy\n" + ("Run tests.\n" * 200), encoding="utf-8"
            )
            server = _server("github")
            tools = (ToolSchema(name="issues_list", input_schema={"type": "object"}),)
            probe = ProbeResult(server=server, ok=True, initialized=True, tools=tools)
            budget = analyze_tool_budget(server, tools, budget_tokens=100)
            scan = ScanResult(sources=(server.source,), servers=(server,), findings=())
            context_budget = plan_context_budget(
                root, config_sources=scan.sources, budget_tokens=10
            )

            report = build_diagnostic_report(
                scan,
                (probe,),
                (budget,),
                context_budget=context_budget,
            )

        self.assertEqual(report.status, "insufficient")
        self.assertTrue(report.context_budget.preserves_orchestrator_baseline)
        self.assertTrue(
            any("Instruction evidence skipped" in fact for fact in report.missing_facts)
        )

    def test_report_is_unanswerable_without_supported_config_sources(self) -> None:
        report = build_diagnostic_report(
            ScanResult(sources=(), servers=(), findings=()), (), ()
        )

        self.assertEqual(report.status, "unanswerable")
        self.assertIn("No supported MCP config source was found.", report.missing_facts)

    def test_report_cli_emits_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--root",
                        tmp,
                        "--home",
                        str(Path(tmp) / "home"),
                        "--timeout",
                        "0.1",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "unanswerable")
        self.assertIn("evidence", payload)

    def test_report_cli_accepts_context_budget_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Policy\n" + ("Run tests.\n" * 200), encoding="utf-8"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "report",
                        "--root",
                        str(root),
                        "--home",
                        str(root / "home"),
                        "--timeout",
                        "0.1",
                        "--context-budget",
                        "10",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertIn("context_budget", payload)
        self.assertTrue(payload["context_budget"]["skipped"])
        self.assertEqual(
            len(payload["feedback_queries"]), len(set(payload["feedback_queries"]))
        )


def _server(server_id: str) -> McpServerConfig:
    return McpServerConfig(
        source=ConfigSource(Path("config.toml"), "codex", "project"),
        server_id=server_id,
        command="fake",
    )


if __name__ == "__main__":
    unittest.main()
