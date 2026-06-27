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
from save_the_token.evaluation import evaluate_token_budget


class EvaluationTests(unittest.TestCase):
    def test_compares_full_selected_compressed_and_reordered_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "\n".join(
                    (
                        "# Release",
                        "Publish release notes.",
                        "# Safety",
                        "Never leak secrets.",
                        "# Tests",
                        "Run unit tests before final.",
                        "python -m unittest discover -s tests -v",
                    )
                ),
                encoding="utf-8",
            )

            report = evaluate_token_budget(root, task_query="unit tests")

        variants = {variant.name: variant for variant in report.variants}
        self.assertEqual(
            set(variants),
            {
                "full_context",
                "selected_context",
                "compressed_context",
                "reordered_context",
            },
        )
        self.assertGreaterEqual(
            variants["full_context"].estimated_tokens,
            variants["selected_context"].estimated_tokens,
        )
        self.assertGreaterEqual(
            variants["selected_context"].estimated_tokens,
            variants["compressed_context"].estimated_tokens,
        )
        self.assertEqual(variants["compressed_context"].selected_evidence_recall, 1.0)
        self.assertEqual(variants["reordered_context"].sufficiency_status, "sufficient")
        self.assertFalse(report.regressions)

    def test_reports_regression_when_compression_drops_required_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "\n".join(
                    (
                        "# Deploy",
                        "Deploy checklist.",
                        "deploy step one",
                        "deploy step two",
                        "deploy step three",
                        "deploy step four",
                        "deploy step five",
                        "deploy step six",
                        "prod approval required",
                    )
                ),
                encoding="utf-8",
            )

            report = evaluate_token_budget(root, task_query="deploy prod")

        compressed = next(
            variant
            for variant in report.variants
            if variant.name == "compressed_context"
        )
        reordered = next(
            variant
            for variant in report.variants
            if variant.name == "reordered_context"
        )
        self.assertLess(compressed.selected_evidence_recall, 1.0)
        self.assertEqual(reordered.sufficiency_status, "insufficient")
        self.assertGreater(reordered.missing_fact_count, 0)
        self.assertTrue(
            any("compressed_context dropped" in item for item in report.regressions)
        )

    def test_eval_cli_emits_evaluation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Tests\nRun unit tests before final.\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["eval", "--root", str(root), "--task", "unit tests"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["task_query"], "unit tests")
        self.assertTrue(payload["variants"])
        self.assertEqual(payload["regressions"], [])

    def test_eval_cli_can_include_guidance_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONTRIBUTING.md").write_text(
                "# Tests\nRun unit tests with pytest.\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "eval",
                        "--root",
                        str(root),
                        "--task",
                        "unit tests",
                        "--include-guidance",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        variants = {variant["name"]: variant for variant in payload["variants"]}
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            variants["selected_context"]["sufficiency_status"], "sufficient"
        )

    def test_eval_cli_can_include_nested_instruction_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "services" / "api"
            nested.mkdir(parents=True)
            (nested / "CLAUDE.md").write_text(
                "# Tests\nRun api unit tests with pytest.\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "eval",
                        "--root",
                        str(root),
                        "--task",
                        "api unit tests",
                        "--include-nested-instructions",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        variants = {variant["name"]: variant for variant in payload["variants"]}
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            variants["selected_context"]["sufficiency_status"], "sufficient"
        )


if __name__ == "__main__":
    unittest.main()
