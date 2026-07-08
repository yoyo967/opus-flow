"""Planner — Befehl → Schrittplan (§4 PLAN-Phase), hybrider Modell-Katalog (OPUS FLOW EX).

Zwei-Phasen-Prinzip (§4): der Planner erzeugt NUR einen Plan (welche Tools, welche Args) — er
führt **nichts** aus. Ausführung passiert später über die API, Schritt für Schritt, gegated.

Modellwahl aus dem Katalog (`config/models.yaml`, `src/flow/models.py`): **gemma** (Ollama, lokal
oder Cloud-GPU), **anthropic**, **gemini** (Vertex-EU) — dasselbe Muster wie OPUS PRIME EX. Der
Modell-Caller ist injizierbar → Tests ohne Netz/SDK. Fehlt das Modell oder ist die Antwort
unparsbar, kommt ein **typisiertes** Ergebnis (kein Crash).

# SPEC: opus-deck/spec/FLOW_STUDIO.md §4/§7; opus-flow/docs/STATUS.md (OPUS FLOW EX Vision)
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable
from typing import Any

from src.flow.models import ModelNotFound, ModelProfile, default_model_id, resolve_model
from src.flow.registry import liste

_OLLAMA_HOST = "http://localhost:11434"
_TIMEOUT_S = 300
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

# Caller: (profil, system, user) -> Rohtext des Modells. Injizierbar (Tests).
ModelCaller = Callable[[ModelProfile, str, str], str]


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
    model_id: str | None = None,
    caller: ModelCaller | None = None,
) -> dict[str, Any]:
    """Erzeuge einen Schrittplan mit dem gewaehlten Modell. {plan, modell} oder {fehler}."""
    if not befehl.strip():
        return {"fehler": "Leerer Befehl."}
    try:
        profil = resolve_model(model_id or default_model_id())
    except ModelNotFound as exc:
        return {"fehler": str(exc)}
    ruf = caller or _default_caller
    try:
        inhalt = ruf(profil, _system_prompt(), befehl.strip())
    except Exception as exc:  # Modell/Provider nicht erreichbar (Netz/SDK/Key/ADC)
        return {"fehler": f"Planner-Modell '{profil.id}' nicht erreichbar: {type(exc).__name__}"}
    plan = _parse_plan(inhalt)
    if plan is None:
        return {"fehler": "Plan nicht parsebar.", "roh": inhalt[:2000], "modell": profil.label}
    return {"plan": plan, "modell": profil.label, "provider": profil.provider}


def _default_caller(profil: ModelProfile, system: str, user: str) -> str:
    """Ruft je Provider das passende Modell. SDKs werden lazy importiert (Extras optional)."""
    if profil.provider == "gemma":
        return _call_gemma(profil, system, user)
    if profil.provider == "anthropic":
        return _call_anthropic(profil, system, user)
    if profil.provider == "gemini":
        return _call_gemini(profil, system, user)
    raise ValueError(f"Unbekannter Provider: {profil.provider}")


def _call_gemma(profil: ModelProfile, system: str, user: str) -> str:
    """Gemma ueber Ollama (lokal oder Cloud-GPU via host_env). Stdlib, kein Extra noetig."""
    host = os.environ.get(profil.host_env) if profil.host_env else _OLLAMA_HOST
    if not host:
        raise RuntimeError(f"Cloud-GPU-Host nicht gesetzt: ${profil.host_env}")
    payload = json.dumps({
        "model": profil.model_name or profil.id,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False, "format": "json", "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # noqa: S310  # Ollama-Endpoint
        daten = json.loads(resp.read().decode("utf-8"))
    return str((daten.get("message") or {}).get("content", "")).strip()


def _call_anthropic(profil: ModelProfile, system: str, user: str) -> str:
    """Claude ueber die Anthropic-API (Extra [anthropic], ANTHROPIC_API_KEY)."""
    import anthropic

    kwargs: dict[str, Any] = {
        "model": profil.id, "max_tokens": profil.max_tokens,
        "system": system, "messages": [{"role": "user", "content": user}],
    }
    if profil.temperature is not None:
        kwargs["temperature"] = profil.temperature
    antwort = anthropic.Anthropic().messages.create(**kwargs)
    return "".join(
        b.text for b in antwort.content if getattr(b, "type", None) == "text"
    )


def _call_gemini(profil: ModelProfile, system: str, user: str) -> str:
    """Gemini ueber Vertex AI (EU-Region; Extra [vertex] + GCP ADC)."""
    import vertexai
    from vertexai.generative_models import GenerativeModel

    projekt = os.environ.get("GOOGLE_CLOUD_PROJECT") or "leadmachines-prod"
    vertexai.init(project=projekt, location=profil.region or "europe-west3")
    modell = GenerativeModel(profil.model_name or profil.id, system_instruction=system)
    antwort = modell.generate_content(
        user, generation_config={"max_output_tokens": profil.max_tokens, "temperature": 0},
    )
    return str(getattr(antwort, "text", ""))


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
