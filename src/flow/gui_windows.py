"""Echter Windows-UIA-Treiber fuer OPUS FLOW F4 (Accessibility, §3.1).

Kapselt das ``uiautomation``-Paket (Extra ``[gui]``). Wird NUR von ``gui.build_driver()`` geladen;
fehlt das Paket oder ist die Plattform kein Windows, faellt ``build_driver()`` auf ``None`` zurueck
und die GUI-Tools liefern einen typisierten Fehler (kein Crash, §3.3).

Selector-Format (minimal, robust): ``name=<Fenstertitel-Teil>`` · ``auto=<AutomationId>`` ·
``class=<ClassName>``. Accessibility statt Pixel; Pixel-Fallback bewusst nicht im MVP.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3.1 (Accessibility-first), §3.3 (typisierte Fehler)
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import uiautomation as auto

_MAX_TIEFE = 6
_MAX_ELEMENTE = 400
_SUCH_S = 3


def _rolle(ctrl: Any) -> str:
    try:
        return str(ctrl.ControlTypeName)
    except Exception:  # noqa: BLE001
        return ""


def _sel(ctrl: Any) -> str:
    """Bevorzugten Selector fuer ein Element ableiten (auto > name > class)."""
    for art, attr in (("auto", "AutomationId"), ("name", "Name"), ("class", "ClassName")):
        try:
            wert = getattr(ctrl, attr)
        except Exception:  # noqa: BLE001
            wert = None
        if wert:
            return f"{art}={wert}"
    return ""


class WindowsUiaDriver:
    """Windows-UI-Automation-Treiber (Accessibility-Baum, Klick, Fuellen, Screenshot)."""

    def _fenster(self, target: str) -> Any | None:
        w = auto.WindowControl(searchDepth=1, SubName=target)
        if not w.Exists(maxSearchSeconds=_SUCH_S):
            return None
        try:
            w.SetActive()
        except Exception:  # noqa: BLE001 — Aktivieren best-effort
            pass
        return w

    def _descendants(self, ctrl: Any) -> Iterator[Any]:
        stapel: list[tuple[Any, int]] = [(ctrl, 0)]
        gezaehlt = 0
        while stapel and gezaehlt < _MAX_ELEMENTE:
            knoten, tiefe = stapel.pop(0)
            try:
                kinder = knoten.GetChildren()
            except Exception:  # noqa: BLE001
                kinder = []
            for kind in kinder:
                gezaehlt += 1
                yield kind
                if tiefe < _MAX_TIEFE:
                    stapel.append((kind, tiefe + 1))

    def inspect(self, target: str) -> list[dict[str, Any]]:
        w = self._fenster(target)
        if w is None:
            raise RuntimeError(f"Fenster nicht gefunden: {target!r}")
        aus: list[dict[str, Any]] = []
        for c in self._descendants(w):
            try:
                name = c.Name or ""
            except Exception:  # noqa: BLE001
                name = ""
            aus.append({"name": name, "rolle": _rolle(c), "selector": _sel(c)})
        return aus

    def _find(self, target: str, selector: str) -> Any | None:
        w = self._fenster(target)
        if w is None:
            return None
        art, _, wert = selector.partition("=")
        art = art.strip().lower()
        wert = wert.strip()
        for c in self._descendants(w):
            try:
                if art == "name" and wert.lower() in (c.Name or "").lower():
                    return c
                if art == "auto" and (c.AutomationId or "") == wert:
                    return c
                if art == "class" and (c.ClassName or "") == wert:
                    return c
            except Exception:  # noqa: BLE001
                continue
        return None

    def click(self, target: str, selector: str) -> bool:
        c = self._find(target, selector)
        if c is None:
            return False
        c.Click(simulateMove=False)
        return True

    def fill(self, target: str, selector: str, wert: str) -> bool:
        c = self._find(target, selector)
        if c is None:
            return False
        try:
            c.GetValuePattern().SetValue(wert)
        except Exception:  # noqa: BLE001 — Fallback: fokussieren + tippen
            c.SetFocus()
            auto.SendKeys(wert, waitTime=0)
        return True

    def screenshot(self, ziel: Path) -> None:
        auto.GetRootControl().CaptureToImage(str(ziel))
