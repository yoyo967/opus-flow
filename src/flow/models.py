"""Modell-Katalog fuer den OPUS-FLOW-Planner (Muster wie OPUS PRIME EX gateway).

Der Katalog (`config/models.yaml`) ist die Single-Source; Nutzer:innen waehlen im Panel.
OPUS FLOW EX = so stark wie OPUS PRIME EX (voller hybrider Modell-Katalog, dasselbe Muster).

# SPEC: opus-deck/spec/FLOW_STUDIO.md §7; opus-flow/docs/STATUS.md (OPUS FLOW EX Vision)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_MODELS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "models.yaml"


class ModelNotFound(ValueError):
    """Ein angefragtes Modell ist nicht im Katalog."""


@dataclass(frozen=True)
class ModelProfile:
    """Ein waehlbares Planner-Modell. provider: anthropic | gemini | gemma."""

    id: str
    label: str
    provider: str
    temperature: float | None = None
    max_tokens: int = 4096
    region: str | None = None  # gemini: Vertex-Region (EU-first)
    host_env: str | None = None  # gemma: Env-Var mit Remote-Host (Cloud-GPU); leer -> localhost
    model_name: str | None = None  # provider-nativer Name (Default: id)


def _profile_from(eintrag: dict[str, Any]) -> ModelProfile:
    temp = eintrag.get("temperature")
    return ModelProfile(
        id=str(eintrag["id"]),
        label=str(eintrag.get("label", eintrag["id"])),
        provider=str(eintrag["provider"]),
        temperature=(None if temp is None else float(temp)),
        max_tokens=int(eintrag.get("max_tokens", 4096)),
        region=(str(eintrag["region"]) if eintrag.get("region") else None),
        host_env=(str(eintrag["host_env"]) if eintrag.get("host_env") else None),
        model_name=(str(eintrag["model_name"]) if eintrag.get("model_name") else None),
    )


@lru_cache(maxsize=1)
def _load(path: str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = yaml.safe_load(handle)
    return loaded


def list_models(models_path: Path = _MODELS_PATH) -> list[ModelProfile]:
    """Der waehlbare Modell-Katalog (Reihenfolge erhalten)."""
    raw = _load(str(models_path))
    return [_profile_from(e) for e in raw.get("catalog", []) or []]


def default_model_id(models_path: Path = _MODELS_PATH) -> str:
    """Id des Default-Modells (sonst erster Katalog-Eintrag)."""
    raw = _load(str(models_path))
    if raw.get("default_model"):
        return str(raw["default_model"])
    katalog = raw.get("catalog") or []
    if not katalog:
        raise ModelNotFound("models.yaml hat weder default_model noch catalog.")
    return str(katalog[0]["id"])


def resolve_model(model_id: str, models_path: Path = _MODELS_PATH) -> ModelProfile:
    """Das ModelProfile zu einer gewaehlten Modell-id."""
    for profil in list_models(models_path):
        if profil.id == model_id:
            return profil
    raise ModelNotFound(f"Unbekanntes Modell '{model_id}' (nicht im Katalog).")
