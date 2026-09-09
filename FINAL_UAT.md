# GREENLIGHT — Final Judge UAT

Run the server:

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:app --port 8889 --host 127.0.0.1
```

Open `http://127.0.0.1:8889` and hard-refresh once.

## P0 — Must pass

- [ ] Initial state says `READY` and does **not** show UNKNOWN, N/A, WHY, NEXT, or zero counters.
- [ ] `Demo Scenario` and `Paste Screenplay` are the only input modes.
- [ ] Exactly three visible scenario buttons appear: Brooklyn Drone Chase, Svalbard Arctic, Savannah Pyro.
- [ ] No Fountain tab and no native `<select>` appear in the judging UI.
- [ ] Click Brooklyn → selected state is visible → click Analyze.
- [ ] Agent Activity does not overlap; every row has a pipeline prefix.
- [ ] Pipeline visibly progresses in this order: Ingest → Extract → Triage → Research → Assess → Mitigate → Greenlight.
- [ ] Extract and Triage are visibly represented; they are not skipped in the UI presentation even when SSE events arrive quickly.
- [ ] Final Production Decision shows RED/YELLOW/GREEN and readiness score.
- [ ] WHY is concise and explains the most important risk.
- [ ] NEXT is concise and actionable.
- [ ] Top Risks contains the actual highest-priority dependencies, with status, why, and next action.
- [ ] Evidence & Citations shows actual source titles/URLs from the backend; no invented evidence.
- [ ] Decision Chain shows dependency → evidence → mitigation.
- [ ] Scene → Production Impact shows the scene and production implication.
- [ ] Audit trail is hidden by default and expands only when requested.

## P0 — Scenario persistence

- [ ] Analyze Brooklyn to completion.
- [ ] Click Svalbard → analyze to completion.
- [ ] Click Savannah → analyze to completion.
- [ ] Click Brooklyn again → Brooklyn result returns, not Svalbard/Savannah and not blank.
- [ ] Click Svalbard again → Svalbard result returns.
- [ ] Click Savannah again → Savannah result returns.
- [ ] Switching scenarios does not erase completed results.
- [ ] If a scenario is analyzed while another scenario is selected, the background result is retained and appears when returning to it.

## P0 — Reset

- [ ] Click `↻ Reset Demo`.
- [ ] All result panels clear to the intentional READY state.
- [ ] Agent Activity returns to waiting state.
- [ ] Pipeline returns to INGEST.
- [ ] Scenario selection clears.
- [ ] Analyze becomes available again.

## P1 — Paste Screenplay

- [ ] Click `Paste Screenplay`.
- [ ] Helper text says `Paste screenplay content for analysis.`
- [ ] Paste a short screenplay and click Analyze.
- [ ] It uses the existing `/api/analyze` flow.
- [ ] Final Production Decision renders normally.
- [ ] Click Reset Demo and confirm the custom result is cleared.

## Judge quick-glance test

After any scenario completes, ask:

1. What is the production decision?
2. How ready is it?
3. What is the biggest blocker?
4. What do I need to do next?
5. What evidence supports that conclusion?

If those five answers are visible within ~10 seconds, the UI is doing its job.
