"""OPUS FLOW F0 Tests: Scope (Path-Traversal), Redaction, read-Tools.

# SPEC: opus-deck/spec/FLOW_STUDIO.md §3.2/§3.3/§5
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.flow.redact import redact
from src.flow.scope import Scope, ScopeError
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
