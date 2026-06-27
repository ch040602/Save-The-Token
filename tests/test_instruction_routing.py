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
from save_the_token.instruction_routing import route_instruction_sections


class InstructionRoutingTests(unittest.TestCase):
    def test_routes_task_to_relevant_sections_and_records_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "\n".join(
                    (
                        "# Safety",
                        "Never leak secrets.",
                        "# Tests",
                        "Run unit tests before final.",
                        "# Release",
                        "Publish a changelog.",
                    )
                ),
                encoding="utf-8",
            )

            report = route_instruction_sections(
                root, task_query="fix failing unit tests"
            )

        selected_headings = [
            section.heading_path for section in report.selected_sections
        ]
        skipped_headings = [section.heading_path for section in report.skipped_sections]
        self.assertEqual(report.original_task, "fix failing unit tests")
        self.assertTrue(report.preserves_orchestrator_baseline)
        self.assertIn("Tests", selected_headings)
        self.assertIn("Safety", selected_headings)
        self.assertIn("Release", skipped_headings)
        self.assertTrue(report.lineage)
        self.assertTrue(
            all(item.original_task == report.original_task for item in report.lineage)
        )

    def test_routes_fallback_instruction_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TEAM_GUIDE.md").write_text(
                "# Review\nUse review-driven development for implementation.",
                encoding="utf-8",
            )

            report = route_instruction_sections(
                root,
                task_query="implementation review",
                fallback_instruction_names=("TEAM_GUIDE.md",),
            )

        self.assertEqual(len(report.selected_sections), 1)
        self.assertTrue(report.selected_sections[0].source.endswith("TEAM_GUIDE.md"))

    def test_redacts_secret_like_lines_and_omits_unrelated_long_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "\n".join(
                    (
                        "# Secrets",
                        "API_TOKEN=super-secret-token",
                        "Authorization: Bearer abc",
                        "# Tests",
                        "Run pytest for failing tests.",
                        "# Long Policy",
                        "Ignore this unrelated release policy. " * 40,
                    )
                ),
                encoding="utf-8",
            )

            report = route_instruction_sections(root, task_query="failing tests")

        rendered = json.dumps([section.snippet for section in report.selected_sections])
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("super-secret-token", rendered)
        self.assertNotIn("Bearer abc", rendered)
        self.assertNotIn("unrelated release policy", rendered)

    def test_report_cli_emits_instruction_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Tests\nRun unit tests.\n# Release\nPublish notes.\n",
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
                        str(root / "home"),
                        "--timeout",
                        "0.1",
                        "--task",
                        "unit tests",
                        "--route-instructions",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertIn("instruction_routes", payload)
        self.assertEqual(payload["instruction_routes"]["original_task"], "unit tests")
        self.assertTrue(payload["instruction_routes"]["selected_sections"])
        self.assertTrue(payload["instruction_routes"]["skipped_sections"])

    def test_guidance_sources_are_opt_in_and_report_source_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONTRIBUTING.md").write_text(
                "# Tests\nRun unit tests with pytest.\n",
                encoding="utf-8",
            )
            (root / ".github").mkdir()
            (root / ".github" / "copilot-instructions.md").write_text(
                "# Security\nReview authentication changes carefully.\n",
                encoding="utf-8",
            )

            default_report = route_instruction_sections(root, task_query="unit tests")
            guidance_report = route_instruction_sections(
                root,
                task_query="unit tests",
                include_guidance_sources=True,
            )

        self.assertFalse(default_report.selected_sections)
        self.assertEqual(
            default_report.missing_facts,
            ("No instruction section evidence was found.",),
        )
        self.assertEqual(len(guidance_report.selected_sections), 2)
        self.assertEqual(
            {section.source_kind for section in guidance_report.selected_sections},
            {"developer-guidance"},
        )
        self.assertTrue(
            all(
                lineage.source_kind == "developer-guidance"
                for lineage in guidance_report.lineage
            )
        )

    def test_report_cli_can_include_guidance_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONTRIBUTING.md").write_text(
                "# Tests\nRun unit tests with pytest.\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(
                    [
                        "report",
                        "--root",
                        str(root),
                        "--home",
                        str(root / "home"),
                        "--timeout",
                        "0.1",
                        "--task",
                        "unit tests",
                        "--route-instructions",
                        "--include-guidance",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        selected = payload["instruction_routes"]["selected_sections"]
        self.assertTrue(selected)
        self.assertEqual(selected[0]["source_kind"], "developer-guidance")

    def test_nested_instruction_files_are_opt_in_and_preserve_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "packages" / "api"
            nested.mkdir(parents=True)
            (root / "AGENTS.md").write_text(
                "# Release\nPublish release notes.\n",
                encoding="utf-8",
            )
            (nested / "AGENTS.md").write_text(
                "# Tests\nRun api unit tests with pytest.\n",
                encoding="utf-8",
            )
            (nested / "CLAUDE.md").write_text(
                "# Security\nReview api authorization changes.\n",
                encoding="utf-8",
            )

            root_only = route_instruction_sections(root, task_query="api unit tests")
            nested_report = route_instruction_sections(
                root,
                task_query="api unit tests",
                include_nested_instructions=True,
            )

        self.assertFalse(
            any("packages" in section.source for section in root_only.selected_sections)
        )
        selected_sources = [
            section.source for section in nested_report.selected_sections
        ]
        self.assertTrue(
            any(
                source.endswith("packages\\api\\AGENTS.md")
                or source.endswith("packages/api/AGENTS.md")
                for source in selected_sources
            )
        )
        self.assertTrue(
            any(
                lineage.scope_path == "packages/api"
                and lineage.source_kind == "nested-instruction"
                for lineage in nested_report.lineage
            )
        )
        self.assertTrue(
            any(section.scope_depth == 2 for section in nested_report.selected_sections)
        )

    def test_nested_instruction_traversal_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(3):
                target = root / f"pkg{index}"
                target.mkdir()
                (target / "AGENTS.md").write_text(
                    f"# Tests\nRun pkg{index} tests.\n",
                    encoding="utf-8",
                )

            report = route_instruction_sections(
                root,
                task_query="tests",
                include_nested_instructions=True,
                max_nested_instruction_files=1,
            )

        nested_sections = [
            section
            for section in report.selected_sections + report.skipped_sections
            if section.source_kind == "nested-instruction"
        ]
        self.assertEqual(len(nested_sections), 1)


if __name__ == "__main__":
    unittest.main()
