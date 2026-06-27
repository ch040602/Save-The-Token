from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.cli import main
from save_the_token.models import ConfigSource, McpServerConfig, ScanResult
from save_the_token.orchestration import plan_orchestration_advice


class OrchestrationAdviceTests(unittest.TestCase):
    def test_distinguishes_main_agent_skills_and_subagent_requests(self) -> None:
        scan = ScanResult(
            sources=(ConfigSource(Path("config.toml"), "codex", "project"),),
            servers=(_server("github"),),
            findings=(),
        )

        advice = plan_orchestration_advice(
            task_query="security review the whole codebase for token leaks",
            scan=scan,
        )

        categories = {item.category for item in advice.recommendations}
        self.assertIn("main-agent", categories)
        self.assertIn("skill-progressive-disclosure", categories)
        self.assertIn("explicit-subagent-request", categories)
        subagents = [
            item
            for item in advice.recommendations
            if item.category == "explicit-subagent-request"
        ]
        self.assertTrue(
            any("security" in item.recommendation.lower() for item in subagents)
        )
        self.assertTrue(all(item.auto_spawn is False for item in subagents))
        self.assertTrue(all(item.token_cost_warning for item in subagents))
        self.assertTrue(advice.preserves_codex_orchestrator)

    def test_report_cli_emits_orchestration_advice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                        "--task",
                        "security review",
                        "--orchestration-advice",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertIn("orchestration_advice", payload)
        self.assertTrue(payload["orchestration_advice"]["preserves_codex_orchestrator"])
        self.assertTrue(
            any(
                item["category"] == "explicit-subagent-request"
                for item in payload["orchestration_advice"]["recommendations"]
            )
        )


def _server(server_id: str) -> McpServerConfig:
    return McpServerConfig(
        source=ConfigSource(Path("config.toml"), "codex", "project"),
        server_id=server_id,
        command="fake",
    )


if __name__ == "__main__":
    unittest.main()
