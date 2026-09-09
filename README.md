# Greenlight — Production Intelligence

Hackathon Demo — 60–90 Seconds

- Prerequisites:
  - Python 3.11+ and a project virtual environment created (see project setup).
  - Activate the project's virtualenv from the repo root on Windows:

    .\.venv\Scripts\Activate.ps1  # PowerShell

  - Install dependencies into the venv (if not already done):

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt

- Start the demo server (from repo root):

  .\.venv\Scripts\python.exe -m uvicorn server.main:app --port 8889 --host 127.0.0.1

- Open the demo in a browser:

  http://127.0.0.1:8889/

- Recommended sample: `brooklyn-drone-chase` (select from the sample dropdown).

What the judge should observe (60–90s):

1. Click `Analyze` on the `brooklyn-drone-chase` sample.
2. The left pipeline animates through: INGEST → EXTRACT → TRIAGE → RESEARCH → ASSESS → MITIGATE → GREENLIGHT.
3. During `RESEARCH` the UI shows Parallel Search activity and citation counts as evidence arrives.
4. As assessments complete, risk lines and recommended mitigations populate.
5. Final executive brief appears: bold color-coded status (GREEN / YELLOW / RED), a Readiness Score, a short "Why" (top risk), and one clear "Next" action.
6. If desired, expand `View technical details` to see the raw JSON used for auditing.

Expected final outcome (demo sample):

- The Brooklyn sample ends with a clear verdict (typically `BLOCKED` / `RED` for this sample), a readiness score, top risks, and recommended mitigations.

Fallback / Demo mode notes:

- The server runs in demo-friendly mode in this repository; if live APIs are unavailable the app falls back to curated sample behavior and the Parallel Search tool returns demo citations.

