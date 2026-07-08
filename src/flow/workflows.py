"""Workflow-Speicherung (§6, F3) — bestaetigte Fluesse als wiederholbare, parametrisierbare JSON.

Ein bestaetigter Plan wird als benannter Workflow gespeichert: `{name, params, schritte}`. Beim
Wiederholen werden `${param}`-Platzhalter in den Args ersetzt; die Ausfuehrung laeuft danach durch
DIESELBEN Gates (Scope bleibt bindend) — der Store fuehrt selbst NICHTS aus, er speichert nur.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §6 (Workflow-Speicherung JSON/YAML, Replay)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SLUG = re.compile(r"[^a-z0-9]+")
_PARAM = re.compile(r"\$\{(\w+)\}")


def _slug(name: str) -> str:
    s = _SLUG.sub("-", name.lower()).strip("-")
    return s or "workflow"


def _norm_schritte(schritte: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nur tool + args (dict) uebernehmen — strukturiert, keine Fremdfelder."""
    out: list[dict[str, Any]] = []
    for s in schritte:
        if isinstance(s, dict) and s.get("tool"):
            args = s.get("args") if isinstance(s.get("args"), dict) else {}
            out.append({"tool": str(s["tool"]), "args": args})
    return out


def substituiere(schritte: list[dict[str, Any]], params: dict[str, str]) -> list[dict[str, Any]]:
    """Ersetzt ${param} in allen String-Args (rekursiv flach ueber die Args-Werte)."""
    def ersetze(wert: Any) -> Any:
        if isinstance(wert, str):
            return _PARAM.sub(lambda m: str(params.get(m.group(1), m.group(0))), wert)
        return wert

    return [
        {"tool": s["tool"], "args": {k: ersetze(v) for k, v in (s.get("args") or {}).items()}}
        for s in schritte
    ]


@dataclass(frozen=True)
class WorkflowStore:
    """JSON-Workflows unter `dir` (ein File je Workflow)."""

    dir: Path

    def speichere(
        self, name: str, schritte: list[dict[str, Any]], params: list[str] | None = None
    ) -> dict[str, Any]:
        """Einen Workflow speichern (ueberschreibt bei gleichem Slug)."""
        norm = _norm_schritte(schritte)
        if not norm:
            raise ValueError("Workflow braucht mindestens einen Schritt.")
        wf_id = _slug(name)
        eintrag = {
            "id": wf_id, "name": name.strip() or wf_id,
            "params": list(params or []), "schritte": norm,
            "erstellt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{wf_id}.json").write_text(
            json.dumps(eintrag, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return eintrag

    def liste(self) -> list[dict[str, Any]]:
        """Alle gespeicherten Workflows (id, name, params, Schrittzahl)."""
        if not self.dir.exists():
            return []
        aus: list[dict[str, Any]] = []
        for pfad in sorted(self.dir.glob("*.json")):
            obj = json.loads(pfad.read_text(encoding="utf-8"))
            aus.append({
                "id": obj["id"], "name": obj["name"],
                "params": obj.get("params", []), "schritte_n": len(obj.get("schritte", [])),
            })
        return aus

    def lies(self, wf_id: str) -> dict[str, Any] | None:
        """Einen Workflow vollstaendig lesen (oder None)."""
        pfad = self.dir / f"{_slug(wf_id)}.json"
        if not pfad.exists():
            return None
        obj: dict[str, Any] = json.loads(pfad.read_text(encoding="utf-8"))
        return obj
