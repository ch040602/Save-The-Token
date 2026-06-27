from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from save_the_token.config import scan_configs


class ConfigScanTests(unittest.TestCase):
    def test_discovers_codex_project_mcp_servers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text(
                """
[mcp_servers.playwright]
command = "npx"
args = ["@playwright/mcp@latest"]
enabled_tools = ["browser_navigate"]
""".strip(),
                encoding="utf-8",
            )

            result = scan_configs(root, home=root / "home")

            self.assertEqual(len(result.sources), 1)
            self.assertEqual(len(result.servers), 1)
            self.assertEqual(result.servers[0].server_id, "playwright")
            self.assertEqual(result.servers[0].command, "npx")
            self.assertEqual(result.servers[0].enabled_tools, ("browser_navigate",))
            self.assertEqual(result.findings, ())

    def test_reports_missing_transport(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".vscode").mkdir()
            (root / ".vscode" / "mcp.json").write_text(
                json.dumps({"mcpServers": {"broken": {"args": ["server.py"]}}}),
                encoding="utf-8",
            )

            result = scan_configs(root, home=root / "home")

            self.assertEqual(result.findings[0].code, "server_missing_transport")

    def test_parses_http_headers_and_lints_unsafe_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".vscode").mkdir()
            (root / ".vscode" / "mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "remote": {
                                "url": "https://example.com/mcp",
                                "headers": {
                                    "Authorization": "Bearer token",
                                    "Bad\nName": "value",
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = scan_configs(root, home=root / "home")

            self.assertEqual(result.servers[0].headers["Authorization"], "Bearer token")
            self.assertEqual(result.findings[0].code, "unsafe_http_header")

    def test_discovers_claude_code_project_mcp_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".mcp.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "paypal": {
                                "type": "http",
                                "url": "https://mcp.paypal.com/mcp",
                                "headers": {"Authorization": "Bearer token"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = scan_configs(root, home=root / "home")

            self.assertEqual(result.sources[0].client, "claude-code")
            self.assertEqual(result.sources[0].scope, "project")
            self.assertEqual(result.servers[0].server_id, "paypal")
            self.assertEqual(result.servers[0].url, "https://mcp.paypal.com/mcp")
            self.assertEqual(result.findings, ())

    def test_discovers_claude_code_user_and_local_servers_from_claude_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            (home / ".claude.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "hubspot": {
                                "type": "http",
                                "url": "https://mcp.hubspot.com/anthropic",
                            }
                        },
                        "projects": {
                            str(root.resolve()): {
                                "mcpServers": {
                                    "stripe": {
                                        "type": "http",
                                        "url": "https://mcp.stripe.com",
                                    }
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = scan_configs(root, home=home)

            by_id = {server.server_id: server for server in result.servers}
            self.assertEqual(by_id["hubspot"].source.scope, "user")
            self.assertEqual(by_id["stripe"].source.scope, "local")
            self.assertEqual(by_id["stripe"].url, "https://mcp.stripe.com")

    def test_discovers_claude_desktop_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            config_dir = home / "AppData" / "Roaming" / "Claude"
            config_dir.mkdir(parents=True)
            (config_dir / "claude_desktop_config.json").write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "filesystem": {
                                "command": "npx",
                                "args": [
                                    "-y",
                                    "@modelcontextprotocol/server-filesystem",
                                    str(root),
                                ],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = scan_configs(root, home=home)

            self.assertEqual(result.sources[0].client, "claude-desktop")
            self.assertEqual(result.servers[0].server_id, "filesystem")
            self.assertEqual(result.servers[0].command, "npx")


if __name__ == "__main__":
    unittest.main()
