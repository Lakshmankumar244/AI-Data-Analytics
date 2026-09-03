# Approved Product Contract

**Source of authority:** `product-decision-register.md`, updated with the approval table below.
**Status:** Partial approval. This document is authoritative **only** for the decisions explicitly marked approved. Every other item from the register remains in force at whatever status the register assigned it (resolved documentation/implementation fix, or still unresolved) and is carried forward unchanged, not re-decided here.
**Rule:** Nothing in this document goes beyond what was explicitly approved. Where an approval was given at the topic level without specifying the underlying mechanism, that gap is flagged rather than filled in.

---

## 0. How to use this document

This contract is meant to become the authoritative input for:

- **The rule catalogue** — pull scoring mechanics, state definitions, and duplicate/plausibility policy from Section 1 and 3 only where marked fully specified.
- **Golden test cases** — build fixtures against the formulas and thresholds in Section 1's Implementation Details, not against the widget's current behavior where the two diverge.
- **Catalyst architecture** — build extraction, authorization, and persistence design against Section 1's D13, D14-POLICY, D14-EVIDENCE, and D7 entries.

Any item listed in Section 4 (Not Yet Approved) must **not** be used to author rule logic, test fixtures, or architecture until it is fully specified. Treat those gaps as blockers for the specific areas they touch, not as license to infer a reasonable default. D14-EVIDENCE (Section 1) is scoped but not yet verified — see its entry for what that means in practice.

---

## 1. Approved Decisions

Each entry separates **Product Requirement** (what the product must do, stated at the business/behavior level) from **Implementation Detail** (the specific mechanism approved to satisfy it).

### D2 — Scoring formula: Severity-weighted scoring (Option A)

**Status:** ✅ Approved

**Product Requirement:**
Domain scores must reflect the relative severity of failed rules, not merely the count or presence of failing records. The overall organizational score must not be penalized for domains that cannot currently be measured (PII/Access, Automation Health) — those domains are excluded from the score's basis rather than counted as failing.

**Implementation Detail:**
- Domain score = severity-weighted mean of per-rule pass rates.
- Approved severity coefficients: `critical = 3`, `high = 2.5`, `medium = 2`, `low = 1.5`, `info = 1`.
- Overall score = weighted sum of domain scores, divided by the sum of **applicable, measurable** domain weights only (unmeasurable domains excluded from the denominator, not scored as zero).
- A single record may contribute to `eligible`/`offending` totals more than once if it fails multiple rules within a domain. This is an adopted characteristic of the approved formula, not an error, and must be documented explicitly anywhere the score is explained to a customer (any "X of Y records fail" language must be checked for consistency with this counting method before being used in copy or reporting).

**Carries forward from register:** This resolves D2 in full, including its interaction with D12 (Configuration Hygiene domain weighting) wherever D12 is eventually resolved — D12 remains unresolved (see Section 4) and this formula must be re-validated once D12 is settled.

---

### D4 — User score: Percent-proper (Option 1)

**Status:** ✅ Approved

