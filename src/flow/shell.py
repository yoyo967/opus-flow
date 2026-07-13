"""shell.execute_powershell — gegateter Shell-Zugriff (Wirkungsklasse `exec`, §3.2/§5.3).

Gehärtet ab Tag 1: **Allowlist** (nur erlaubte Kommandos, erstes Token), **Denylist**
(Zerstörerisches hart blockiert), Timeout, keine erhöhten Rechte, Secret-Redaction der Ausgabe,
strukturiertes Ergebnis. Der Runner ist injizierbar → Tests laufen ohne echte Ausführung.

Wichtig: `exec` ist NIE auto-erlaubt — der Aufruf erzeugt eine PENDING-Aktion, die ein Mensch in
OPUS DECK freigibt (siehe Gate §5.2 + API). Diese Funktion führt erst NACH Freigabe aus.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3.2, §5.3 (PowerShell gehärtet)
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from src.flow.redact import redact
from src.flow.scope import Scope
from src.flow.tools import ToolResult

_MAX_BYTES = 100_000
_TIMEOUT_S = 30

# Allowlist: nur diese Programme (erstes Token, case-insensitive). Bewusst konservativ.
_ALLOWLIST = frozenset({
    "git", "echo", "type", "cat", "ls", "dir", "pwd",
    "node", "npm", "npx", "python", "python3", "pip",
    "get-childitem", "get-content", "get-location", "select-string", "test-path",
    "measure-object", "where-object", "select-object",
})
# Denylist (Teilstrings, case-insensitive): Zerstörerisches / Exfiltration — hart blockiert.
_DENYLIST = (
    "remove-item", "rmdir", "rd ", "del ", "erase ", "format-", "format ",
    "-recurse", "-force", "reg delete", "reg add", "new-item -force",
    "invoke-webrequest", "invoke-restmethod", "iwr ", "curl ", "wget ",
    "start-process", "stop-process", "set-executionpolicy", "; rm", "&& rm",
)

# Runner: (command, cwd, timeout) -> (returncode, stdout, stderr). Default = echtes PowerShell.
Runner = Callable[[str, str, int], "tuple[int, str, str]"]


def _powershell_runner(command: str, cwd: str, timeout: int) -> tuple[int, str, str]:
    ergebnis = subprocess.run(  # noqa: S603
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
    )
    return ergebnis.returncode, ergebnis.stdout or "", ergebnis.stderr or ""


def sicherheits_listen() -> dict[str, list[str]]:
    """Allowlist/Denylist offenlegen (Transparenz für den Security-Review, F5)."""
    return {"allowlist": sorted(_ALLOWLIST), "denylist": [d.strip() for d in _DENYLIST]}


def pruefe_kommando(command: str) -> str | None:
    """Gibt einen Ablehnungsgrund zurück, oder None wenn zulässig (Allowlist ∧ ¬Denylist)."""
    cmd = command.strip()
    if not cmd:
        return "Leeres Kommando."
    erstes = cmd.split()[0].lower().lstrip("&").strip("\"'")
    if erstes not in _ALLOWLIST:
        return f"Kommando nicht in Allowlist: '{erstes}'"
    low = cmd.lower()
    for bad in _DENYLIST:
        if bad in low:
            return f"Denylist blockiert: '{bad.strip()}'"
    return None


def shell_execute(
    scope: Scope,
    command: str,
    timeout_s: int = _TIMEOUT_S,
    runner: Runner = _powershell_runner,
) -> ToolResult:
    """Führt `command` aus — NUR wenn Allowlist ∧ ¬Denylist. Ausgabe redigiert + strukturiert."""
    tool = "shell.execute_powershell"
    grund = pruefe_kommando(command)
    if grund is not None:
        return ToolResult(tool, "exec", False, fehler=grund)
    cwd = str(scope.roots[0])
    try:
        code, out, err = runner(command.strip(), cwd, timeout_s)
    except FileNotFoundError:
        return ToolResult(tool, "exec", False, fehler="PowerShell nicht gefunden.")
    except subprocess.TimeoutExpired:
        return ToolResult(tool, "exec", False, fehler=f"Timeout (> {timeout_s}s).")
    return ToolResult(tool, "exec", code == 0, {
        "command": command.strip(),
        "returncode": code,
        "stdout": redact(out)[:_MAX_BYTES],
        "stderr": redact(err)[:_MAX_BYTES],
    })
