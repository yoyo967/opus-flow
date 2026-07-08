"""Planner — Befehl → Schrittplan via lokalem Gemma 4 (Ollama), §4 PLAN-Phase.

Zwei-Phasen-Prinzip (§4): der Planner erzeugt NUR einen Plan (welche Tools, welche Args) — er
führt **nichts** aus. Ausführung passiert später über die API, Schritt für Schritt, gegated.

Lokal, kein Datenabfluss. Der HTTP-Opener ist injizierbar → Tests ohne Ollama/Netz. Fehlt Ollama
oder ist die Antwort unparsbar, kommt ein **typisiertes** Ergebnis (kein Crash) — das Panel bleibt
für direkte Tool-Aufrufe nutzbar.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §4 (Plan→Approve→Execute), §7 (Gemma lokal)
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from typing import Any

from src.flow.registry import liste

_HOST = "http://localhost:11434"
_TIMEOUT_S = 300
_MODELL = "gemma4:e4b"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

Opener = Callable[[urllib.request.Request], Any]


def _default_opener(req: urllib.request.Request) -> Any:
    return urllib.request.urlopen(req, timeout=_TIMEOUT_S)  # noqa: S310  # nur localhost-Ollama


def _system_prompt() -> str:
    zeilen = [
        f"- {t['name']} ({t['wirkungsklasse']}): {t['beschreibung']}; params={t['params']}"
        for t in liste()
    ]
    return (
        "Du bist der Planner von OPUS FLOW. Zerlege den Nutzerbefehl in einen Schrittplan, der NUR "
        "diese Tools verwendet:\n" + "\n".join(zeilen) + "\n\n"
        "Regeln: nutze ausschliesslich vorhandene Tools und deren params; gib pro Schritt eine "
        "kurze Begruendung. Antworte AUSSCHLIESSLICH als JSON, ohne Prosa, im Format: "
        '{"plan":[{"tool":"<name>","args":{...},"warum":"<kurz>"}]}'
    )


def plane(
    befehl: str,
    opener: Opener = _default_opener,
    modell: str = _MODELL,
    host: str = _HOST,
) -> dict[str, Any]:
    """Erzeuge einen Schrittplan. Rückgabe: {plan:[...], modell} oder {fehler:...}."""
    if not befehl.strip():
        return {"fehler": "Leerer Befehl."}
    payload = json.dumps({
        "model": modell,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": befehl.strip()},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with opener(req) as resp:
            daten = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # Ollama nicht erreichbar / Modell nicht gezogen
        return {"fehler": f"Planner-Modell nicht erreichbar ({host}): {type(exc).__name__}"}
    inhalt = str((daten.get("message") or {}).get("content", "")).strip()
    plan = _parse_plan(inhalt)
    if plan is None:
        return {"fehler": "Plan nicht parsebar.", "roh": inhalt[:2000]}
    return {"plan": plan, "modell": modell}


def _parse_plan(inhalt: str) -> list[dict[str, Any]] | None:
    treffer = _JSON_BLOCK.search(inhalt)
    if not treffer:
        return None
    try:
        obj = json.loads(treffer.group(0))
    except (ValueError, TypeError):
        return None
    plan = obj.get("plan") if isinstance(obj, dict) else None
    if not isinstance(plan, list):
        return None
    schritte: list[dict[str, Any]] = []
    for s in plan:
        if isinstance(s, dict) and "tool" in s:
            schritte.append({
                "tool": str(s.get("tool")),
                "args": s.get("args") if isinstance(s.get("args"), dict) else {},
                "warum": str(s.get("warum", "")),
            })
    return schritte