**Product Requirement:**
User score represents the percentage of a given user's own records that are in the `proper` (clean) terminal state, shown only once that user's record count meets a minimum floor. This is deliberately a simple, self-diagnostic "percent clean" metric for individual coaching — it is **not** the same metric as org/module score (D2's severity-weighted formula), and the two must never be presented or implied as directly comparable without explicit labeling to that effect.

**Implementation Detail:**
- User score = `properPct` — the percentage of that user's records whose terminal state is `proper` — gated by the existing minimum-record floor before the score is surfaced.
- Coaching bands operate on this percent-clean value.
- This matches current widget behavior (`Sg.byUser`); no engineering change is required for the formula itself.
- Any UI or reporting surface that displays user score alongside org/module score must label them distinctly (e.g., "percent clean" vs. "quality score") to avoid implying a shared formula.

---

### D5 — Duplicate policy (fully resolved)

**Status:** ✅ Approved — all four sub-decisions resolved

**Product Requirement:**
Duplicate detection ships with a defined, defensible confirmation policy: shortcuts are limited to very strong exact matches; matching scope is deliberately bounded to within-module for v1; oversized candidate blocks are still fully evaluated (via splitting) rather than silently skipped; and the blocking strategy is fully documented rather than containing undocumented behavior.

**Implementation Detail:**

**D5.1 — Confirmation shortcuts.** Kept, restricted to exact matches only:
- Exact strong-identifier match (e.g., a government/tax ID or other unique strong identifier field) → confirms directly.
- Exact email match **+** exact phone match (both fields exact) → confirms directly.
- Removed: the shortcut allowing exact email + name similarity ≥0.90 to confirm without meeting the 0.90 overall confidence floor.
- All other pairs use the standard rule: confidence ≥0.90 **and** two strong fields agreeing exactly (spec §6.7). Scores of 0.70–0.90 remain `suspected_duplicate` and route to human review (per D16).

**D5.2 — Cross-module scope.** Matching remains **within-module only for v1** (Leads, Contacts, Accounts, and Vendors are not compared against one another). This is an explicit, deliberate v1 scope decision, not an oversight — cross-module matching may be reconsidered in a later phase but is out of scope now. The rule catalogue and golden test cases should treat within-module matching as the confirmed v1 behavior and should not build cross-module test fixtures for this release.

**D5.3 — Block-overflow handling (>40 records).** Blocks exceeding 40 records are no longer skipped. Instead, oversized blocks are **split into smaller batches** for evaluation, so every record still gets compared rather than silently excluded. Implementation must define a deterministic splitting strategy (e.g., fixed sub-block size with a consistent ordering rule) so that batch boundaries don't themselves introduce missed comparisons at the edges — this deterministic-splitting design is engineering work under this approved direction, not a separate open product decision.

**D5.4 — Name-blocking key.** The normalized-name-prefix blocking key (`|nm|`, first 8 normalized characters) is **kept** and must be **formally documented** — in the spec's §6.7 duplicate-detection description and in the rule catalogue — as an intentional additional blocking strategy alongside the existing signature-based blocking, rather than left as an undocumented implementation detail.

**Golden test coverage required for this item:**
- Exact strong-ID → confirmed.
- Exact email + exact phone → confirmed.
- Exact email + fuzzy name match → falls to `suspected_duplicate`, not confirmed.
- Within-module pairs matched; cross-module pairs (same person represented in two modules) correctly **not** matched for v1.
- A block of >40 records is split and every record within it is still evaluated (no silent exclusions at or near split boundaries).
- The `|nm|` blocking key is exercised and documented as expected behavior, not a bug.

---

### D7 — Data retention: Session data + minimized persistence (Option 3)

**Status:** ✅ Approved

**Product Requirement:**
The product's UI claim of "identifiers and states only" governs anything that leaves the active browser session — exports, and any future Catalyst-persisted data. Within an active session, the tool may retain richer working context (names, labels, stage) to support usability, but that richer context must never be exported or persisted beyond the session.

**Implementation Detail:**
- **In-session working facts** (memory only, cleared at session end): may retain record label, creator/modifier/owner names, stage, timestamps, and issue messages as currently implemented — this tier is not required to change.
- **Anything exported or persisted** (CSV export, any future Catalyst storage): must be reduced to the minimal tuple — record ID, module, state, rule/reason identifiers, and duplicate confidence/partner reference where applicable. No names, labels, stage values, or embedded source field values (e.g., flagged dummy values, invalid picklist values) may appear in exported or persisted output.
- The duplicate-pair array (`Eu`) is subject to the same rule: acceptable to retain in-session, but any export or Catalyst persistence of duplicate-pair data must be reduced to the minimal tuple (pair reference, confidence, state) with blocking-key raw values (which can contain normalized emails/phones/statutory IDs) excluded.
- TTL, deletion trigger, and audit-log retention duration for anything persisted under Catalyst are **not** specified by this decision and remain open (see Section 4, formerly part of D7's broader retention questions in the register — the *scope* of what's minimized is now decided; *how long* Catalyst retains the minimized tuple is not).

---

### D13 — Date-bounded extraction: Batch processing + persisted batch results

**Status:** ✅ Approved

**Product Requirement:**
Scans must be built on a durable, resumable batch/job model rather than best-effort client-side pagination. A scan's completeness must be verifiable and its progress must not be silently lost if interrupted.

**Implementation Detail:**
- Extraction moves from the current client-side `getAllRecords` + JavaScript filtering approach to a bounded batch/job architecture (e.g., COQL or Bulk Read as the date-bounded collector, consistent with the register's evidence-gathering note on rate limits/latency/date-filtering capability — that technical verification is not itself part of this approval and should still be confirmed during build).
- Each batch's results are **persisted** (not held only in browser memory) so that: (a) a job can resume from a checkpoint after interruption rather than restarting, and (b) completeness can be audited after the fact rather than trusted implicitly.
- The prior client-side heuristic (sort by clock field, stop after >25 older records) is superseded by this approach and should not be carried into Catalyst as the primary collector.
- Watermark/resume semantics, the exact persisted-batch data shape, and null/malformed-timestamp handling are implementation design work under this approved direction, not separate open product decisions — but should be documented as part of the Catalyst architecture build, not invented here.

---

### D14-POLICY — Authorization/visibility model: Admin-authorized organization connection (Option B)

**Status:** ✅ Approved

**Product Requirement:**
The product connects to a customer's CRM org through an explicit, admin-authorized, org-wide integration — not through an individual operator's personal sign-in session. An organization administrator must take an explicit action to authorize the connection. Scan results are intended to reflect org-wide visibility, subject to whatever the integration identity's granted scopes actually permit (see D14-EVIDENCE below — this has not yet been technically verified).

**Implementation Detail:**
- Build an admin-facing connection/consent flow, separate from any individual operator's CRM login.
- Request and document explicit read scopes for the integration identity, scoped per Zoho product/module as needed.
- Disclose to the admin, at the point of connection, what data the integration will access.
- Because scans now run under an org-wide identity rather than a signed-in operator's own visibility, any comparison to prior single-user-scoped scores (if such comparisons exist anywhere in reporting) must be clearly labeled as not directly comparable across the two models.

---

### D14-EVIDENCE — Technical verification items

**Status:** 🟢 Defined — **plan scoped, verification not yet completed**

**Product Requirement:** N/A — this is a technical evidence-gathering item, not a product-facing requirement.

**Implementation Detail — verification plan (from the register, carried forward unchanged):**
1. Determine whether Zoho CRM APIs expose any queryable signal that an identity's visible record count is less than a module's true total (e.g., comparing scoped vs. admin-level counts).
2. Determine what OAuth scopes are actually requested/granted under the D14-POLICY admin-authorized integration model, and whether they can be introspected at runtime.
3. Determine how record-level sharing rules, territory management, and role hierarchies affect `getAllRecords`/COQL results in practice, ideally verified against a real or realistic sandboxed org with non-trivial sharing rules configured.

> ⚠️ **This is "Defined," not "Resolved."** The verification plan is approved and scoped — engineering should execute it — but its outcomes are not yet known. **D14-POLICY's implementation must not assume full org-wide visibility is technically guaranteed until this verification is complete.** If the evidence shows visibility gaps are possible even under the admin-authorized model, that finding must be fed back into D14-POLICY's implementation (e.g., a partial-visibility disclosure mechanism) rather than silently ignored.

---

### TZ-1 — Organization timezone + proper close timestamp

**Status:** ✅ Approved

**Product Requirement:**
Time-based plausibility findings (burst detection, off-hours detection) must reflect the customer organization's actual business timezone, not the operator's local browser timezone. Any rule that determines a record is "closed" for freshness/audit purposes must use a genuine close/audit event, not a proxy that can be misleading (such as `Modified_Time`, which can change for unrelated reasons after a record is actually closed).

**Implementation Detail:**
- Fetch the CRM org's configured timezone (via org metadata) at scan setup and apply it uniformly across all time-based rule evaluation (burst window, off-hours detection, and any fiscal-period-adjacent calculations).
- Identify and use the correct audit/close timestamp field per module where one exists in the CRM data model, rather than defaulting to `Modified_Time`.
- Where a true close/audit timestamp is **not** available for a given module (this has not been verified), the rule catalogue must document `Modified_Time` as an explicit, disclosed approximation rather than silently substituting it — confirming field availability per module is implementation verification work under this approved direction, not a separate open product decision.

---

## 2. Summary — Approved but Underspecified

None remaining. D4 and D5 were the only items in this category; both are now fully resolved (see Section 1).

---

## 3. Carried Forward Unchanged — Already Resolved in the Register

These were resolved in `product-decision-register.md` prior to this approval round, as documentation corrections or implementation fixes (not open product decisions). They remain authoritative and are not re-litigated here.

**Documentation corrections** (spec must match confirmed code behavior):
- **D1** — Live extraction path exists; spec's "synthetic-only" claim is corrected.
- **D3** — State precedence (`proper < incomplete < inaccurate < suspicious < suspected_duplicate < confirmed_duplicate`) is already explicit in code and matches the spec's own proposed ordering; only the spec's "not found" claim needed correction.
- **D11** — Data model documentation (fact shape, cube, duplicate-pair structure) corrected to match executable state.
- **D15-COUNT** — Rule count corrected to 22 (16 record rules + 6 set rules), not 24.

**Implementation fixes** (bugs against already-stated intent, not open questions):
- **D6** — Repeated-phone plausibility must exclude blank phone values from grouping, matching the existing email-path behavior.
- **D16** — Suspected duplicates must route to a `review-duplicates` action, not be aggregated into `merge-duplicates`; `merge-duplicates` is reserved for confirmed duplicates only (subject to D5's still-open confirmation policy, once specified). Fix action gain totals must be computed against the combined rescored selection, not summed independently per action.
- **D17** — API statistics (`apiStats`) must reset per scan run; the already-tracked failed-call count must be surfaced on the running screen.

---

## 4. Not Yet Approved — Remains Unresolved

These items were **not** included in the approval table and remain exactly as `product-decision-register.md` left them: `TBD — PRODUCT DECISION REQUIRED`. No content is invented for them here.

| ID | Topic |
|---|---|
| D8 | Threshold configurability in the UI (build the editable panel for v1, defer, or read-only) |
| D9 | Setup cost/runtime estimate accuracy (build a real records-in-range estimator, or relabel the cap-based approximation) |
| D10 | Screen behavior gaps across Modules, Users, Trend, Records, and Fix tabs |
| D12 | Configuration Hygiene domain definition and scope (org-level-only vs. module-aware vs. rename) |
| D15-KNOB | Whether to implement or remove the dead `maxExamplesPerRule` configuration |

These items do not block the architecture-affecting work enabled by Section 1, but they must be resolved before the affected areas (Setup screen, Modules/Users/Trend/Records/Fix tabs, the Configuration Hygiene rule, and threshold-editing UI) are built out or included in golden test coverage.

---

## 5. Go/No-Go for Implementation — Reassessment

**Previous status (register v1): NO-GO**, pending resolution of D2, D4, D5, D7, D13, D14-POLICY, D14-EVIDENCE, and TZ-1.

**Updated status: Conditional GO for architecture and extraction work; NO-GO for user-score and duplicate-detection rule authoring.**

- **Cleared to proceed:** Scoring engine (domain/overall formula per D2, user score per D4), data retention/export minimization boundary (D7), extraction architecture (D13), authorization/connection model (D14-POLICY), timezone/close-timestamp handling (TZ-1), and the full duplicate-detection policy (D5, all four sub-decisions) are now fully specified and may be used to author Catalyst architecture, the rule catalogue, and golden test cases for the areas they cover.
- **Still blocking:**
  - **D14-EVIDENCE** must be executed (not just "defined") before D14-POLICY's implementation can be considered complete — architecture work may proceed on the admin-authorized connection model, but must not assume full visibility guarantees until verification results are in.
  - **D8, D9, D10, D12, D15-KNOB** remain fully unresolved and out of scope for any implementation work until separately decided.

This document should be re-issued as a new version once D14-EVIDENCE's verification results are finalized, at which point full GO status can be reassessed for the remaining architecture-affecting item.
