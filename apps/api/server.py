"""OPUS FLOW — lokale HTTP-API für das OPUS-DECK-Flow-Panel.

Bindet NUR an 127.0.0.1 (alles lokal, §1 Non-Goal „kein Cloud/Datenabfluss"). Endpoints spiegeln
den Daemon: Tools/Plan/Run(→Gate)/Approve/Reject/Audit. CORS erlaubt die (lokale) OPUS-DECK-UI auf
anderem Port.

Nutzung:  FLOW_ROOT=<erlaubter-space> python apps/api/server.py   ->  http://127.0.0.1:8850

# SPEC: opus-deck/spec/FLOW_STUDIO.md §2 (Broker), §4 (Plan/Approve/Execute), §6 (Audit)
"""

from __future__ import annotations

import json
import os
import socketserver
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.flow import gui, models, planner, registry, shell  # noqa: E402
from src.flow.audit import AuditLog  # noqa: E402
from src.flow.daemon import FlowDaemon  # noqa: E402
from src.flow.scope import Scope  # noqa: E402
from src.flow.workflows import WorkflowStore  # noqa: E402

_HOST = "127.0.0.1"
_PORT = int(os.environ.get("FLOW_PORT", "8850"))


def _scope() -> Scope:
    return Scope.of(os.environ.get("FLOW_ROOT") or str(Path.cwd()))


def _audit_pfad() -> Path:
    return Path(os.environ.get("FLOW_AUDIT") or (Path.cwd() / ".flow" / "audit.jsonl"))


def _wf_dir() -> Path:
    return Path(os.environ.get("FLOW_WORKFLOWS") or (Path.cwd() / ".flow" / "workflows"))


def _app_scope() -> gui.AppScope:
    """App-Allowlist aus FLOW_APPS (Komma-getrennt). Leer = deny-all (Least Privilege, §5.1)."""
    roh = os.environ.get("FLOW_APPS", "")
    return gui.AppScope.of(*[m for m in roh.split(",") if m.strip()])


class _Handler(BaseHTTPRequestHandler):
    daemon: FlowDaemon

    def _send(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:  # noqa: N802
        pfad = urlparse(self.path).path.rstrip("/")
        if pfad == "/api/flow/tools":
            scope = [str(r) for r in self.daemon.scope.roots]
            self._send(200, {"tools": registry.liste(), "scope": scope})
        elif pfad == "/api/flow/models":
            self._send(200, {"modelle": [
                {"id": m.id, "label": m.label, "provider": m.provider}
                for m in models.list_models()
            ], "default": models.default_model_id()})
        elif pfad == "/api/flow/audit":
            self._send(200, {"eintraege": self.daemon.audit.alle()})
        elif pfad == "/api/flow/pending":
            self._send(200, {"pending": list(self.daemon.pending.values())})
        elif pfad == "/api/flow/workflows":
            wf = self.daemon.wf_store
            self._send(200, {"workflows": wf.liste() if wf else []})
        elif pfad == "/api/flow/security":
            self._send(200, self._sicherheit())
        else:
            self._send(404, {"fehler": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        pfad = urlparse(self.path).path.rstrip("/")
        laenge = int(self.headers.get("Content-Length", "0"))
        try:
            payload: dict[str, Any] = json.loads(self.rfile.read(laenge) or b"{}")
        except (ValueError, TypeError):
            self._send(400, {"fehler": "ungueltige Anfrage"})
            return
        if pfad == "/api/flow/plan":
            mid = payload.get("model_id")
            self._send(200, planner.plane(
                str(payload.get("befehl", "")), str(mid) if mid else None))
        elif pfad == "/api/flow/dry_run":
            self._send(200, self.daemon.dry_run(payload.get("plan") or []))
        elif pfad == "/api/flow/run_plan":
            self._send(200, self.daemon.run_plan(payload.get("plan") or []))
        elif pfad == "/api/flow/run":
            args = payload.get("args") or {}
            self._send(200, self.daemon.run(str(payload.get("tool", "")), args))
        elif pfad == "/api/flow/approve":
            self._send(200, self.daemon.approve(str(payload.get("id", ""))))
        elif pfad == "/api/flow/reject":
            self._send(200, self.daemon.reject(str(payload.get("id", ""))))
        elif pfad == "/api/flow/workflow/save":
            self._send(200, self._wf_save(payload))
        elif pfad == "/api/flow/workflow/run":
            self._send(200, self.daemon.run_workflow(
                str(payload.get("id", "")), payload.get("params") or {}))
        elif pfad == "/api/flow/kill":
            self._send(200, self.daemon.kill())
        elif pfad == "/api/flow/arm":
            self._send(200, self.daemon.arm())
        else:
            self._send(404, {"fehler": "not found"})

    def _sicherheit(self) -> dict[str, Any]:
        """Security-Posture (read-only, Transparenz): Scope, Kill-Switch, Gate, Listen, GUI."""
        d = self.daemon
        listen = shell.sicherheits_listen()
        return {
            "kill_switch": {"gestoppt": d.gestoppt, "offene_freigaben": len(d.pending)},
            "datei_scope": [str(r) for r in d.scope.roots],
            "gate": {"read": "auto", "exec/write/ui": "Freigabe nötig"},
            "shell": {
                "allowlist": listen["allowlist"], "allowlist_n": len(listen["allowlist"]),
                "denylist": listen["denylist"], "denylist_n": len(listen["denylist"]),
            },
            "gui": gui.status(),
            "tools": [
                {"name": t["name"], "wirkungsklasse": t["wirkungsklasse"]}
                for t in registry.liste()
            ],
        }

    def _wf_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        wf = self.daemon.wf_store
        if wf is None:
            return {"fehler": "Kein Workflow-Store."}
        schritte = payload.get("schritte") or payload.get("plan") or []
        try:
            return wf.speichere(
                str(payload.get("name", "")), schritte, payload.get("params"))
        except ValueError as exc:
            return {"fehler": str(exc)}

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


def main() -> int:
    _Handler.daemon = FlowDaemon(
        scope=_scope(), audit=AuditLog(_audit_pfad()), wf_store=WorkflowStore(_wf_dir()))
    app_scope = _app_scope()
    driver = gui.build_driver()
    root = Path(os.environ.get("FLOW_ROOT") or str(Path.cwd()))
    gui.configure(app_scope=app_scope, driver=driver, artefakt_dir=root / ".flow" / "artifacts")
    treiber = "aktiv" if driver is not None else "deaktiviert (Extra [gui]/kein Windows)"
    muster = list(app_scope.muster) or "(leer=deny-all)"
    print(f"[flow] OPUS FLOW API · Scope: {[str(r) for r in _Handler.daemon.scope.roots]}")
    print(f"[flow] GUI-Treiber: {treiber} · App-Scope: {muster}")
    print(f"[flow] -> http://{_HOST}:{_PORT}   (Strg+C zum Beenden)")
    with socketserver.ThreadingTCPServer((_HOST, _PORT), _Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[flow] beendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
