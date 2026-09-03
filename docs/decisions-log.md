# Decisions Log — Zoho Data Health Scanner → Catalyst Port

**Status: all D1–D17 items resolved.** Nothing blocking the next build phase remains
open from the validation. This document is the single source of truth — supersedes
anything in chat history or in `functional-specification.md` that conflicts with it.

**Status of underlying documents:**
- `functional-specification.md` — accurate on confirmed items; every correction below
  is pending against it and should be applied before it's used as a build reference again.
- `codex-validation.md` — the independent validation that raised D1–D17. Fully resolved below.
- The original 12-prompt Codex pack — still broadly the right build order, but Prompts
  1, 2, 5, 6, 7, 9, 10, 11 need rewriting against the decisions below before reuse.

---

## A. D1–D17 adjudication outcomes — all resolved

### A1. Spec corrections only (no design change, just fix the document)

| # | Finding | Resolution |
|---|---|---|
| D1 | Widget has a real (if limited) live Zoho CRM extraction path — not purely a mock demo | Strike spec's §10 claim that no live extraction exists |
| D3 | State precedence (`confirmed_duplicate > suspected_duplicate > suspicious > inaccurate > incomplete > proper`) is explicit and working in code | Correct "no priority constant found" claim; document the confirmed order |
| D11 | Widget's internal data model uses bitmask fields and an in-memory memoized cube, not `failedRuleIds[]`/a durable cube | Correct the spec's description of the *widget's* internals only. Production data model still targets a durable normalized schema (`record_states`, `agg_cube`) regardless |
| D15 | Widget implements 22 rules (16 per-record + 6 set-level), not 24 | Correct the count; ~48 rules still needed to reach the deck's "~70" |
| D13 | Widget's extraction is client-side `getAllRecords` + JS-side date filtering, not Bulk Read/COQL with watermark resume | No change — this was never meant to be the production extractor. Spec's Catalyst-side Bulk Read/COQL design stands |
| D10 (partial) | Missing team/min/bulk controls on Users, no send-to-fix-list, no run/preview/SOW on Fix | Already correctly flagged as deck-only/absent in spec's §10 — precision tightening only |

### A2. Code fixes against already-clear intent

| # | Finding | Fix direction |
|---|---|---|
| D6 | Repeated-phone plausibility groups all blank-phone records under one shared key → false "suspicious" flags | Guard phone truthiness before building the grouping key, matching the email path's existing correct behavior |
| D8 | Rule thresholds are configurable in the reducer but have zero UI controls wired to them | Build the threshold panel — intent is settled, work is unfinished. Fold D10's 20-observation floor (below) into this same panel |
| D9 | Setup cost estimate uses a fixed depth-cap heuristic, not real records-in-range / credit cost | Deck requires this shown before a scan runs; needs a real calculation |
| D12 | Config Hygiene domain is a crude "% of fields with any value" proxy, not the deck's real definition | **Resolved via A5 evidence** (see below) — build the real thing: unused fields/dead workflows/layout sprawl via Zoho's Workflow Rules, Workflow Usage Report, and Layouts Metadata APIs. Not an unmeasurable domain after all |
| D16 | Suspected duplicates route to the same `merge-duplicates` action as confirmed duplicates; `review-duplicates` exists but is unused | Bind `suspected_duplicate` → `review-duplicates`, reserve `merge-duplicates` for `confirmed_duplicate` only |
| D17 | API call statistics are cumulative across scans, not reset per run | Reset counters on scan start; surface the failed-count that's already tracked but not displayed |
| D15 (sub-item) | `maxExamplesPerRule` config value is never consumed; real cap is a hardcoded, inconsistent 3 | Wire the config value up for real, or remove it |
| D10 (sub-item, via A5) | Live `getUsers` doesn't populate team/role in the widget | **Resolved via A5 evidence** — Zoho's Users API does return a `role` object; this was a parsing gap, not an API limitation. Pull it off the existing response |

### A3. Access model — resolved this session (see Section B)

| # | Finding | Resolution |
|---|---|---|
| D14 | No scope verification, no disclosure of partial visibility, scan runs as whoever connects | Self-serve per-connection OAuth, developer-fixed read-only scope, no admin requirement, deliberately scoped to the connecting person's own visibility ("Personal Check" mode). Full detail in Section B |

### A4. Scoring, duplicate, and retention policy — resolved this session

