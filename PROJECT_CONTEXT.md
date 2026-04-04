# Project Context

## One-Line Summary

This project is pivoting to **PRs for Operations**: a Codex-style agent for Google Sheets that reads messy operational spreadsheets, proposes structured fixes as reviewable changes, then applies them and generates an audit-ready report.

## Why This Exists

The original spreadsheet-agent idea risked feeling like:

- upload a sheet
- ask a question
- get an AI answer

That is too close to generic spreadsheet chat.

The stronger direction is:

- understand messy sheet structure
- apply a domain rule pack
- propose actual operational changes
- let the user review and approve those changes
- write the changes back into the sheet
- leave a report tab showing what changed and why

The key framing is:

**This is not spreadsheet Q&A. This is operational patch review for spreadsheets.**

## Product Thesis

Codex works because it does more than answer questions about code:

- it reads messy context
- proposes structured edits
- shows diffs
- applies changes safely

This project brings that interaction model to spreadsheets.

### Core Analogy

**What pull requests do for code, this does for business operations in Sheets.**

## Current Product Direction

The product should be described as:

**PRs for Operations**

An agent that turns messy operational spreadsheets into executable, reviewable work queues.

## What The Product Should Do

Given a Google Sheet and a one-sentence prompt, the agent should:

1. read the active workbook or selected sheet
2. map messy headers to known business concepts
3. run a domain-specific rule pack
4. generate proposed changes
5. show those changes in a reviewable form
6. apply approved changes back into the sheet
7. create supporting tabs that act as operational artifacts

## Not The Product

This project should **not** be pitched as:

- AI that understands spreadsheets
- spreadsheet chatbot
- upload CSV and ask questions
- dashboard generator
- report-only assistant

If it only analyzes data and writes commentary, it is too weak and too replaceable.

## What Counts As A Real Fix

A real fix is not just a recommendation paragraph.

A real fix means changing workflow state inside the spreadsheet, for example:

- setting `Priority`
- assigning missing owners
- generating `Next Action`
- setting `Follow-up Date`
- normalizing status values
- creating a clean execution queue tab
- creating a report tab with impact and justification
- optionally supporting review, apply, and rollback

## Current Demo Domain

The current live demo uses **Accounts Receivable / collections ops** because it is universal and easy for judges to understand.

Example user prompt:

`We're behind on collections. Who should I chase first and fix the follow-ups.`

### Why AR Was Chosen

- everyone understands overdue invoices
- business value is obvious
- prioritization is explainable
- it supports visible writeback into the sheet

## Domain Logic In The Current Demo

The current AR demo ranks accounts using factors like:

- invoice amount
- days overdue
- payment risk
- stale or missing follow-up
- missing owner
- payment state

It writes back fields like:

- `Agent Priority`
- `Next Action`
- `Recovery ETA`
- `Agent Note`

And it creates a `Report` tab with:

- ranked accounts
- projected recoverable cash
- reasons for prioritization

## What Still Needs To Change In The Product Story

The current AR implementation is useful, but it is still closer to:

- structured reporting
- action generation

than to the final ideal:

- patch proposal
- human review
- apply / rollback workflow

So the product story should always emphasize the next step:

**reviewable patches for spreadsheet operations**

## Target UX

The intended UX is:

1. user opens a Google Sheet
2. user types one sentence
3. agent reads messy tabs / data
4. agent maps fields
5. agent proposes changes in a review panel
6. user approves
7. sheet is updated
8. audit/report tabs appear

### Strong UX Artifacts

The product should eventually show:

- proposed changes
- confidence / rationale
- impacted rows
- projected outcome
- apply button
- rollback button

## Multi-Sheet Direction

This project should support multiple tabs naturally.

The mental model should be:

- `Raw Data`: original messy operational export
- `Proposed Changes`: pending AI patch set
- `Work Queue`: executable actions for operators
- `Report`: summary of what changed and expected impact
- optional `Config` or `Rules`: business preferences

Another AI continuing this project should treat multi-sheet handling as a core feature, not an edge case.

## Current Repo Files

### UI Prototype

- `index.html`
- `styles.css`
- `app.js`

These files are a static prototype that demonstrates the interaction pattern visually.

Important note:
The static prototype originally started from a Google Ads example and may still contain older framing or copy. The correct product framing is now **PRs for Operations**, not a Google Ads vertical demo.

### Live Google Sheets Demo

- `sheetops_gws_demo.py`

This script currently uses the locally authenticated `gws` CLI to create and update a live Google Sheet for the Accounts Receivable demo.

It currently:

- creates a sample sheet
- writes fake AR data
- analyzes rows
- writes action columns back
- creates a `Report` tab

This is the working integration path right now.

### Supporting Docs

- `README.md`

This should be kept aligned with the pivot, but `PROJECT_CONTEXT.md` is the main handoff file for future AI sessions.

## Integration Notes

### Google Sheets

The reliable path in this workspace is currently `gws`, not the Composio `googlesheets` execution flow.

Observed behavior:

- Composio account records existed, but execution returned `NoActiveConnection`
- local Google auth via `gws` was able to create and update spreadsheets successfully

Future agents should assume:

- `gws` is the working path unless proven otherwise
- Composio may need reconnect / session repair before use

## Hackathon Positioning

This project maps best to:

- **UX for Agentic Applications**
- **Domain Agents**
- optionally **Building Evals**

It is less compelling if pitched as a raw vertical app.
It is more compelling if pitched as a new interaction model for spreadsheets.

## Short Pitch

Use this pitch:

**PRs for Operations is a Codex-style agent for Google Sheets. It reads messy operational spreadsheets, proposes reviewable fixes, applies approved changes, and creates an audit-ready report.**

## Even Shorter Pitch

Use this if time is tight:

**Codex for ops spreadsheets: review, patch, apply, report.**

## Demo Walkthrough

Use this flow in a demo:

1. open the raw sheet
2. show that the data is messy and operational
3. give one sentence prompt
4. show mapped fields and proposed actions
5. apply the changes
6. open the generated queue/report tab
7. show business impact

## Current Gaps

These are the main unfinished parts:

- no true review diff UI yet
- no rollback flow yet
- static prototype and live script are not fully unified
- some copy still reflects earlier directions
- the AR demo is strong, but the platform framing must stay above the vertical

## Recommended Next Steps

If continuing this project, prioritize in this order:

1. build a real review/apply diff layer
2. split output into `Proposed Changes` and `Applied Report`
3. make the same flow work for multi-sheet workbooks
4. tighten the product copy so every screen says **PRs for Operations**
5. optionally add an eval harness for expected row ranking / patch correctness

## Guidance For Another AI

If you are another AI continuing this repo:

- do not frame this as spreadsheet chat
- do not optimize for a report-only assistant
- optimize for reviewable operational changes
- keep the product framing above any single vertical
- treat AR as the demo domain, not the entire product
- prefer `gws` for live Google Sheets interaction in this environment

The most important thing to preserve is this:

**The product is about turning messy spreadsheet context into reviewable operational patches.**
