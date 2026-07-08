"""OPUS FLOW F0 Tests: Scope (Path-Traversal), Redaction, read-Tools.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3.2/§3.3/§5
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.flow.audit import AuditLog
from src.flow.daemon import FlowDaemon
from src.flow.gate import braucht_freigabe
from src.flow.planner import _parse_plan, plane
from src.flow.redact import redact
from src.flow.scope import Scope, ScopeError
from src.flow.shell import pruefe_kommando, shell_execute
from src.flow.tools import fs_list_files, fs_read_file, git_diff, git_status


class TestScope:
    def test_innerhalb_erlaubt(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x")
        ziel = Scope.of(tmp_path).resolve_within(tmp_path / "a.txt")
        assert ziel == (tmp_path / "a.txt").resolve()

    def test_ausserhalb_blockiert(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        (tmp_path / "geheim.txt").write_text("x")
        with pytest.raises(ScopeError, match="ausserhalb"):
            Scope.of(root).resolve_within(tmp_path / "geheim.txt")

    def test_traversal_blockiert(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        with pytest.raises(ScopeError):
            Scope.of(root).resolve_within(root / ".." / "eltern.txt")

    def test_leerer_scope_fehler(self) -> None:
        with pytest.raises(ScopeError):
            Scope.of()


class TestRedact:
    def test_maskiert_bekannte_keys(self) -> None:
        assert "sk-" not in redact("key sk-ABCDEFGHIJKLMNOP1234")
        assert "AIza" not in redact("g AIzaSyABCDEFGHIJKLMNOPQRSTUV12345")
        assert "«redigiert»" in redact("ghp_ABCDEFGHIJKLMNOPQRST1234")

    def test_key_wert_paar(self) -> None:
        out = redact("api_key=supersecretvalue123")
        assert "supersecretvalue123" not in out
        assert "api_key" in out  # Schluessel bleibt, Wert maskiert

    def test_harmlosen_text_unveraendert(self) -> None:
        assert redact("Hallo, das ist normaler Text.") == "Hallo, das ist normaler Text."


class TestReadTools:
    def test_list_files_strukturiert(self, tmp_path: Path) -> None:
        (tmp_path / "datei.txt").write_text("abc")
        (tmp_path / "unter").mkdir()
        r = fs_list_files(Scope.of(tmp_path), str(tmp_path))
        assert r.ok and r.wirkungsklasse == "read"
        namen = {e["name"]: e["typ"] for e in r.data["eintraege"]}
        assert namen == {"datei.txt": "file", "unter": "dir"}

    def test_list_files_ausserhalb_scope(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        r = fs_list_files(Scope.of(root), str(tmp_path))
        assert not r.ok and r.fehler and "Scope" in r.fehler

    def test_read_file_redigiert_und_truncated(self, tmp_path: Path) -> None:
        f = tmp_path / "conf.env"
        f.write_text("api_key=supersecret123\nrest")
        r = fs_read_file(Scope.of(tmp_path), str(f))
        assert r.ok
        assert "supersecret123" not in r.data["inhalt"]  # redigiert
        r2 = fs_read_file(Scope.of(tmp_path), str(f), max_bytes=5)
        assert r2.data["truncated"] is True

    def test_read_file_kein_file(self, tmp_path: Path) -> None:
        r = fs_read_file(Scope.of(tmp_path), str(tmp_path))
        assert not r.ok

    def test_git_status_kein_repo(self, tmp_path: Path) -> None:
        # Kein Crash, typisierter Fehler.
        r = git_status(Scope.of(tmp_path), str(tmp_path))
        assert not r.ok and r.fehler

    def test_git_status_und_diff_auf_repo(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.de"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "neu.txt").write_text("inhalt")
        r = git_status(Scope.of(tmp_path), str(tmp_path))
        assert r.ok and r.data["branch"] is not None
        assert r.data["sauber"] is False  # neue Datei = Aenderung
        d = git_diff(Scope.of(tmp_path), str(tmp_path))
        assert d.ok  # kein Crash (leerer diff-stat ist ok)


class TestGate:
    def test_read_auto(self) -> None:
        assert braucht_freigabe("read") is False

    def test_exec_write_ui_gegated(self) -> None:
        assert all(braucht_freigabe(k) for k in ("exec", "write", "ui"))


class TestShell:
    def test_allowlist_denylist(self) -> None:
        assert pruefe_kommando("git status") is None
        assert "Allowlist" in (pruefe_kommando("format C:") or "")
        assert "Denylist" in (pruefe_kommando("git clean; Remove-Item -Recurse x") or "")

    def test_execute_nur_erlaubt(self, tmp_path: Path) -> None:
        aufgerufen: dict[str, str] = {}

        def fake_runner(cmd: str, cwd: str, timeout: int) -> tuple[int, str, str]:
            aufgerufen["cmd"] = cmd
            return 0, "hallo", ""

        r = shell_execute(Scope.of(tmp_path), "echo hallo", runner=fake_runner)
        assert r.ok and r.wirkungsklasse == "exec" and r.data["stdout"] == "hallo"
        # Blockiertes Kommando wird NICHT ausgefuehrt:
        aufgerufen.clear()
        b = shell_execute(Scope.of(tmp_path), "Remove-Item -Recurse x", runner=fake_runner)
        assert not b.ok and "cmd" not in aufgerufen


class TestAudit:
    def test_append_und_redaction(self, tmp_path: Path) -> None:
        log = AuditLog(tmp_path / ".flow" / "audit.jsonl")
        log.schreibe(
            tool="t", wirkungsklasse="exec",
            args={"command": "token sk-ABCDEFGHIJKLMNOP12"},
            freigabe="user", ok=True, ergebnis={"x": 1}, dauer_ms=3,
        )
        eintraege = log.alle()
        assert len(eintraege) == 1 and eintraege[0]["freigabe"] == "user"
        assert "sk-ABCDEFGHIJKLMNOP12" not in eintraege[0]["args"]  # redigiert


class TestDaemon:
    def _daemon(self, tmp_path: Path) -> FlowDaemon:
        return FlowDaemon(scope=Scope.of(tmp_path), audit=AuditLog(tmp_path / ".flow" / "a.jsonl"))

    def test_read_sofort_und_auditiert(self, tmp_path: Path) -> None:
        (tmp_path / "x.txt").write_text("hi")
        d = self._daemon(tmp_path)
        antwort = d.run("fs.list_files", {"pfad": str(tmp_path)})
        assert "ergebnis" in antwort and antwort["ergebnis"]["ok"]
        assert d.audit.alle()[-1]["freigabe"] == "auto"

    def test_exec_gegated_pending_kein_execute(self, tmp_path: Path) -> None:
        d = self._daemon(tmp_path)
        antwort = d.run("shell.execute_powershell", {"command": "git status"})
        assert "pending" in antwort and antwort["pending"]["wirkungsklasse"] == "exec"
        assert d.audit.alle() == []  # noch NICHTS ausgefuehrt/auditiert

    def test_approve_fuehrt_aus_und_auditiert(self, tmp_path: Path) -> None:
        d = self._daemon(tmp_path)
        pid = d.run("shell.execute_powershell", {"command": "echo test"})["pending"]["id"]
        d.approve(pid)
        assert pid not in d.pending
        assert d.audit.alle()[-1]["freigabe"] == "user"  # ausgefuehrt nach Freigabe

    def test_reject_verwirft(self, tmp_path: Path) -> None:
        d = self._daemon(tmp_path)
        pid = d.run("shell.execute_powershell", {"command": "echo x"})["pending"]["id"]
        assert d.reject(pid)["ok"] and pid not in d.pending and d.audit.alle() == []

    def test_unbekanntes_tool(self, tmp_path: Path) -> None:
        assert "fehler" in self._daemon(tmp_path).run("gibt.nicht", {})


class TestPlanner:
    def test_parse_plan(self) -> None:
        roh = 'Text {"plan":[{"tool":"git.status","args":{"repo":"."},"warum":"x"}]} Ende'
        plan = _parse_plan(roh)
        assert plan and plan[0]["tool"] == "git.status" and plan[0]["args"] == {"repo": "."}

    def test_parse_plan_muell(self) -> None:
        assert _parse_plan("kein json hier") is None

    def test_plane_mit_fake_opener(self) -> None:
        class _Resp:
            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def read(self) -> bytes:
                inhalt = '{"plan":[{"tool":"git.status","args":{"repo":"."}}]}'
                return json.dumps({"message": {"content": inhalt}}).encode("utf-8")

        ergebnis = plane("zeig git status", opener=lambda req: _Resp())
        assert ergebnis["plan"][0]["tool"] == "git.status"

    def test_plane_ollama_weg(self) -> None:
        def boom(req: object) -> object:
            raise ConnectionError()

        assert "fehler" in plane("x", opener=boom)
