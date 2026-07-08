"""FlowDaemon — Kernlogik: run → (Gate) → pending → approve → execute → audit.

Trennt die Wirk-Logik vom HTTP (testbar). `read`-Tools laufen sofort (auto, auditiert). `exec`/
`write`/`ui` erzeugen eine **PENDING-Aktion**, die erst nach menschlicher Freigabe ausgeführt wird —
das Gate ist vom Agenten NICHT umgehbar (§5.8), Tools sind die einzige Wirk-Schnittstelle.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §4 (Approve→Execute), §5 (Gate), §6 (Audit)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.flow import gate, registry, shell
from src.flow.audit import AuditLog
from src.flow.scope import Scope, ScopeError


@dataclass
class FlowDaemon:
    scope: Scope
    audit: AuditLog
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)

    def run(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """read → sofort ausführen (auto); exec/write/ui → PENDING (braucht Freigabe)."""
        spec = registry.REGISTRY.get(tool)
        if spec is None:
            return {"fehler": f"Unbekanntes Tool: {tool}"}
        if gate.braucht_freigabe(spec.wirkungsklasse):
            pid = uuid.uuid4().hex[:12]
            self.pending[pid] = {
                "id": pid, "tool": tool, "args": args,
                "wirkungsklasse": spec.wirkungsklasse,
            }
            return {"pending": self.pending[pid]}
        return {"ergebnis": self._execute(tool, args, "auto")}

    def approve(self, pid: str) -> dict[str, Any]:
        """Menschliche Freigabe → Ausführung der PENDING-Aktion."""
        aktion = self.pending.pop(pid, None)
        if aktion is None:
            return {"fehler": "Unbekannte oder bereits erledigte Freigabe."}
        return {"ergebnis": self._execute(aktion["tool"], aktion["args"], "user")}

    def reject(self, pid: str) -> dict[str, Any]:
        """PENDING-Aktion verwerfen (kein Execute)."""
        return {"ok": self.pending.pop(pid, None) is not None}

    def dry_run(self, plan: list[dict[str, Any]]) -> dict[str, Any]:
        """Validiere jeden Plan-Schritt gegen Scope + Allowlist — OHNE Ausfuehrung (§4 Dry-Run).

        Zeigt vor jeder Wirkung, was laufen wuerde und was (warum) blockiert waere.
        """
        schritte: list[dict[str, Any]] = []
        for step in plan:
            tool = str(step.get("tool", ""))
            roh = step.get("args")
            args: dict[str, Any] = roh if isinstance(roh, dict) else {}
            spec = registry.REGISTRY.get(tool)
            if spec is None:
                schritte.append({"tool": tool, "ok": False, "hinweis": "Unbekanntes Tool"})
                continue
            ok, hinweis = self._validate(spec, args)
            schritte.append({
                "tool": tool, "args": args, "wirkungsklasse": spec.wirkungsklasse,
                "braucht_freigabe": gate.braucht_freigabe(spec.wirkungsklasse),
                "ok": ok, "hinweis": hinweis,
            })
        return {"dry_run": schritte}

    def _validate(self, spec: registry.ToolSpec, args: dict[str, Any]) -> tuple[bool, str]:
        """Statische Pruefung eines Schritts (kein Nebeneffekt)."""
        if spec.name == "shell.execute_powershell":
            grund = shell.pruefe_kommando(str(args.get("command", "")))
            return (grund is None, grund or "Kommando erlaubt (Allowlist) — Freigabe noetig")
        pfad = args.get("pfad") if args.get("pfad") is not None else args.get("repo")
        if pfad is not None:
            try:
                self.scope.resolve_within(str(pfad))
            except ScopeError as exc:
                return (False, str(exc))
            return (True, "im Scope")
        return (True, "ok")

    def _execute(self, tool: str, args: dict[str, Any], freigabe: str) -> dict[str, Any]:
        start = time.monotonic()
        ergebnis = registry.dispatch(tool, self.scope, args)
        dauer_ms = int((time.monotonic() - start) * 1000)
        self.audit.schreibe(
            tool=tool, wirkungsklasse=ergebnis.wirkungsklasse, args=args, freigabe=freigabe,
            ok=ergebnis.ok, ergebnis=ergebnis.data if ergebnis.ok else ergebnis.fehler,
            dauer_ms=dauer_ms,
        )
        return ergebnis.as_dict()
