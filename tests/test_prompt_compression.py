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
from save_the_token.prompt_compression import compress_instruction_routes


class PromptCompressionTests(unittest.TestCase):
    def test_compresses_selected_instruction_sections_and_preserves_required_facts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "\n".join(
                    (
                        "# Tests",
                        "Run pytest before final.",
                        "Always include failing test names in the report.",
                        "Background prose that is unrelated to tests. " * 30,
                        "python -m unittest discover -s tests -v",
                        "# Release",
                        "Publish release notes.",
                    )
                ),
                encoding="utf-8",
            )
            routes = route_instruction_sections(root, task_query="failing tests")
            report = compress_instruction_routes(routes)

        self.assertEqual(len(report.items), 1)
        item = report.items[0]
        self.assertTrue(item.citation_id)
        self.assertLess(item.compressed_tokens, item.original_tokens)
        self.assertLess(item.compression_ratio, 1.0)
        self.assertIn("# Tests", item.compressed_text)
        self.assertIn("Always include failing test names", item.compressed_text)
        self.assertIn("python -m unittest discover", item.compressed_text)
        self.assertNotIn("Background prose", item.compressed_text)
        self.assertTrue(item.required_facts_preserved)
        self.assertFalse(report.missing_facts)

    def test_reports_missing_compressible_evidence_when_no_sections_are_selected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            routes = route_instruction_sections(Path(tmp), task_query="tests")
            report = compress_instruction_routes(routes)

        self.assertIn(
            "No selected instruction sections were available for compression.",
            report.missing_facts,
        )
        self.assertEqual(report.original_tokens, 0)
        self.assertEqual(report.compressed_tokens, 0)

    def test_report_cli_emits_prompt_compression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Tests\n"
                "Run pytest before final.\n"
                "Background prose. "
                * 40
                + "\npython -m unittest discover -s tests -v\n"
                "# Release\nPublish notes.\n",
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
                        "tests",
                        "--compress-instructions",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertIn("instruction_routes", payload)
        self.assertIn("prompt_compression", payload)
        self.assertLess(
            payload["prompt_compression"]["compressed_tokens"],
            payload["prompt_compression"]["original_tokens"],
        )


if __name__ == "__main__":
    unittest.main()
