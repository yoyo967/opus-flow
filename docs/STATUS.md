# OPUS FLOW — Status & Vision (Stand: 2026-07-08, Sessionpause)

## Vision: OPUS FLOW → **OPUS FLOW EX**

**Beschluss (Yahya, 2026-07-08):** OPUS FLOW soll **genauso stark wie OPUS PRIME EX** werden und
wird deshalb zu **OPUS FLOW EX**. Konkret:

- **Voller hybrider Modell-Katalog wie OPUS PRIME EX** — nicht nur lokales Gemma E4B, sondern
  **alle** Modelle, die OPUS PRIME EX hat: alle Claude-Modelle (Opus/Sonnet/Fable/Haiku),
  **Gemini/Vertex-EU**, **Gemma 4 lokal** UND **Gemma 4 via Cloud-GPU**.
- **Muster wiederverwenden statt neu bauen:** OPUS PRIME EX' Gateway (`config/models.yaml`-Katalog,
  `ModelProfile`, `build_llm_client`, Provider-Abstraktion anthropic/gemini/gemma) nach opus-flow
  übernehmen. Der Planner (aktuell nur `gemma4:e4b`) wählt dann aus dem Katalog; **Modellwahl im
  Flow-Panel** (analog zum Agent-Panel-Dropdown).
- **Namens-Hinweis:** wie beim Leadmachines→Agenticum-Rebrand dürfen **technische IDs den alten
  Slug behalten** (Repo `opus-flow`, Package `flow`, MCP `opus-flow`); nur die Produktmarke wird
  OPUS FLOW EX.

## Ist-Stand (gebaut, Gates grün, Cloud verifiziert)

- **F0** read-Tools (Scope/Traversal-Schutz, Redaction, Wirkungsklassen) — MCP-Server.
- **F1** Gate (read auto / exec-write-ui → Freigabe) + `shell.execute_powershell` (Allow/Deny/
  Timeout/Redaction) + append-only Audit + **lokale HTTP-API** (`apps/api/server.py`, 127.0.0.1:8850)
  + Planner (`planner.py`, lokales Gemma).
- **F2** **Dry-Run** (validiert Plan-Schritte gegen Scope+Allow/Deny **ohne** Nebeneffekt) +
  **schrittweise gegatete Ausführung** aus dem Plan.
- **OPUS-DECK-Flow-Panel** (`@opus-deck/flow-panel`, Tabs Ausführen/Plan/Freigaben/Audit) —
  **Gate in der UI**; im Cloud-UI (Workbench-Image **v8**) end-to-end verifiziert.
- Gates: ruff · mypy --strict (14) · pytest (28). Repo: github.com/yoyo967/opus-flow.

## Nächste Schritte (Reihenfolge)

1. **OPUS FLOW EX — Provider-Katalog ✅ (2026-07-08):** OPUS-PRIME-EX-Gateway-Muster portiert —
   `config/models.yaml` + `src/flow/models.py` (8 Modelle: Gemma lokal/Cloud-GPU · Gemini/Vertex-EU
   · Claude), `planner.plane(befehl, model_id)` mit Provider-Dispatch, `/api/flow/models`,
   Modell-Dropdown im Panel. Gates grün (34 Tests); Gemini-Plan live verifiziert. Damit ist OPUS
   FLOW modell-seitig so stark wie OPUS PRIME EX.
2. **F3** — Replay + parametrisierte Workflow-Speicherung (JSON/YAML).
3. **F2-Feinschliff** — automatische Ketten-Ausführung + Re-Plan + **Flow-Eval** (Gemma-Function-
   Calling-Zuverlässigkeit messen, §7/§9).
4. **F4** — GUI-Automation (Windows UI Automation / DOM).

## Betriebs-Hinweise (nicht vergessen)

- **OneDrive-Risiko:** die Repos liegen in `Documents\...` (OneDrive-gesynct); das hat opus-deck
  live korrumpiert (`.git` + Dateien verschwanden, aus Remote wiederhergestellt). **Engmaschig
  pushen**; besser die Repos an einen nicht-gesyncten Pfad (z.B. `C:\dev`) verschieben.
- Daemon lokal starten: `pip install -e .[mcp]` → `FLOW_ROOT=<space> opus-flow-serve`.
- Cloud-Workbench (privat) via `gcloud run services proxy opus-deck-workbench --region=europe-west3
  --port=8899` → http://localhost:8899. Deploy-Runbook: OPUS PRIME EX `docs/deploy_cloud_run.md`.
