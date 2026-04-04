# Architecture (PRs for Operations)

## Overview

The demo uses a single Python service (`sheetops_gws_demo.py`) that serves:
- static UI (`index.html`, `styles.css`, `app.js`),
- local JSON APIs for propose/apply,
- live Google Sheets reads/writes via `gws` CLI.

## Request Flow

1. UI sends `POST /api/propose`.
2. Backend reads `Receivables Raw`, maps messy headers, runs AR rules.
3. Backend creates structured patch objects and writes `Proposed Changes` tab.
4. UI renders patch rows (checkbox approvals).
5. UI sends `POST /api/apply` with selected patch IDs.
6. Backend writes approved changes to `Receivables Raw`, then writes `Collections Queue` and `Report`.
7. Backend stores proposal/apply artifacts in `artifacts/` for audit + rollback guidance.

## AI Layer (when `OPENAI_API_KEY` is set)

- **Column mapping**: AI maps messy headers to canonical business fields with confidence and ambiguities.
- **Patch reasoning**: AI proposes row-level `Priority`, `Assigned Owner`, `Next Action`, `Follow-up ETA`, `Reason`, `confidence` in strict JSON.
- **Review intelligence**: AI surfaces risky/ambiguous patches with tradeoffs before apply.
- **Policy adaptation**: apply decisions update `artifacts/policy_memory.json`, and acceptance patterns are fed back as policy hints in future proposes.

If AI is unavailable, deterministic rules remain the fallback path.

## Patch Model

Each patch includes:
- `patch_id`
- row location (`row_index`, `sheet_row_number`)
- `customer`
- `field`
- `before` / `after`
- `reason`
- `rule`
- `confidence`
- `projected_impact`

This is the core product primitive: reviewable operational diffs.

## Rule Engine (AR demo vertical)

Prioritization factors:
- invoice amount
- days overdue
- payment risk
- stale/missing follow-up
- missing owner
- payment status normalization

Generated operational fields:
- `Priority`
- `Assigned Owner`
- `Next Action`
- `Follow-up ETA`
- `Reason`
- `Projected Recoverable Cash`

## Safety Model

- `propose` does not mutate `Receivables Raw`.
- only `apply` mutates raw rows.
- every apply writes an artifact with before/after values for manual rollback.
