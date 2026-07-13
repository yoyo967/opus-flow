"""Flow-Eval-CLI — misst die Function-Calling-Zuverlaessigkeit eines Modells (§9).

    python -m apps.eval.run --root . [--model gemini-2.5-flash] [--set pfad.json] [--json]

Faehrt den Standard-Eval-Satz durch den echten Planner (Modell aus dem Katalog) und bewertet
jeden Plan deterministisch gegen Registry + Dry-Run (Scope/Allowlist) — OHNE Nebeneffekt.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §9 (Messen statt annehmen)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.flow import planner
from src.flow.audit import AuditLog
from src.flow.daemon import FlowDaemon
from src.flow.eval import evaluiere, lade_faelle
from src.flow.scope import Scope


def _scorecard(bericht: dict[str, object]) -> str:
    s = bericht["summary"]
    assert isinstance(s, dict)
    zeilen = [
        "OPUS FLOW — Flow-Eval",
        f"  Faelle:            {s['n']}",
        f"  geparst:           {s['geparst']:.0%}",
        f"  tools_gueltig:     {s['tools_gueltig']:.0%}",
        f"  scope_ok:          {s['scope_ok']:.0%}",
        "  erwartet getroffen: "
        + ("n/a" if s["erwartet_getroffen"] is None else f"{s['erwartet_getroffen']:.0%}"),
        "",
    ]
    faelle = bericht["faelle"]
    assert isinstance(faelle, list)
    for z in faelle:
        mark = "OK " if z["geparst"] and z["tools_gueltig"] and z["scope_ok"] else "-- "
        zeilen.append(f"  [{mark}] {z['befehl']}  ->  {z['tools']}")
        if z["fehler"]:
            zeilen.append(f"          Fehler: {z['fehler']}")
    return "\n".join(zeilen)


def main() -> int:
    ap = argparse.ArgumentParser(description="Flow-Eval — Modell-Zuverlaessigkeit messen.")
    ap.add_argument("--root", default=".", help="Scope-Wurzel fuer den Dry-Run.")
    ap.add_argument("--model", default=None, help="Modell-ID aus config/models.yaml.")
    ap.add_argument("--set", dest="satz", default=None, help="Eigener Eval-Satz (JSON).")
    ap.add_argument("--json", action="store_true", help="Bericht als JSON ausgeben.")
    a = ap.parse_args()

    scope = Scope.of(Path(a.root))
    daemon = FlowDaemon(scope=scope, audit=AuditLog(Path(a.root) / ".flow" / "eval-audit.jsonl"))
    faelle = lade_faelle(a.satz)
    bericht = evaluiere(faelle, lambda b: planner.plane(b, a.model), daemon.dry_run)

    if a.json:
        print(json.dumps(bericht, ensure_ascii=False, indent=2))
    else:
        print(_scorecard(bericht))
    return 0


if __name__ == "__main__":
    sys.exit(main())
