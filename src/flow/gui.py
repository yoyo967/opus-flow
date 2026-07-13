"""OPUS FLOW F4 — GUI-Automation (§3.1). Accessibility-first, App-Scope bindend.

Primaer ueber Accessibility (Windows UI Automation) statt Pixel — robuster (§3.1). Der
**App-Scope** (Allowlist erlaubter Apps) ist bindend: ausserhalb = hartes Nein (§5.1). Default
leer = deny-all (Least Privilege). ``ui.inspect`` ist nebenwirkungsfrei (``read``); ``ui.click``/
``ui.fill`` wirken auf Fremd-Apps (``ui``, gegated §5.2) und erzeugen je Schritt einen
**Screenshot-Artifact** (AK F4).

Der Treiber ist **injizierbar** (Protocol) — Tests laufen ohne echtes UI. Der echte Windows-
Treiber (``uiautomation``, Extra ``[gui]``) wird nur bei Bedarf gebaut und bricht die Gates nie
(fehlt er, liefern die Tools einen typisierten Fehler statt Crash, §3.3).

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3.1 (GUI-Tools), §5.1 (Scope), §5.2 (Gate)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.flow.redact import redact
from src.flow.tools import ToolResult

_MAX_ELEMENTE = 400  # Baum-Truncation (§3.3)


@dataclass(frozen=True)
class AppScope:
    """Allowlist erlaubter Apps (Substring-Muster gegen Fenstertitel/Prozessname, lower-case)."""

    muster: tuple[str, ...] = ()

    @classmethod
    def of(cls, *muster: str) -> AppScope:
        return cls(tuple(m.strip().lower() for m in muster if m.strip()))

    def erlaubt(self, app: str) -> bool:
        ziel = app.lower()
        return any(m in ziel for m in self.muster)


@runtime_checkable
class GuiDriver(Protocol):
    """Treiber-Kontrakt. Der echte Treiber kapselt Windows UI Automation; Tests injizieren Fakes."""

    def inspect(self, target: str) -> list[dict[str, Any]]:
        """Accessibility-Baum eines Fensters als flache Elementliste (name/rolle/selector)."""

    def click(self, target: str, selector: str) -> bool:
        """Element per Selector anklicken. True = getroffen."""

    def fill(self, target: str, selector: str, wert: str) -> bool:
        """Textfeld per Selector setzen. True = gesetzt."""

    def screenshot(self, ziel: Path) -> None:
        """Screenshot des aktuellen Zustands nach ``ziel`` (PNG) schreiben."""


# --- Modul-Konfiguration (beim Daemon-Start gesetzt; Default = sicher/deny-all) ---------------
_APP_SCOPE = AppScope.of()
_DRIVER: GuiDriver | None = None
_ARTEFAKT_DIR = Path(".flow") / "artifacts"


def configure(
    app_scope: AppScope | None = None,
    driver: GuiDriver | None = None,
    artefakt_dir: Path | None = None,
) -> None:
    """GUI-Subsystem konfigurieren (None = unverändert lassen)."""
    global _APP_SCOPE, _DRIVER, _ARTEFAKT_DIR
    if app_scope is not None:
        _APP_SCOPE = app_scope
    if driver is not None:
        _DRIVER = driver
    if artefakt_dir is not None:
        _ARTEFAKT_DIR = artefakt_dir


def reset() -> None:
    """GUI-Subsystem hart auf sicheren Default zurücksetzen (deny-all, kein Treiber)."""
    global _APP_SCOPE, _DRIVER, _ARTEFAKT_DIR
    _APP_SCOPE = AppScope.of()
    _DRIVER = None
    _ARTEFAKT_DIR = Path(".flow") / "artifacts"


def aktiv() -> tuple[AppScope, GuiDriver | None]:
    """Aktueller (App-Scope, Treiber) — von der Registry zur Laufzeit gelesen."""
    return _APP_SCOPE, _DRIVER


def status() -> dict[str, Any]:
    """Aktuelle GUI-Sicherheitslage (für den Security-Posture-Inspektor, F5)."""
    return {
        "app_scope": list(_APP_SCOPE.muster),
        "treiber_aktiv": _DRIVER is not None,
        "artefakt_dir": str(_ARTEFAKT_DIR),
    }


def _fehler(tool: str, klasse: str, msg: str) -> ToolResult:
    return ToolResult(tool=tool, wirkungsklasse=klasse, ok=False, fehler=redact(msg))


def _pruefe(
    tool: str, klasse: str, target: str, scope: AppScope, drv: GuiDriver | None
) -> ToolResult | None:
    if not scope.erlaubt(target):
        return _fehler(tool, klasse, f"App ausserhalb App-Scope: {target!r}")
    if drv is None:
        return _fehler(tool, klasse, "GUI-Treiber nicht verfuegbar (Extra [gui] / kein Windows).")
    return None


def _screenshot(drv: GuiDriver, dir_: Path, tag: str) -> str | None:
    """Screenshot je Schritt (AK F4). Fehler beim Schuss brechen den Schritt NICHT ab."""
    try:
        dir_.mkdir(parents=True, exist_ok=True)
        stempel = time.strftime("%Y%m%d-%H%M%S")
        ziel = dir_ / f"{tag}-{stempel}-{int(time.monotonic() * 1000) % 1000}.png"
        drv.screenshot(ziel)
        return str(ziel)
    except Exception:  # noqa: BLE001 — Artifact ist Beiwerk, kein Grund den Schritt zu kippen
        return None


def ui_inspect(target: str, app_scope: AppScope, driver: GuiDriver | None) -> ToolResult:
    """Accessibility-Baum einer erlaubten App lesen (nebenwirkungsfrei, ``read``)."""
    tool, klasse = "ui.inspect", "read"
    drv = driver
    fehler = _pruefe(tool, klasse, target, app_scope, drv)
    if fehler is not None:
        return fehler
    assert drv is not None
    try:
        elemente = drv.inspect(target)
    except Exception as exc:  # noqa: BLE001 — Fremd-App/UIA-Fehler als typisiertes Ergebnis (§3.3)
        return _fehler(tool, klasse, f"inspect fehlgeschlagen: {exc}")
    gekuerzt = [
        {"name": redact(str(e.get("name", ""))), "rolle": str(e.get("rolle", "")),
         "selector": str(e.get("selector", ""))}
        for e in elemente[:_MAX_ELEMENTE]
    ]
    return ToolResult(tool, klasse, True, data={
        "app": target, "elemente": gekuerzt,
        "truncated": len(elemente) > _MAX_ELEMENTE, "gesamt": len(elemente),
    })


def ui_click(
    target: str, selector: str, app_scope: AppScope, driver: GuiDriver | None
) -> ToolResult:
    """Element in einer erlaubten App anklicken (``ui``, gegated). Screenshot je Schritt."""
    tool, klasse = "ui.click", "ui"
    drv = driver
    fehler = _pruefe(tool, klasse, target, app_scope, drv)
    if fehler is not None:
        return fehler
    assert drv is not None
    try:
        getroffen = drv.click(target, selector)
    except Exception as exc:  # noqa: BLE001
        return _fehler(tool, klasse, f"click fehlgeschlagen: {exc}")
    shot = _screenshot(drv, _ARTEFAKT_DIR, "click")
    return ToolResult(tool, klasse, getroffen, data={
        "app": target, "selector": selector, "getroffen": getroffen, "screenshot": shot,
    })


def ui_fill(
    target: str, selector: str, wert: str, app_scope: AppScope, driver: GuiDriver | None
) -> ToolResult:
    """Textfeld in einer erlaubten App setzen (``ui``, gegated). Der Wert wird NICHT geloggt."""
    tool, klasse = "ui.fill", "ui"
    drv = driver
    fehler = _pruefe(tool, klasse, target, app_scope, drv)
    if fehler is not None:
        return fehler
    assert drv is not None
    try:
        gesetzt = drv.fill(target, selector, wert)
    except Exception as exc:  # noqa: BLE001
        return _fehler(tool, klasse, f"fill fehlgeschlagen: {exc}")
    shot = _screenshot(drv, _ARTEFAKT_DIR, "fill")
    # Wert bewusst NICHT in der Ausgabe (koennte Secret sein, §5.7) — nur Laenge.
    return ToolResult(tool, klasse, gesetzt, data={
        "app": target, "selector": selector, "wert_laenge": len(wert),
        "gesetzt": gesetzt, "screenshot": shot,
    })


def build_driver() -> GuiDriver | None:
    """Echten Windows-UIA-Treiber bauen — nur wenn ``uiautomation`` verfuegbar (sonst None)."""
    try:
        from src.flow.gui_windows import WindowsUiaDriver
    except Exception:  # noqa: BLE001 — kein Windows / Extra fehlt: GUI-Tools bleiben deaktiviert
        return None
    return WindowsUiaDriver()
