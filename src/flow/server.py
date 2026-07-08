"""OPUS FLOW F0 — MCP-Server: read-only Tools ueber MCP (Tool-Broker-Schicht, §2).

Ehrliche Abweichung von der Spec: die Spec nennt ACP als UI-Transport; der ACP-Host in OPUS DECK
ist bewusst zurueckgestellt. MCP IST die Tool-Broker-Schicht (§2) und wird bereits im OPUS-System
genutzt (OPUS PRIME EX, Second Brain) — F0 exponiert die read-Tools daher ueber MCP. write/exec/ui
(mit Permission-Gate) folgen ab F1.

Scope aus Env `FLOW_ROOT` (Default: aktuelles Verzeichnis). `mcp` ist optional (Extra [mcp]),
lazy importiert -> Tool-Logik + Tests laufen ohne das SDK.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §2 (Broker), §3.2 (read-Tools), §8 F0
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.flow import tools
from src.flow.scope import Scope

_DEFAULT_ROOT = Path.cwd()


def _scope_from_env() -> Scope:
    """Scope: Env FLOW_ROOT > aktuelles Verzeichnis."""
    return Scope.of(os.environ.get("FLOW_ROOT") or str(_DEFAULT_ROOT))


def build_server(scope: Scope | None = None) -> Any:
    """FastMCP-Server 'opus-flow' mit den read-Tools. `mcp` lazy importiert."""
    from mcp.server.fastmcp import FastMCP

    aktiver = scope or _scope_from_env()
    server = FastMCP("opus-flow")

    @server.tool()
    def flow_list_files(pfad: str) -> dict[str, Any]:
        """Verzeichnis auflisten (read, scope-gated)."""
        return tools.fs_list_files(aktiver, pfad).as_dict()

    @server.tool()
    def flow_read_file(pfad: str) -> dict[str, Any]:
        """Datei lesen (read, scope-gated, redigiert, truncated)."""
        return tools.fs_read_file(aktiver, pfad).as_dict()

    @server.tool()
    def flow_git_status(repo: str) -> dict[str, Any]:
        """git status strukturiert (read, scope-gated)."""
        return tools.git_status(aktiver, repo).as_dict()

    @server.tool()
    def flow_git_diff(repo: str) -> dict[str, Any]:
        """git diff --stat (read, scope-gated)."""
        return tools.git_diff(aktiver, repo).as_dict()

    return server


def main() -> int:
    build_server().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
