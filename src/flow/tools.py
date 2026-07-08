"""OPUS FLOW F0 — read-only Tools (Wirkungsklasse `read`, auto-erlaubt, §5.2).

Jedes Tool: Scope-geprueft (§5.1), **strukturierte** typisierte Ausgabe (kein Dump, §3.3),
Secret-redigiert, groessenbegrenzt, Fehler als typisiertes Ergebnis statt Crash (§3.3).
F0 wirkt NICHT — nur Lesen. write/exec/ui kommen ab F1 mit Permission-Gate.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3.2 (read-Tools), §3.3 (Tool-Kontrakt), §5 (Sicherheit)
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any

from src.flow.redact import redact
from src.flow.scope import Scope, ScopeError

_MAX_BYTES = 100_000  # Datei-/Ausgabe-Truncation
_MAX_EINTRAEGE = 1000
_GIT_TIMEOUT_S = 15


@dataclass(frozen=True)
class ToolResult:
    """Strukturiertes Tool-Ergebnis (§3.3). `wirkungsklasse` ist in F0 immer 'read'."""

    tool: str
    wirkungsklasse: str
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    fehler: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "wirkungsklasse": self.wirkungsklasse,
            "ok": self.ok,
            "data": self.data,
            "fehler": self.fehler,
        }


def _fehler(tool: str, msg: str) -> ToolResult:
    return ToolResult(tool=tool, wirkungsklasse="read", ok=False, fehler=msg)


def fs_list_files(scope: Scope, pfad: str) -> ToolResult:
    """Verzeichnis auflisten (Name/Typ/Groesse). Scope-geprueft."""
    tool = "fs.list_files"
    try:
        ziel = scope.resolve_within(pfad)
    except ScopeError as exc:
        return _fehler(tool, str(exc))
    if not ziel.exists():
        return _fehler(tool, f"Nicht gefunden: {ziel}")
    if not ziel.is_dir():
        return _fehler(tool, f"Kein Verzeichnis: {ziel}")
    eintraege: list[dict[str, Any]] = []
    for kind in sorted(ziel.iterdir(), key=lambda p: p.name):
        ist_datei = kind.is_file()
        eintraege.append({
            "name": kind.name,
            "typ": "file" if ist_datei else "dir",
            "groesse": kind.stat().st_size if ist_datei else None,
        })
        if len(eintraege) >= _MAX_EINTRAEGE:
            break
    return ToolResult(tool, "read", True, {"pfad": str(ziel), "eintraege": eintraege})


def fs_read_file(scope: Scope, pfad: str, max_bytes: int = _MAX_BYTES) -> ToolResult:
    """Datei lesen (UTF-8, binaer-sicher, truncated + redigiert). Scope-geprueft."""
    tool = "fs.read_file"
    try:
        ziel = scope.resolve_within(pfad)
    except ScopeError as exc:
        return _fehler(tool, str(exc))
    if not ziel.is_file():
        return _fehler(tool, f"Keine Datei: {ziel}")
    roh = ziel.read_bytes()
    gekuerzt = roh[:max_bytes]
    text = redact(gekuerzt.decode("utf-8", errors="replace"))
    return ToolResult(tool, "read", True, {
        "pfad": str(ziel),
        "inhalt": text,
        "truncated": len(roh) > max_bytes,
        "groesse": len(roh),
    })


def _git(args: list[str], cwd: str) -> tuple[bool, str]:
    try:
        ergebnis = subprocess.run(  # noqa: S603  (feste git-Args, cwd scope-geprueft)
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT_S, check=False,
        )
    except FileNotFoundError:
        return False, "git nicht gefunden (installiert?)"
    except subprocess.TimeoutExpired:
        return False, f"git-Timeout (> {_GIT_TIMEOUT_S}s)"
    if ergebnis.returncode != 0:
        return False, redact((ergebnis.stderr or "git-Fehler").strip())[:_MAX_BYTES]
    return True, redact(ergebnis.stdout)[:_MAX_BYTES]


def git_status(scope: Scope, repo: str) -> ToolResult:
    """`git status --porcelain --branch` strukturiert. Read-only. Scope-geprueft."""
    tool = "git.status"
    try:
        ziel = scope.resolve_within(repo)
    except ScopeError as exc:
        return _fehler(tool, str(exc))
    ok, ausgabe = _git(["status", "--porcelain", "--branch"], str(ziel))
    if not ok:
        return _fehler(tool, ausgabe)
    zeilen = ausgabe.splitlines()
    branch = zeilen[0][3:] if zeilen and zeilen[0].startswith("## ") else None
    aenderungen = [z for z in zeilen if not z.startswith("## ")]
    return ToolResult(tool, "read", True, {
        "repo": str(ziel),
        "branch": branch,
        "sauber": not aenderungen,
        "aenderungen": aenderungen,
    })


def git_diff(scope: Scope, repo: str) -> ToolResult:
    """`git diff --stat` (Uebersicht, kein voller Patch). Read-only. Scope-geprueft."""
    tool = "git.diff"
    try:
        ziel = scope.resolve_within(repo)
    except ScopeError as exc:
        return _fehler(tool, str(exc))
    ok, ausgabe = _git(["diff", "--stat"], str(ziel))
    if not ok:
        return _fehler(tool, ausgabe)
    return ToolResult(tool, "read", True, {"repo": str(ziel), "stat": ausgabe.strip()})
