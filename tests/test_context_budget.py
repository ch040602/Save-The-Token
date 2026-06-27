from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.context_budget import plan_context_budget
from save_the_token.models import ConfigSource


class ContextBudgetTests(unittest.TestCase):
    def test_measures_instruction_candidates_and_omits_raw_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents = root / "AGENTS.md"
            agents.write_text("# Policy\n" + ("Run tests.\n" * 200), encoding="utf-8")
            fallback = root / "TEAM_GUIDE.md"
            fallback.write_text("# Team\nUse review flow.\n", encoding="utf-8")

            report = plan_context_budget(
                root,
                config_sources=(),
                budget_tokens=20,
                fallback_instruction_names=("TEAM_GUIDE.md",),
            )

        all_items = report.selected + report.skipped
        agents_item = next(
            item for item in all_items if item.source.endswith("AGENTS.md")
        )
        fallback_item = next(
            item for item in all_items if item.source.endswith("TEAM_GUIDE.md")
        )
        serialized = str([item.__dict__ for item in all_items])
        self.assertGreater(agents_item.size_bytes, fallback_item.size_bytes)
        self.assertGreater(agents_item.estimated_tokens, 20)
        self.assertIn("exceeds remaining context budget", agents_item.reason)
        self.assertNotIn("Run tests", serialized)
        self.assertTrue(report.preserves_orchestrator_baseline)

    def test_selects_config_and_instruction_sources_with_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / ".codex" / "config.toml"
            config.parent.mkdir()
            config.write_text(
                '[mcp_servers.github]\ncommand = "gh"\n', encoding="utf-8"
            )
            agents = root / "AGENTS.md"
            agents.write_text("# Policy\nRun tests.\n", encoding="utf-8")

            report = plan_context_budget(
                root,
                config_sources=(ConfigSource(config, "codex", "project"),),
                budget_tokens=100,
            )

        self.assertEqual(len(report.selected), 2)
        self.assertFalse(report.skipped)
        self.assertTrue(all(item.selected for item in report.selected))
        self.assertTrue(any(item.kind == "client-config" for item in report.selected))
        self.assertTrue(any(item.kind == "instructions" for item in report.selected))

    def test_reports_missing_instruction_evidence_when_no_candidates_exist(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = plan_context_budget(
                Path(tmp), config_sources=(), budget_tokens=100
            )

        self.assertIn("No instruction evidence file was found.", report.missing_facts)
        self.assertEqual(report.total_estimated_tokens, 0)

    def test_reports_skipped_config_evidence_when_budget_is_too_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / ".codex" / "config.toml"
            config.parent.mkdir()
            config.write_text(
                '[mcp_servers.github]\ncommand = "gh"\n', encoding="utf-8"
            )

            report = plan_context_budget(
                root,
                config_sources=(ConfigSource(config, "codex", "project"),),
                budget_tokens=1,
            )

        self.assertTrue(
            any("Config evidence skipped" in fact for fact in report.missing_facts)
        )


if __name__ == "__main__":
    unittest.main()
