from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.benchmark import build_benchmark_report, render_markdown_report
from save_the_token.cli import main


class BenchmarkTests(unittest.TestCase):
    def test_static_smoke_fixture_stays_small_and_successful(self) -> None:
        root = Path(__file__).parent / "fixtures" / "benchmark-smoke"
        report = build_benchmark_report(
            root / "repos",
            task_queries=("unit tests",),
            repo_commits_path=root / "repo-commits.json",
        )

        self.assertEqual(report["summary"]["total_cases"], 2)
        self.assertEqual(report["summary"]["eligible_full_sufficient_cases"], 1)
        self.assertEqual(report["summary"]["successful_reduced_cases"], 1)
        self.assertEqual(report["rows"][0]["repo"], "owner/good")
        self.assertLess(report["rows"][0]["full_tokens"], 100)

    def test_builds_strict_benchmark_summary_with_caveats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repos = root / "repos"
            repos.mkdir()
            repo_a = repos / "owner__good"
            repo_a.mkdir()
            (repo_a / "AGENTS.md").write_text(
                "# Tests\nRun unit tests before final.\n# Release\nPublish notes.\n",
                encoding="utf-8",
            )
            repo_b = repos / "owner__missing"
            repo_b.mkdir()
            (repo_b / "AGENTS.md").write_text(
                "# Release\nPublish notes.\n",
                encoding="utf-8",
            )
            commits = root / "repo-commits.json"
            commits.write_text(
                json.dumps(
                    [
                        {"repo": "owner/good", "commit": "abc123"},
                        {"repo": "owner/missing", "commit": "def456"},
                    ]
                ),
                encoding="utf-8",
            )

            report = build_benchmark_report(
                repos,
                task_queries=("unit tests",),
                repo_commits_path=commits,
            )

        self.assertEqual(report["summary"]["total_cases"], 2)
        self.assertEqual(report["summary"]["eligible_full_sufficient_cases"], 1)
        self.assertEqual(report["summary"]["successful_reduced_cases"], 1)
        self.assertEqual(report["rows"][0]["repo"], "owner/good")
        self.assertEqual(report["rows"][0]["commit"], "abc123")
        self.assertIn("Savings are counted only", report["caveats"][0])
        self.assertIn("benchmark_options", report)

    def test_cli_writes_json_and_markdown_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repos = root / "repos"
            repos.mkdir()
            repo = repos / "owner__good"
            repo.mkdir()
            (repo / "AGENTS.md").write_text(
                "# Tests\nRun unit tests before final.\n# Release\nPublish notes.\n",
                encoding="utf-8",
            )
            json_out = root / "benchmark.json"
            markdown_out = root / "benchmark.md"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "benchmark",
                        "--repos-dir",
                        str(repos),
                        "--task",
                        "unit tests",
                        "--json-out",
                        str(json_out),
                        "--markdown-out",
                        str(markdown_out),
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(json_out.exists())
            self.assertTrue(markdown_out.exists())
            self.assertEqual(payload["summary"]["successful_reduced_cases"], 1)
            self.assertIn(
                "| repo | task | best variant |",
                markdown_out.read_text(encoding="utf-8"),
            )

    def test_markdown_report_includes_caveats_even_without_successes(self) -> None:
        report = {
            "summary": {
                "total_cases": 1,
                "eligible_full_sufficient_cases": 0,
                "successful_reduced_cases": 0,
                "success_rate_all_cases_pct": 0.0,
                "weighted_saving_successes_pct": None,
            },
            "rows": [],
            "caveats": ("No safe savings.",),
        }

        markdown = render_markdown_report(report)

        self.assertIn("No safe savings.", markdown)
        self.assertIn("successful reduced cases", markdown)

    def test_benchmark_can_include_nested_instruction_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repos = root / "repos"
            repos.mkdir()
            repo = repos / "owner__nested"
            nested = repo / "packages" / "api"
            nested.mkdir(parents=True)
            (nested / "AGENTS.md").write_text(
                "# Tests\nRun api unit tests with pytest.\n",
                encoding="utf-8",
            )

            root_only = build_benchmark_report(repos, task_queries=("api tests",))
            nested_report = build_benchmark_report(
                repos,
                task_queries=("api tests",),
                include_nested_instructions=True,
            )

        self.assertEqual(root_only["summary"]["eligible_full_sufficient_cases"], 0)
        self.assertEqual(nested_report["summary"]["eligible_full_sufficient_cases"], 1)
        self.assertIn("root-level instruction", root_only["caveats"][-1])
        self.assertIn("nested instruction", nested_report["caveats"][-1])


if __name__ == "__main__":
    unittest.main()