| # | Decision | Resolution |
|---|---|---|
| D2a | Domain scoring formula | **Simple ratio**: `domain_score = 100 × (1 − offending/eligible)`. No severity weighting — every rule counts equally. Chosen for simplicity and to avoid the double-counting risk severity-weighting introduced in the widget's implementation |
| D2b | Handling of unmeasurable domains (PII, Automation) in the overall score | **Renormalize but disclose.** Overall score is computed from measurable/applicable domain weights only, with the UI stating plainly how many of the 100 points were actually measured (e.g. "92 of 100 possible points measured — PII and Automation Health need broader access") |
| D4 | User score formula | **Same weighted-domain formula as org/module** — one scoring path everywhere, not a separate metric. Percent-of-records-in-proper-state is kept as a secondary display stat only, never as *the* score |
| D5 | Duplicate detection policy | **Module-scoped only for v1** (cross-module deferred). **Block-size cap removed as a silent skip** — oversized blocks get processed or explicitly flagged, never dropped without disclosure. **0.90 confidence floor is absolute** — the email+phone / email+strong-name-similarity shortcut that bypassed it is removed. Exact match on a strong statutory identifier (GSTIN/PAN/etc.) still auto-confirms independently — that's a legitimate separate path, not a floor bypass |
| D7 | Data retention boundary | IDs, module, state, failed rule IDs, stage, timestamps, and display names are permitted to persist (they're what the product is for). Reason strings must be templated, never echoing an actual field value (e.g. "GSTIN failed checksum," never the GSTIN itself). Duplicate-matching keys are cleared once that scan step completes |
| D10 (sub-item) | Modules matrix "worst cell" 20-observation floor | Keep the floor (avoids noisy scores off tiny samples), but make it visible and configurable via the same threshold panel being built for D8 |

### A5. Evidence gathered — both resolved via direct API research

| # | Question | Finding |
|---|---|---|
| D10 (team/role) | Does Zoho's Users API expose team/role data at all? | **Yes.** Returns a `role` object (name + ID); a separate Roles API provides the full hierarchy. The widget's blank team column was a code gap, not an API ceiling |
| D12 (config hygiene feasibility) | Can even an elevated integration identity see workflow/layout usage metadata? | **Yes.** Zoho provides a Workflow Rules API (with `last_execution` timestamps and a `deprecated` flag — direct dead-workflow detection), a Workflow Rule Usage Report, and a Layouts Metadata API reporting whether a field/section is actually used. Config Hygiene can be built as originally specified, with the right scopes (`ZohoCRM.settings.workflow_rules.READ`, `ZohoCRM.settings.layouts.READ`) |

---

## B. Access and connection model

### B1. Two separate identity layers

1. **App-level login** (Catalyst's own signup/login) — the consultant/operator's own account. Standard Catalyst user management.
2. **Per-connection OAuth** — a separate identity per connected Zoho login, independent of the operator's app account. One operator account can have many connections.

### B2. Scope is developer-fixed, not client-selectable

One fixed, minimal, read-only scope bundle requested at OAuth time (CRM modules/records/users, read only, no writes). No in-app scope picker.

### B3. No admin requirement (for now)

Any role can connect. Admin-gating was considered and deferred, not rejected outright — see B5.

### B4. Personal Check mode — the only mode being built right now

Zoho itself filters what a connected token can see (modules, fields, records) — the app does no extra restriction, it just displays what comes back honestly, scoped to that login.

- **Setup screen**: module list/counts reflect only what this login can see, with explicit copy saying so.
- **Report labeling**: "your data health," first-person throughout — never "org health."
- **Users tab**: single-user detail view (own state mix, own trend), not a comparison table.
- **Modules, Trend, Records, Fix tabs**: unchanged, operating on a smaller self-scoped record set.

### B5. Org Audit mode — deferred, not built now

Shape already known for later: admin-profile check at connect time (Zoho's "get current user" call, or the more robust `AdminUsers` filter rather than name-matching), a mode toggle, Users tab reverts to a comparison table for that mode only. An addition on top of what's built now, not a rebuild.

### B6. Data model implication

A "connection" is one row per **person's OAuth grant**, not per org. Multiple people from the same org can each connect separately. `orgs`/`token_vault` from the original prompt pack need to become connection-centric (track the connecting person's profile info, plus a `mode` field for when Org Audit is added).

---

## C. What this changes in the original Codex prompt pack

- **Prompt 1 (Data Store schema)** — connection-centric per B6; add `agg_cube` fields for the disclosed-renormalization score (D2b) and templated reason strings (D7).
- **Prompt 2 (Auth service)** — no admin-check logic; fixed developer-defined scope allowlist per B2; "get current user" call retained for report labeling, not gating.
- **Prompt 5/6 (Rule engine, scoring)** — build against the simple-ratio formula (D2a) with disclosed renormalization (D2b); no severity weighting.
- **Prompt 7 (Duplicate detection)** — module-scoped only, absolute 0.90 floor, no confirmation shortcuts, block-overflow must be disclosed not silently skipped (D5).
- **Prompt 9 (Scan orchestration/API)** — Personal Check framing baked into every response shape ("your score," not "org score"); Config Hygiene built for real per A5, not stubbed.
- **Prompt 10/11 (React frontend)** — Users tab as single-user view (B4); threshold panel includes the 20-observation floor (D10) alongside D8's other thresholds; setup screen shows real records-in-range/credit cost (D9), not a cap-based estimate.

---

## D. Immediate next steps

1. Revise `functional-specification.md` against Sections A and B above.
2. Rewrite Prompts 1, 2, 5, 6, 7, 9, 10, 11 from the original Codex pack against this
   decisions log.
3. No open product decisions remain — next session can go straight to prompt-writing
   and, when credits are back, execution.
