from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.budget import analyze_tool_budget, codex_enabled_tools_snippet
from save_the_token.models import ConfigSource, McpServerConfig, ToolSchema


class BudgetTests(unittest.TestCase):
    def test_measures_schema_surface_and_flags_over_budget(self) -> None:
        server = _server("wide")
        tools = tuple(
            ToolSchema(
                name=f"tool_{index}",
                description="x" * 120,
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            )
            for index in range(5)
        )

        report = analyze_tool_budget(server, tools, budget_tokens=20)

        self.assertEqual(report.total_tools, 5)
        self.assertGreater(report.estimated_tokens, 20)
        self.assertTrue(report.over_budget)
        self.assertLess(len(report.recommended_enabled_tools), 5)
        self.assertIn("enabled_tools", report.codex_toml_snippet)

    def test_respects_existing_enabled_tools(self) -> None:
        server = _server("github", enabled_tools=("issues_list",))
        tools = (
            ToolSchema(name="issues_list", input_schema={"type": "object"}),
            ToolSchema(name="pulls_list", input_schema={"type": "object"}),
        )

        report = analyze_tool_budget(server, tools, budget_tokens=1)

        self.assertEqual(report.recommended_enabled_tools, ("issues_list",))

    def test_task_query_prioritizes_relevant_tools(self) -> None:
        server = _server("github")
        tools = (
            ToolSchema(name="repo_status", description="Show repository status"),
            ToolSchema(name="issues_create", description="Create a GitHub issue"),
            ToolSchema(name="pulls_merge", description="Merge a pull request"),
        )

        report = analyze_tool_budget(
            server, tools, budget_tokens=20, task_query="create issue"
        )

        self.assertEqual(report.recommended_enabled_tools, ("issues_create",))
        issue_item = next(item for item in report.items if item.name == "issues_create")
        self.assertGreater(issue_item.relevance_score, 0)
        self.assertEqual(issue_item.matched_terms, ("create", "issue"))

    def test_task_query_falls_back_to_budget_when_no_tool_matches(self) -> None:
        server = _server("github")
        tools = (
            ToolSchema(name="repo_status", description="Show repository status"),
            ToolSchema(name="pulls_merge", description="Merge a pull request"),
        )

        report = analyze_tool_budget(
            server, tools, budget_tokens=20, task_query="calendar event"
        )

        self.assertTrue(report.recommended_enabled_tools)
        self.assertTrue(all(item.relevance_score == 0 for item in report.items))

    def test_quotes_dotted_toml_server_ids(self) -> None:
        snippet = codex_enabled_tools_snippet("github.enterprise", ("issues_list",))

        self.assertIn('[mcp_servers."github.enterprise"]', snippet)

    def test_generates_json_enabled_tools_snippet_for_mcp_json_clients(self) -> None:
        server = _server("github", source_client="vscode")
        tools = (
            ToolSchema(name="issues_list", input_schema={"type": "object"}),
            ToolSchema(name="pulls_list", input_schema={"type": "object"}),
        )

        report = analyze_tool_budget(
            server, tools, budget_tokens=100, task_query="issues"
        )

        self.assertEqual(report.client_snippet_format, "json")
        self.assertIn('"mcpServers"', report.client_snippet)
        self.assertIn('"enabledTools"', report.client_snippet)
        self.assertIn('"issues_list"', report.client_snippet)

    def test_defers_claude_enabled_tools_snippet_strategy(self) -> None:
        server = _server("github", source_client="claude-code")
        tools = (ToolSchema(name="issues_list", input_schema={"type": "object"}),)

        report = analyze_tool_budget(
            server, tools, budget_tokens=100, task_query="issues"
        )

        self.assertEqual(report.client_snippet_format, "deferred")
        self.assertIn("Claude", report.client_snippet)
        self.assertIn("deferred", report.client_snippet.lower())


def _server(
    server_id: str,
    enabled_tools: tuple[str, ...] = (),
    source_client: str = "codex",
) -> McpServerConfig:
    return McpServerConfig(
        source=ConfigSource(Path("config.toml"), source_client, "project"),
        server_id=server_id,
        command="fake",
        enabled_tools=enabled_tools,
    )


if __name__ == "__main__":
    unittest.main()
