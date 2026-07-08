"""Secret-Redaction — Tokens/Keys/Passwoerter aus Ausgaben maskieren (Sicherheits-Kontrakt §3.3).

Jede Tool-Ausgabe laeuft VOR Log/Anzeige durch `redact`. Bewusst konservativ: lieber einmal zu
viel maskieren als ein Secret durchlassen. Kein Anspruch auf Vollstaendigkeit — ergaenzbar.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3.3 (Secret-Redaction), §5.6 (Audit ohne Leaks)
"""

from __future__ import annotations

import re

_MASKE = "«redigiert»"

# Wert-nach-Schluessel (api_key=..., token: ..., password=...): Schluessel behalten, Wert maskieren.
_KEY_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwort|bearer|authorization)"
    r"(\s*[=:]\s*|\s+)(\S+)"
)
# Bekannte Key-Formate direkt.
_TOKEN_MUSTER = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),          # Anthropic/OpenAI-artig
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"),         # Google API-Key
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),            # GitHub-Token
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),    # Slack-Token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM-Privatschluessel
]


def redact(text: str) -> str:
    """Maskiere erkennbare Secrets in `text`."""
    out = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_MASKE}", text)
    for muster in _TOKEN_MUSTER:
        out = muster.sub(_MASKE, out)
    return out
