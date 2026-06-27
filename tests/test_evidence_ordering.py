from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.cli import main
from save_the_token.evidence_ordering import order_prompt_evidence
from save_the_token.instruction_routing import route_instruction_sections
from save_the_token.prompt_compression import compress_instruction_routes


class EvidenceOrderingTests(unittest.TestCase):
    def test_orders_safety_and_task_evidence_first_with_lead_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "AGENTS.md"
            path.write_text(
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
            routes = route_instruction_sections(root, task_query="unit tests")
            compression = compress_instruction_routes(routes)
            ordered = order_prompt_evidence(compression)

        headings = [item.heading_path for item in ordered.ordered_items]
        self.assertEqual(headings[:2], ["Safety", "Tests"])
        self.assertEqual(ordered.ordered_items[0].placement, "front")
        self.assertIn("Safety", ordered.lead_digest)
        self.assertIn("Tests", ordered.lead_digest)
        self.assertTrue(ordered.ordering_rationale)

    def test_uses_recency_after_priority_and_stable_tie_breaker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "OLDER.md"
            newer = root / "NEWER.md"
            older.write_text("# Tests\nRun tests.\n", encoding="utf-8")
            newer.write_text("# Tests\nRun tests.\n", encoding="utf-8")
            os.utime(older, (1_700_000_000, 1_700_000_000))
            os.utime(newer, (1_800_000_000, 1_800_000_000))

            routes = route_instruction_sections(
                root,
                task_query="tests",
                fallback_instruction_names=("OLDER.md", "NEWER.md"),
            )
            compression = compress_instruction_routes(routes)
            ordered = order_prompt_evidence(compression)

            tied_a = root / "A.md"
            tied_b = root / "B.md"
            tied_a.write_text("# Tests\nRun tests.\n", encoding="utf-8")
            tied_b.write_text("# Tests\nRun tests.\n", encoding="utf-8")
            os.utime(tied_a, (1_700_000_000, 1_700_000_000))
            os.utime(tied_b, (1_700_000_000, 1_700_000_000))
            tied_routes = route_instruction_sections(
                root,
                task_query="tests",
                fallback_instruction_names=("B.md", "A.md"),
            )
            tied = order_prompt_evidence(compress_instruction_routes(tied_routes))

        self.assertTrue(ordered.ordered_items[0].source.endswith("NEWER.md"))
        tied_sources = [Path(item.source).name for item in tied.ordered_items]
        self.assertEqual(tied_sources, sorted(tied_sources))

    def test_report_cli_emits_evidence_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Safety\nNever leak secrets.\n# Tests\nRun unit tests.\n",
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
                        "--order-evidence",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertIn("prompt_compression", payload)
        self.assertIn("evidence_order", payload)
        self.assertTrue(payload["evidence_order"]["lead_digest"])
        self.assertTrue(payload["evidence_order"]["ordered_items"])


if __name__ == "__main__":
    unittest.main()
