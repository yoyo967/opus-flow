"""Scope — deklarierter Wirkungsraum eines Flows (Sicherheits-Kontrakt §5.1).

Ein Flow darf nur INNERHALB erklaerter Wurzeln wirken. `resolve_within` loest einen Pfad auf
und weist alles ausserhalb hart ab — Path-Traversal (`..`) und Symlinks werden durch `resolve()`
neutralisiert, bevor die Zugehoerigkeit geprueft wird.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §5 (Least Privilege + Scope)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ScopeError(Exception):
    """Zugriff ausserhalb des erlaubten Scope."""


@dataclass(frozen=True)
class Scope:
    """Erlaubte Wurzeln. Nur Pfade darin (oder darunter) sind zulaessig."""

    roots: tuple[Path, ...]

    @classmethod
    def of(cls, *roots: str | Path) -> Scope:
        """Scope aus einer oder mehreren Wurzeln (aufgeloest, absolut)."""
        if not roots:
            raise ScopeError("Scope braucht mindestens eine Wurzel.")
        return cls(tuple(Path(r).resolve() for r in roots))

    def resolve_within(self, pfad: str | Path) -> Path:
        """Loese `pfad` auf und stelle sicher, dass er in einer erlaubten Wurzel liegt.

        Wirft ScopeError, wenn ausserhalb — Traversal/Symlinks sind durch resolve() bereits
        aufgeloest, die Pruefung erfolgt also auf dem realen Zielpfad.
        """
        ziel = Path(pfad).resolve()
        for root in self.roots:
            if ziel == root or ziel.is_relative_to(root):
                return ziel
        raise ScopeError(f"Pfad ausserhalb des erlaubten Scope: {pfad}")
