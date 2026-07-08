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

from src.flow import planner, registry  # noqa: E402
from src.flow.audit import AuditLog  # noqa: E402
from src.flow.daemon import FlowDaemon  # noqa: E402
from src.flow.scope import Scope  # noqa: E402

_HOST = "127.0.0.1"
_PORT = int(os.environ.get("FLOW_PORT", "8850"))


def _scope() -> Scope:
    return Scope.of(os.environ.get("FLOW_ROOT") or str(Path.cwd()))


def _audit_pfad() -> Path:
    return Path(os.environ.get("FLOW_AUDIT") or (Path.cwd() / ".flow" / "audit.jsonl"))


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
        elif pfad == "/api/flow/audit":
            self._send(200, {"eintraege": self.daemon.audit.alle()})
        elif pfad == "/api/flow/pending":
            self._send(200, {"pending": list(self.daemon.pending.values())})
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
            self._send(200, planner.plane(str(payload.get("befehl", ""))))
        elif pfad == "/api/flow/dry_run":
            self._send(200, self.daemon.dry_run(payload.get("plan") or []))
        elif pfad == "/api/flow/run":
            args = payload.get("args") or {}
            self._send(200, self.daemon.run(str(payload.get("tool", "")), args))
        elif pfad == "/api/flow/approve":
            self._send(200, self.daemon.approve(str(payload.get("id", ""))))
        elif pfad == "/api/flow/reject":
            self._send(200, self.daemon.reject(str(payload.get("id", ""))))
        else:
            self._send(404, {"fehler": "not found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


def main() -> int:
    _Handler.daemon = FlowDaemon(scope=_scope(), audit=AuditLog(_audit_pfad()))
    print(f"[flow] OPUS FLOW API · Scope: {[str(r) for r in _Handler.daemon.scope.roots]}")
    print(f"[flow] -> http://{_HOST}:{_PORT}   (Strg+C zum Beenden)")
    with socketserver.ThreadingTCPServer((_HOST, _PORT), _Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[flow] beendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
