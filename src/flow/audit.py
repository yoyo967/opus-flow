"""Append-only Audit-Log (Sicherheits-Kontrakt §6).

Jeder Tool-Aufruf wird als eine JSONL-Zeile protokolliert — **redigiert** (args + Ergebnis durch
die Secret-Redaction), mit Freigabe-Quelle (`user`/`auto`), Dauer, Erfolg. Append-only: der Agent
kann NICHT aus dem Log löschen (die API bietet kein Löschen).

# SPEC: opus-deck/spec/FLOW_STUDIO.md §6 (Audit, append-only)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.flow.redact import redact

_MAX_FELD = 4000  # Truncation je redigiertem Feld


def _kurz(obj: Any) -> str:
    return redact(json.dumps(obj, ensure_ascii=False, default=str))[:_MAX_FELD]


@dataclass(frozen=True)
class AuditLog:
    """Append-only JSONL-Audit unter `pfad`."""

    pfad: Path

    def schreibe(
        self,
        *,
        tool: str,
        wirkungsklasse: str,
        args: dict[str, Any],
        freigabe: str,
        ok: bool,
        ergebnis: Any,
        dauer_ms: int,
    ) -> dict[str, Any]:
        """Einen Audit-Eintrag anhängen (redigiert) und zurückgeben."""
        eintrag = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tool": tool,
            "wirkungsklasse": wirkungsklasse,
            "args": _kurz(args),
            "freigabe": freigabe,  # "user" | "auto"
            "ok": ok,
            "ergebnis": _kurz(ergebnis),
            "dauer_ms": dauer_ms,
        }
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        with self.pfad.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
        return eintrag

    def alle(self, limit: int = 200) -> list[dict[str, Any]]:
        """Die letzten `limit` Einträge (neueste zuletzt)."""
        if not self.pfad.exists():
            return []
        zeilen = self.pfad.read_text(encoding="utf-8").splitlines()
        eintraege: list[dict[str, Any]] = []
        for z in zeilen[-limit:]:
            if z.strip():
                eintraege.append(json.loads(z))
        return eintraege
