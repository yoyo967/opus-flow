# OPUS FLOW

Lokaler Desktop-/Dev-Automations-Agent (Gemma 4, lokal) — Mieter von OPUS DECK. Macht aus **einem**
natürlichsprachlichen Befehl einen **transparenten, auditierbaren, wiederholbaren** Flow, der
App-Oberfläche und Shell/Dev kombiniert. **Alles lokal, kein Datenabfluss.**

> Spec: [`opus-deck/spec/FLOW_STUDIO.md`](../opus-deck/spec/FLOW_STUDIO.md) ·
> Entscheidung: [`opus-deck/docs/adr/ADR-0004`](../opus-deck/docs/adr/ADR-0004-flow-studio-agent.md)

## Stand: F0 — Daemon-Skelett + read-only Tools (via MCP)

F0 wirkt **nicht** — es liest nur, mit dem vollen Sicherheits-Kontrakt ab Tag 1:

- **Scope-Enforcement** (`src/flow/scope.py`): jeder Zugriff nur innerhalb erklärter Wurzeln;
  Path-Traversal (`..`) und Symlinks durch `resolve()` neutralisiert. Außerhalb = hartes Nein.
- **Wirkungsklassen** (`read` in F0; `write`/`exec`/`ui` ab F1 mit Permission-Gate).
- **Strukturierte, typisierte Ausgabe** (kein nackter Dump), größenbegrenzt, Fehler als Ergebnis (kein Crash).
- **Secret-Redaction** (`src/flow/redact.py`): Tokens/Keys/Passwörter vor jeder Rückgabe maskiert.
- Tools: `fs.list_files`, `fs.read_file`, `git.status`, `git.diff` — exponiert als **MCP-Server**.

**Ehrliche Abweichung von der Spec:** die Spec nennt ACP als UI-Transport; der ACP-Host in OPUS
DECK ist bewusst zurückgestellt. MCP ist laut Spec §2 die Tool-Broker-Schicht und im OPUS-System
bereits im Einsatz — F0 nutzt daher MCP. ACP-Anbindung folgt, wenn der ACP-Host steht.

## Nutzung

```bash
pip install -e .[dev,mcp]
FLOW_ROOT=/pfad/zum/erlaubten/space opus-flow-mcp   # MCP-Server (stdio)
```

Als MCP-Server registrieren (z. B. Claude Code `.mcp.json`):
```json
{ "mcpServers": { "opus-flow": { "command": "opus-flow-mcp", "env": { "FLOW_ROOT": "..." } } } }
```

## Gates

`ruff check src tests` · `mypy` · `pytest` — grün vor jedem Commit (Perfect-Twin-Disziplin).

## Roadmap (Spec §8)

F0 read-Tools ✅ · **F1** Shell mit Gate+Audit · **F2** Planner (Plan→Approve→Execute) · **F3**
Artifacts/Replay/Workflow-Speicherung · **F4** GUI-Automation · **F5** Hybrid-Modell + Härtung.
