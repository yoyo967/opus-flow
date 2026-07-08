"""Permission-Gate — Freigabe je Wirkungsklasse (Sicherheits-Kontrakt §5.2).

`read` ist auto-erlaubt (nebenwirkungsfrei). `write`/`exec`/`ui` erfordern **explizite
menschliche Freigabe** (Just-in-time in OPUS DECK). Kein „Alles-erlauben"-Schalter.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §5.2 (Gate je Wirkungsklasse)
"""

from __future__ import annotations

_AUTO_ERLAUBT = frozenset({"read"})


def braucht_freigabe(wirkungsklasse: str) -> bool:
    """True, wenn die Wirkungsklasse eine menschliche Freigabe braucht (alles außer `read`)."""
    return wirkungsklasse not in _AUTO_ERLAUBT
