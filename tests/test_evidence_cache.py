from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.evidence_cache import (
    cache_entry,
    fingerprint_file,
    fingerprint_text,
    fingerprint_tools,
    load_summary_cache,
    lookup_cached_summary,
)
from save_the_token.models import ConfigSource, McpServerConfig, ToolSchema


class EvidenceCacheTests(unittest.TestCase):
    def test_text_fingerprint_changes_with_content_and_path_scope(self) -> None:
        first = fingerprint_text(
            "AGENTS.md", "Run tests before final.", kind="instructions"
        )
        same = fingerprint_text(
            "AGENTS.md", "Run tests before final.", kind="instructions"
        )
        changed_content = fingerprint_text(
            "AGENTS.md", "Run lint before final.", kind="instructions"
        )
        changed_source = fingerprint_text(
            "sub/AGENTS.md", "Run tests before final.", kind="instructions"
        )

        self.assertEqual(first.sha256, same.sha256)
        self.assertEqual(first.estimated_tokens, same.estimated_tokens)
        self.assertNotEqual(first.sha256, changed_content.sha256)
        self.assertNotEqual(first.cache_key, changed_source.cache_key)

    def test_file_fingerprint_omits_raw_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            content = '[mcp_servers.github]\ncommand = "gh"\n'
            path.write_text(content, encoding="utf-8")

            fingerprint = fingerprint_file(path, kind="client-config")
            expected_size_bytes = len(path.read_bytes())
            expected_source = str(path.resolve())

        payload = fingerprint.to_dict()
        self.assertEqual(payload["kind"], "client-config")
        self.assertEqual(payload["source"], expected_source)
        self.assertEqual(payload["size_bytes"], expected_size_bytes)
        self.assertGreaterEqual(payload["estimated_tokens"], 1)
        self.assertIn("sha256", payload)
        self.assertNotIn("command", json.dumps(payload))

    def test_summary_cache_hit_and_miss_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            fingerprint = fingerprint_text(
                "AGENTS.md", "Run tests.", kind="instructions"
            )
            changed = fingerprint_text("AGENTS.md", "Run lint.", kind="instructions")
            path.write_text(
                json.dumps(
                    {"entries": [cache_entry(fingerprint, "test instructions")]}
                ),
                encoding="utf-8",
            )

            cache = load_summary_cache(path)
            hit = lookup_cached_summary(cache, fingerprint)
            miss = lookup_cached_summary(cache, changed)

        self.assertTrue(hit.cache_hit)
        self.assertEqual(hit.cached_summary, "test instructions")
        self.assertEqual(hit.cached_estimated_tokens, fingerprint.estimated_tokens)
        self.assertFalse(miss.cache_hit)
        self.assertIsNone(miss.cached_summary)

    def test_tool_schema_fingerprint_is_stable_and_path_scoped(self) -> None:
        server = McpServerConfig(
            source=ConfigSource(Path("mcp.json"), "vscode", "project"),
            server_id="github",
        )
        tools = (
            ToolSchema(
                name="issues_create",
                description="Create issue",
                input_schema={"type": "object", "required": ["title"]},
            ),
        )

        first = fingerprint_tools(server, tools)
        same = fingerprint_tools(server, tools)
        changed = fingerprint_tools(
            server,
            (
                ToolSchema(
                    name="issues_create",
                    description="Create issue",
                    input_schema={"type": "object", "required": ["title", "body"]},
                ),
            ),
        )

        self.assertEqual(first.sha256, same.sha256)
        self.assertNotEqual(first.sha256, changed.sha256)
        self.assertEqual(first.kind, "tools")
        self.assertIn("#github/tools-list", first.source)


if __name__ == "__main__":
    unittest.main()
