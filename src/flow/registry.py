"""Tool-Registry — einheitliche Metadaten + Dispatch (für API & Planner).

Bündelt alle Tools mit Name, Wirkungsklasse, Beschreibung, Parametern und Aufruf-Funktion.
Die Wirkungsklasse steuert das Gate (§5.2); die Metadaten speisen Panel + Planner.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3 (Tool-Schichten), §3.3 (Tool-Kontrakt)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.flow import gui, shell, tools
from src.flow.scope import Scope
from src.flow.tools import ToolResult


@dataclass(frozen=True)
class ToolSpec:
    name: str
    wirkungsklasse: str
    beschreibung: str
    params: tuple[str, ...]
    fn: Callable[[Scope, dict[str, Any]], ToolResult]


def _arg(args: dict[str, Any], key: str) -> str:
    wert = args.get(key)
    if wert is None:
        raise KeyError(key)
    return str(wert)


REGISTRY: dict[str, ToolSpec] = {
    "fs.list_files": ToolSpec(
        "fs.list_files", "read", "Verzeichnis auflisten", ("pfad",),
        lambda s, a: tools.fs_list_files(s, _arg(a, "pfad")),
    ),
    "fs.read_file": ToolSpec(
        "fs.read_file", "read", "Datei lesen (redigiert, truncated)", ("pfad",),
        lambda s, a: tools.fs_read_file(s, _arg(a, "pfad")),
    ),
    "git.status": ToolSpec(
        "git.status", "read", "git status strukturiert", ("repo",),
        lambda s, a: tools.git_status(s, _arg(a, "repo")),
    ),
    "git.diff": ToolSpec(
        "git.diff", "read", "git diff --stat", ("repo",),
        lambda s, a: tools.git_diff(s, _arg(a, "repo")),
    ),
    "shell.execute_powershell": ToolSpec(
        "shell.execute_powershell", "exec",
        "PowerShell-Kommando (Allowlist, Denylist, Timeout) — braucht Freigabe", ("command",),
        lambda s, a: shell.shell_execute(s, _arg(a, "command")),
    ),
    "ui.inspect": ToolSpec(
        "ui.inspect", "read", "Accessibility-Baum einer erlaubten App lesen", ("target",),
        lambda s, a: gui.ui_inspect(_arg(a, "target"), *gui.aktiv()),
    ),
    "ui.click": ToolSpec(
        "ui.click", "ui", "Element in erlaubter App klicken — braucht Freigabe",
        ("target", "selector"),
        lambda s, a: gui.ui_click(_arg(a, "target"), _arg(a, "selector"), *gui.aktiv()),
    ),
    "ui.fill": ToolSpec(
        "ui.fill", "ui", "Textfeld in erlaubter App setzen — braucht Freigabe",
        ("target", "selector", "wert"),
        lambda s, a: gui.ui_fill(
            _arg(a, "target"), _arg(a, "selector"), _arg(a, "wert"), *gui.aktiv()),
    ),
}


def liste() -> list[dict[str, Any]]:
    """Tool-Metadaten (für Panel & Planner)."""
    return [
        {"name": t.name, "wirkungsklasse": t.wirkungsklasse,
         "beschreibung": t.beschreibung, "params": list(t.params)}
        for t in REGISTRY.values()
    ]


def dispatch(name: str, scope: Scope, args: dict[str, Any]) -> ToolResult:
    """Ein Tool ausführen (Scope-geprüft in den Tools selbst). Unbekannt/fehlende Args → Fehler."""
    spec = REGISTRY.get(name)
    if spec is None:
        return ToolResult(name, "read", False, fehler=f"Unbekanntes Tool: {name}")
    try:
        return spec.fn(scope, args)
    except KeyError as exc:
        return ToolResult(name, spec.wirkungsklasse, False, fehler=f"Fehlender Parameter: {exc}")
