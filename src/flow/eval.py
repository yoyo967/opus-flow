"""Flow-Eval (§7/§9) — Function-Calling-Zuverlaessigkeit MESSEN statt annehmen.

Bewertet, ob ein Modell aus natuerlichsprachlichen Befehlen brauchbare Plaene erzeugt — die
Voraussetzung, bevor autonome Ketten erlaubt werden (§9). Vier deterministische Kriterien je Fall:

- ``geparst``            — nicht-leerer Schrittplan (Function-Calling ueberhaupt geglueckt).
- ``tools_gueltig``     — alle Schritt-Tools existieren in der Registry.
- ``scope_ok``          — alle Schritte bestehen den Dry-Run (Scope + Allowlist), OHNE Nebeneffekt.
- ``erwartet_getroffen`` — erwartete Tools ⊆ erzeugte Tools (nur wenn der Fall es vorgibt).

Das Modell ist injizierbar (``planner_fn``/``dry_fn``) — Tests laufen ohne echtes Modell,
die CLI verdrahtet den echten Planner + Daemon-Dry-Run.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §7 (Modelle), §9 (Messen statt annehmen)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.flow import registry

_DEFAULT_SET = Path(__file__).resolve().parents[2] / "config" / "flow_eval.json"

# befehl -> Planner-Ergebnis ({"plan": [...]} oder {"fehler": ...}); plan -> {"dry_run": [...]}
PlannerFn = Callable[[str], dict[str, Any]]
DryFn = Callable[[list[dict[str, Any]]], dict[str, Any]]


@dataclass(frozen=True)
class EvalFall:
    """Ein Eval-Fall: ein Befehl, optional die erwarteten Tools (als Trefferpruefung)."""

    befehl: str
    erwartete_tools: list[str] = field(default_factory=list)


def bewerte_plan(
    plan: list[dict[str, Any]], dry: list[dict[str, Any]], erwartete: list[str]
) -> dict[str, Any]:
    """Einen einzelnen Plan gegen die vier Kriterien bewerten (rein, kein Nebeneffekt)."""
    tools = [str(s.get("tool", "")) for s in plan]
    geparst = len(plan) > 0
    tools_gueltig = geparst and all(t in registry.REGISTRY for t in tools)
    scope_ok = bool(dry) and all(bool(s.get("ok")) for s in dry)
    erwartet: bool | None = set(erwartete) <= set(tools) if erwartete else None
    return {
        "tools": tools, "geparst": geparst, "tools_gueltig": tools_gueltig,
        "scope_ok": scope_ok, "erwartet_getroffen": erwartet,
    }


def evaluiere(faelle: list[EvalFall], planner_fn: PlannerFn, dry_fn: DryFn) -> dict[str, Any]:
    """Alle Faelle bewerten und zu Raten aggregieren (0..1)."""
    zeilen: list[dict[str, Any]] = []
    for f in faelle:
        res = planner_fn(f.befehl)
        plan = res.get("plan") or []
        dry = dry_fn(plan).get("dry_run", []) if plan else []
        zeile = bewerte_plan(plan, dry, f.erwartete_tools)
        zeile["befehl"] = f.befehl
        zeile["fehler"] = res.get("fehler")
        zeilen.append(zeile)

    n = len(zeilen)

    def rate(key: str) -> float:
        return round(sum(1 for z in zeilen if z[key]) / n, 3) if n else 0.0

    mit_erwartung = [z for z in zeilen if z["erwartet_getroffen"] is not None]
    treffer = (
        round(sum(1 for z in mit_erwartung if z["erwartet_getroffen"]) / len(mit_erwartung), 3)
        if mit_erwartung else None
    )
    summary = {
        "n": n, "geparst": rate("geparst"), "tools_gueltig": rate("tools_gueltig"),
        "scope_ok": rate("scope_ok"), "erwartet_getroffen": treffer,
    }
    return {"summary": summary, "faelle": zeilen}


def lade_faelle(pfad: str | Path | None = None) -> list[EvalFall]:
    """Eval-Satz aus JSON laden (Standard: ``config/flow_eval.json``)."""
    p = Path(pfad) if pfad else _DEFAULT_SET
    daten = json.loads(p.read_text(encoding="utf-8"))
    return [
        EvalFall(befehl=str(d["befehl"]), erwartete_tools=list(d.get("erwartete_tools", [])))
        for d in daten
    ]
