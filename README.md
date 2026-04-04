# PRs for Operations (Hackathon Demo)

**What pull requests do for code, this does for business operations in spreadsheets.**

This demo is an approval-first workflow for Google Sheets, not spreadsheet chat.

Given one operator prompt, it:
1. reads a messy operations sheet (`Receivables Raw`),
2. maps non-standard headers to business concepts,
3. proposes structured row/field patches,
4. lets a user review and approve patch rows,
5. applies approved changes back into the raw sheet,
6. generates `Collections Queue` and `Report` tabs,
7. writes local audit artifacts for rollback guidance.

Demo vertical: **Accounts Receivable / collections** (platform framing remains above the vertical).

## Core Tabs

- `Receivables Raw`
- `Proposed Changes`
- `Collections Queue`
- `Report`

## Run (Preferred)

From this folder:

```bash
python3 sheetops_gws_demo.py serve --host 127.0.0.1 --port 8000
```

Open:

`http://127.0.0.1:8000`

Important: open the app from the URL above. Do not open `index.html` directly or from another static server, or `/api/*` calls may return HTML instead of JSON.

Then in UI:
1. paste an existing fake-data Google Sheet ID **or full Google Sheets link** (preferred), or click **Create Sample Sheet**,
2. keep/edit `Task Prompt` and optionally fill `Business Context` tab (context, SOP, employee operating style),
3. click **Propose Changes** (preflight asks one clarifying decision when confidence is low),
4. review/adjust selected patches,
5. click **Apply Approved**,
6. optionally click **Start Watch** to auto-detect row/tab changes and auto-generate fresh proposals,
7. show `Collections Queue` and `Report`.

The input also supports selecting recently used sheet IDs from the dropdown.

## Executive Dashboard + Operations Hub

On `Propose Changes`, the UI now shows:
- KPI cards: `Total Outstanding`, `At Risk`, `Projected Recovery`
- Health Meter: red/yellow/green operational state
- Aging Buckets: `0-30`, `31-60`, `61+` overdue exposure
- Action alert: critical patch count ready for review
- Anomaly list: notable collection risk signals

On the patch feed:
- risk badges and reasoning tooltips,
- one-click `Bulk Approve Low-Risk` for cleanup-type patches.

## Enable Real AI (OpenAI)

Set your API key in env before starting:

```bash
export OPENAI_API_KEY="<your_key>"
export OPENAI_MODEL="gpt-4.1-mini"   # optional
```

When key is present, `propose` uses AI for:
- messy column mapping (+ confidence, ambiguities),
- row-level patch reasoning (strict JSON contract),
- review intelligence (risky patch highlights + tradeoffs).

Without key, it falls back to deterministic rules.

## CLI Paths

### 1) Create sample sheet only

```bash
python3 sheetops_gws_demo.py create-demo --title "PRs for Operations AR Demo"
```

### 2) Propose patches only (no raw mutations)

```bash
python3 sheetops_gws_demo.py propose \
  --spreadsheet-id <SHEET_ID> \
  --sheet-name "Receivables Raw" \
  --prompt "We're behind on collections. Build today's collections queue and fix the follow-ups."
```

### 3) Apply approved patches

Apply all from latest matching proposal artifact:

```bash
python3 sheetops_gws_demo.py apply \
  --spreadsheet-id <SHEET_ID> \
  --sheet-name "Receivables Raw" \
  --apply-all
```

Apply selected patch IDs:

```bash
python3 sheetops_gws_demo.py apply \
  --spreadsheet-id <SHEET_ID> \
  --sheet-name "Receivables Raw" \
  --patch-ids "r2-priority,r2-next-action"
```

### 4) Backward-compatible alias

`analyze` still exists as a shortcut to `propose` + `apply --apply-all`.

## Local API Contract

The web UI calls these endpoints:

- `POST /api/create-demo`
  - input: `{ "title": "..." }` (optional)
- `POST /api/propose`
  - input: `{ "spreadsheet_id", "sheet_name", "prompt", "prompt_profile" }`
- `POST /api/preflight`
  - input: `{ "spreadsheet_id", "sheet_name", "prompt", "prompt_profile" }`
- `POST /api/apply`
  - input: `{ "spreadsheet_id", "sheet_name", "prompt", "prompt_profile", "proposal_id", "selected_patch_ids": [] }`
- `POST /api/watch`
  - input: `{ "spreadsheet_id", "sheet_name", "prompt", "prompt_profile", "auto_propose": true }`

Responses include mapping, patches, impact metadata, and artifact paths.

## Rollback / Audit Artifacts

Local artifacts are written to:

`./artifacts/`

- `*_proposal.json`: proposal snapshot (mapping, patches, row plans)
- `*_apply.json`: applied patch snapshot (before/after per cell)

Rollback is **soft rollback**: these artifacts are designed to make manual reversal clear and auditable.

## Architecture and Demo Script

- Architecture: `ARCHITECTURE.md`
- 2-minute script: `DEMO_SCRIPT.md`

## Tests

Run deterministic rule/patch tests:

```bash
python3 -m unittest -v test_patch_engine.py
```

Note: tests validate core logic only; they do not hit live Google APIs.
