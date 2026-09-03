# Product Decision Register

**Source documents:** `reverse-engineered-spec.md`, `codex-validation.md` (independent validation against `original-widget.zip` and `product.pptx`)
**Purpose:** Resolve every discrepancy that requires a product or technical decision before Catalyst implementation begins.
**Status of this document:** Living register. Every entry marked `TBD — PRODUCT DECISION REQUIRED` blocks implementation of the area it touches until resolved.

---

## 1. Decision Status Summary

| ID | Topic | Category | Status |
|---|---|---|---|
| D1 | Live extraction path exists | Documentation correction | ✅ Resolved |
| D2 | Scoring formula (domain/overall) | Product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D3 | State precedence ordering | Already determined from existing intent | ✅ Resolved (doc fix only) |
| D4 | User score formula | Product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D5 | Duplicate scope & confirmation policy | Product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D6 | Repeated-phone plausibility (blank grouping) | Implementation fix | ✅ Resolved (fix scoped) |
| D7 | Data retention & export minimization | Product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D8 | Threshold configurability (UI) | Product approval (scope) | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D9 | Setup cost/runtime estimate accuracy | Product approval (scope) + technical evidence | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D10 | Screen behavior gaps (multiple) | Product approval (scope) | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D11 | Reconstructed data model mismatch | Documentation correction | ✅ Resolved |
| D12 | Configuration hygiene domain definition/scope | Product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D13 | Date-bounded extraction architecture | Technical evidence + product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D14-POLICY | Authorization/visibility model | Product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D14-EVIDENCE | Actual Zoho scope/visibility behavior | Technical evidence | 🟡 Evidence required |
| D15-COUNT | Rule count (22 vs. 24) | Documentation correction | ✅ Resolved |
| D15-KNOB | `maxExamplesPerRule` dead configuration | Product approval | 🔴 TBD — PRODUCT DECISION REQUIRED |
| D16 | Duplicate fix routing / projected-gain math | Already determined from existing intent | ✅ Resolved (fix scoped) |
| D17 | API statistics reset/display | Implementation fix | ✅ Resolved (fix scoped) |
| TZ-1 | Timezone & audit "closed" timestamp semantics | Product approval + technical evidence | 🔴 TBD — PRODUCT DECISION REQUIRED |

**Gating for implementation:** D2, D4, D5, D7, D13, D14-POLICY, D14-EVIDENCE, TZ-1 are architecture-affecting and block a Catalyst implementation start. D8, D9, D10, D12, D15-KNOB are scope decisions that affect release planning but do not by themselves block starting core architecture work once the gating items above are resolved.

---

## 2. Decisions That Require Product Approval

### D2 — Scoring formula (domain and overall)

- **Decision ID:** D2
- **Topic:** How domain scores and the overall org score are calculated.
- **Current widget behavior:** For each domain, the code computes each rule's pass rate, multiplies it by a severity coefficient (`critical 3`, `high 2.5`, `medium 2`, `low 1.5`, `info 1`), and averages those weighted rule scores. `eligible`/`offending` totals can count a single record more than once if it fails multiple rules. The overall score divides by the sum of *applicable, measurable* domain weights only — unmeasurable domains (PII/Access, Automation Health, 7 points) are excluded from the denominator rather than scored as zero.
- **Current specification behavior:** §6.5 documents domain score as `1 - (unique offending records / eligible records)`, and implies unmeasurable domains contribute zero rather than being excluded from the denominator.
- **Exact conflict:** Two structurally different formulas exist for the same named concept ("domain score"), and two different renormalization behaviors exist for "overall score." They will not produce the same number for the same data.
- **Why it matters:** This is the number every gauge, band, comparison, and coaching decision in the product is built on. Silently picking either the code's or the spec's formula without approval means shipping a scoring methodology no one has actually signed off on, and any historical/demo numbers shown to prospects were generated under a third, undocumented behavior.
- **Available options:**
  1. Adopt the code's severity-weighted mean, formalize the coefficients, and update the spec.
  2. Adopt the spec's unique-offending-records formula and rebuild the scoring engine to match.
  3. Design a new formula that combines both intents (e.g., severity-weighted but strictly at the unique-record level).
- **Consequences of each option:**
  1. Fastest path to parity with the existing demo; but severity coefficients (3/2.5/2/1.5/1) have never been product-approved and double-counting a record across multiple failed rules is defensible but needs to be stated explicitly, not left implicit.
  2. Matches the deck's worked example and is easier to explain to customers ("X% of records are clean"), but requires new engineering work and will likely produce different scores than any existing demo, which needs to be communicated to stakeholders who have seen the current numbers.
  3. Most correct long-term, but adds design and engineering time before any Catalyst work can start.
- **Recommended option:** Cannot be reasonably recommended from available evidence. Both formulas represent legitimate but incompatible product philosophies (severity-weighted quality signal vs. simple pass/fail transparency), and the deck's own worked example uses language ("X of Y eligible records fail") that only the record-based formula makes safe to say. This must be a deliberate call, not an engineering default.
- **Evidence required:** None beyond product intent — this is a pure policy choice.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner (scoring methodology), with sign-off from whoever owns customer-facing claims about the score (sales/deck owner).
- **Acceptance criteria:** A single documented formula for domain score and overall score, with approved severity coefficients (if kept) and an explicit statement of how unmeasurable domains affect the denominator. All customer-facing "X% of records" language must be checked for consistency with the chosen formula.
- **Impacted implementation areas:** Scoring engine (`Sg.compute`), Overview tab gauge/bars, Modules matrix, prior-comparison logic, all customer-facing copy referencing percentages.

---

### D4 — User score formula

- **Decision ID:** D4
- **Topic:** What "score" means when applied to an individual CRM user, and what drives coaching bands.
- **Current widget behavior:** `Sg.byUser` computes `score = properPct` — the percentage of that user's records whose terminal state is `proper` — gated by a minimum-record floor. Coaching bands are driven by this percent-clean value.
- **Current specification behavior:** The spec treats "score" as a single concept applied uniformly across org, module, and user levels, implying the same weighted-domain formula applies everywhere.
- **Exact conflict:** Org/module scores use a severity-weighted domain formula (see D2); user scores use plain percent-proper. These are not the same metric wearing the same label.
- **Why it matters:** If a manager compares "my team averages 82" against "the org is at 82," they may be comparing two different formulas that happen to look alike. Coaching decisions and any manager rollups will be built on whichever formula is chosen, and this also determines whether D2's resolution needs to propagate to the user level.
- **Available options:**
  1. Keep user score as percent-proper (simple, explainable to individual contributors: "82% of your records are clean").
  2. Switch user score to the same weighted-domain formula used at org/module level, for consistency.
  3. Show both: percent-proper as the primary "your records" metric, and a separate weighted quality score for cross-level comparison.
- **Consequences of each option:**
  1. Simplest and most motivating for individual coaching, but not directly comparable to org/module scores — any dashboard that plots user score next to module score is comparing apples to oranges unless explicitly labeled.
  2. Enables true apples-to-apples rollups (team score = weighted mean of user scores comparable to module score), but percent-proper is easier for a non-technical user to self-diagnose against and may be lost.
  3. Best of both, but doubles the UI surface and requires deciding which one drives coaching-band thresholds and gamification, if any.
- **Recommended option:** Cannot be reasonably recommended without knowing whether "coaching band" is meant to motivate individual behavior change (favors percent-proper) or to feed manager rollups comparable to org/module reporting (favors the weighted formula). This depends on D2's resolution and the intended audience for the Users tab.
- **Evidence required:** None — depends on D2's outcome and product intent for the Users tab audience.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner (scoring methodology) — should be resolved alongside D2.
- **Acceptance criteria:** A documented user-score formula, explicit statement of whether/how it relates to the org/module formula, and confirmation of which value (if either) feeds coaching bands and any future manager rollups.
- **Impacted implementation areas:** `Sg.byUser`, Users tab, coaching bands, any future team/manager rollup feature (currently missing per D10).

---

### D5 — Duplicate scope and confirmation policy

- **Decision ID:** D5
- **Topic:** Which records are compared for duplicates, and what confidence/field combination is sufficient to auto-confirm a duplicate.
- **Current widget behavior:** Blocking keys are prefixed by module, so matching never occurs across Leads/Contacts/Accounts/Vendors. An undocumented normalized-name prefix block (`|nm|`, first 8 normalized characters) exists alongside the documented signature-based blocking. Blocks larger than 40 records are skipped entirely (no comparison happens inside them). Exact strong-ID matches confirm directly; additionally, exact email + exact phone, or exact email + name similarity ≥ 0.90, can confirm a duplicate *without* meeting the documented 0.90 overall confidence floor — meaning a displayed confidence can be below 0.90 on a record marked "confirmed."
- **Current specification behavior:** §6.7 documents blocking key generation, weighted fuzzy scoring, a 0.70–0.90 "suspected" band, and confirmation only above 0.90 *with two strong fields agreeing*. Cross-module scope, the name-blocking key, the 40-record block cap, and the sub-0.90 shortcut paths are not documented.
- **Exact conflict:** The spec describes a single, conservative confirmation rule (>0.90 confidence AND two strong fields). The code implements several additional confirmation shortcuts that can produce a "confirmed duplicate" label at a confidence below the documented floor, and silently drops all comparisons in any block larger than 40 records.
- **Why it matters:** `confirmed_duplicate` is the highest-precedence state and is the input to the `merge-duplicates` fix action (see D16) — the one category where a workflow could plausibly lead to destructive action (merging records) in a future release. False confirmations here are the highest-consequence failure mode in the entire tool. This is explicitly called out in the validation report as a critical-severity risk.
- **Available options:**
  1. Remove the confirmation shortcuts; require the documented 0.90-plus-two-strong-fields rule everywhere, and never display "confirmed" below that floor.
  2. Keep the shortcuts but document and product-approve them explicitly as a deliberate accuracy/recall trade-off, with a clearly stated rationale for each one.
  3. Move all "confirmed" results to require human confirmation regardless of algorithmic path (i.e., no auto-confirm at all pre-Catalyst).
  4. Separately, decide whether matching should be within-module only (current), cross-module (spec's implicit expectation), or configurable per deployment; and decide the policy for blocks over 40 records (raise the cap, sample within the block, or split it).
- **Consequences of each option:**
  1. Safest, most defensible position; may reduce recall (miss some true duplicates that the shortcuts currently catch) and requires engineering changes.
  2. No engineering change needed if the shortcuts are genuinely intentional, but requires someone to be willing to sign off on "confirmed" meaning something looser than the number implies.
  3. Maximally safe but removes the product's ability to claim any auto-confirmed duplicate detection, which may undercut the "confirmed duplicate" state's value entirely.
  4. Cross-module matching increases both true and false positive rates and has real performance/architecture implications (raised again in Catalyst migration risk #4); within-module-only understates true duplicate volume for orgs with parallel Lead/Contact records.
- **Recommended option:** Cannot be reasonably recommended. This is squarely a precision/recall trade-off with data-integrity consequences that only the product owner can accept on the business's behalf; the validation report treats this as a blocking pre-implementation question (open questions #7–#10) precisely because it is not an engineering call.
- **Evidence required:** Would benefit from a labeled sample of real (or realistic seeded) records run through the current shortcuts to quantify the false-confirmation rate before deciding.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner + whoever owns data-integrity/legal risk for customer CRM data (this touches irreversible-if-merged customer data).
- **Acceptance criteria:** A single documented confirmation rule with no undocumented shortcuts remaining; an explicit, approved policy for cross-module scope and block-size overflow; a stated maximum acceptable false-confirmation rate, ideally validated against a test dataset.
- **Impacted implementation areas:** Duplicate matching engine (`fg`, `pg`, `Eu`, `Mf`), `confirmed_duplicate` state assignment, `merge-duplicates` fix action (D16), Fix tab safety guarantees.

---

### D7 — Data retention and export minimization

- **Decision ID:** D7
- **Topic:** What data may be retained in memory and included in exports during and after a scan.
- **Current widget behavior:** Each fact retains `label`, creator/modifier/owner IDs *and names*, timestamps, and stage, plus issue messages — some of which embed source field values (e.g., an invalid picklist value or a flagged dummy name). The Records CSV export includes record label, creator, modifier, owner, stage, dates, and those messages. A duplicate-pair array (`Eu`) retains pair IDs, confidence, reasons, and blocking keys (which can contain normalized statutory IDs, emails, or phones) in memory until the next duplicate run.
- **Current specification behavior:** States that raw field values are discarded after evaluation and that retained facts contain "identifiers and states only." The widget's own UI copy makes this same claim at the point of export.
- **Exact conflict:** The actual retained/exported data is materially broader than "identifiers and states only," and includes personally identifying material (names) and, in duplicate blocking keys, normalized emails/phones/statutory IDs.
- **Why it matters:** This is a stated privacy/minimization commitment shown directly to the customer in the UI, and it is false as implemented. For a tool whose entire pitch is "read-only, minimal-footprint CRM scanning," an incorrect minimization claim is a credibility and potentially compliance risk, especially before this is rebuilt on a durable Catalyst backend with real retention/TTL requirements.
- **Available options:**
  1. Tighten the code to match the stated minimal-tuple claim: strip names/labels/stage/embedded values from retained facts and exports, replacing with opaque identifiers only.
  2. Loosen the stated claim to match current behavior, explicitly documenting what is retained and for how long, and treat this as an accepted product trade-off (richer context vs. minimization).
  3. Tiered approach: keep richer data only in-session (never exported, never persisted beyond the active scan), and enforce true minimal-tuple rules for anything that leaves the browser (CSV export, future Catalyst persistence).
- **Consequences of each option:**
  1. Strongest privacy posture and makes the existing UI copy true; but may reduce the product's usefulness (managers want to see *which* record and *whose* name, not just an opaque ID) and requires engineering changes across fact construction, exports, and duplicate-pair storage.
  2. No engineering change required, but this is a customer-facing promise being walked back — needs explicit sign-off from whoever owns that commitment, and probably a UI copy change too.
  3. Balances usefulness against exposure, but adds complexity (two different data-shape rules depending on export path) and doesn't fully resolve what should happen once Catalyst adds durable server-side storage.
- **Recommended option:** Cannot be reasonably recommended — this is a minimization-vs-usefulness trade-off with compliance implications that depends on customer commitments this document has no visibility into. The validation report lists the exact retention boundary (open questions #20–#23) as unresolved for the same reason.
- **Evidence required:** Clarify any existing customer-facing or contractual data-handling commitments (if such commitments exist outside this codebase) before finalizing.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner + privacy/legal/compliance owner (this is the one item on this register with plausible legal exposure).
- **Acceptance criteria:** A documented, enforced data-minimization boundary that the UI's own claims match exactly; TTL and deletion behavior defined for anything Catalyst persists; the duplicate-pair array's lifetime explicitly bounded.
- **Impacted implementation areas:** Fact construction (`Eg`), Records export (`qg`), Duplicate-pair storage (`Eu`), Modules export, Catalyst data-model design (also referenced in migration risk #6).

---

### D8 — Threshold configurability in the UI

- **Decision ID:** D8
- **Topic:** Whether operators can edit rule thresholds (stale-days, min records, burst window, duplicate floors, stage-aware toggle, exclude-bulk-users) from the setup screen.
- **Current widget behavior:** Default threshold values and a `setRules` reducer action exist, but no rendered control ever calls `setRules`. Several CSS selectors for a thresholds panel (`.control-grid.thresholds`, `.rule-groups`, `.toggle-row`) exist in the stylesheet but are unused by any component.
- **Current specification behavior:** §4.1 and §6.3 describe an "advanced/expandable panel" where all of these thresholds are operator-editable per scan.
- **Exact conflict:** The spec describes a shipped, editable feature; the code has the data plumbing and the leftover CSS for it, but no UI control that exposes it.
- **Why it matters:** This changes whether the tool is "one-size-fits-all defaults" or "tunable per customer/org." It affects onboarding flow design and whether v1 needs a settings/config screen at all.
- **Available options:**
  1. Build the missing UI control before v1 launch (CSS scaffolding already exists, suggesting it was planned and cut).
  2. Defer to a later phase; ship v1 with fixed defaults and document thresholds as non-editable for now.
  3. Expose thresholds read-only in v1 (so operators can see, but not change, the applied values) as a middle ground.
- **Consequences of each option:**
  1. Matches the spec and likely the original intent (given the dormant CSS), but adds scope to the v1 build.
  2. Fastest to ship, but the spec needs to be corrected to describe defaults as fixed, and any customer expecting tunability will be surprised.
  3. Low engineering cost, improves transparency, but doesn't resolve the underlying question of whether tunability is actually needed for v1.
- **Recommended option:** Cannot be reasonably recommended — this is a scope/roadmap call (open question #25: which deck features are required for first release vs. later phases), not a technical one.
- **Evidence required:** None.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner (release scope).
- **Acceptance criteria:** Spec and UI agree on whether thresholds are editable in v1; if deferred, spec explicitly marks this as a later-phase feature rather than a current one.
- **Impacted implementation areas:** Setup screen, `setRules` reducer path, threshold CSS, spec §4.1/§4.3.2/§4.3.3/§6.3.

---

### D9 — Setup cost/runtime estimate accuracy

- **Decision ID:** D9
- **Topic:** How accurately the setup screen must estimate API cost/credit consumption and runtime before a scan is committed.
- **Current widget behavior:** The estimate uses the selected depth cap (up to 100,000 for "full"), assumes 200 records per request, adds fixed metadata-call overhead, and multiplies by a flat 1.2 seconds per unit to estimate minutes. It does not query actual records-in-range, does not inspect the org's real API credit budget, and does not show a hard ceiling.
- **Current specification behavior:** Describes (and the deck, slide 14, asks for) an estimate based on records-in-range and real credit consumption before the operator commits to a run.
- **Exact conflict:** The spec/deck describe a data-driven pre-run estimate; the code provides a rough, cap-based approximation that can be significantly wrong for orgs whose actual record count is far below the cap.
- **Why it matters:** Customers are trusting this number to decide whether to commit API credits to a run. An estimate that is structurally disconnected from the real record count risks under- or over-promising cost/time, which matters more once this hits a metered Catalyst billing model.
- **Available options:**
  1. Build a real pre-run estimate (query record counts in range before committing) for v1.
  2. Keep the cap-based estimate for v1, but relabel it clearly as an upper-bound approximation rather than a precise forecast.
  3. Defer accurate estimation to a later phase, same as D8.
- **Consequences of each option:**
  1. Matches the spec/deck promise, but requires an extra metadata round-trip before scan start and needs the real per-org credit-budget API investigated first (technical evidence, see below).
  2. Minimal engineering change, but requires correcting the spec's claim and possibly the deck's promise.
  3. Fastest, but leaves the same discrepancy in place for a later release to fix.
- **Recommended option:** Cannot be reasonably recommended — depends on release scope (same category as D8/D10) and on the technical evidence below.
- **Evidence required:** Confirmation of what real-time record-count and credit-budget data the Zoho/Catalyst APIs can actually expose before a scan starts, and at what added latency cost — this determines whether option 1 is even feasible within an acceptable setup-time budget.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner (scope) + engineering lead (feasibility, once evidence is gathered).
- **Acceptance criteria:** Setup-screen estimate methodology is documented and either (a) verified accurate against real record counts, or (b) explicitly and visibly labeled as an approximation.
- **Impacted implementation areas:** Setup screen estimator (`ty`), spec §4.1, deck slide 14 commitments.

---

### D10 — Screen behavior gaps (Modules, Users, Trend, Records, Fix)

- **Decision ID:** D10
- **Topic:** Multiple per-screen features described in the spec/deck that have no implementation: Modules stage-aware toggle; Users team filter, minimum-volume input, bulk toggle, trend sparkline, prior/current column, manager rollup, per-user suggested action; Trend's four-checkpoint cohort aging and overlays; Records "send to fix list"; Fix run controls, preview, and SOW generation.
- **Current widget behavior:** Each of these screens implements a narrower feature set than described (see validation §4.3.2–4.3.6 for the full breakdown). The "worst cell" callout on Modules also silently ignores domain cells with fewer than 20 eligible observations — an undocumented rule.
- **Current specification behavior:** Describes the full feature set above as if present.
- **Exact conflict:** Spec describes shipped functionality; multiple discrete features across five screens do not exist in the widget.
- **Why it matters:** This is the largest single block of scope ambiguity in the register. Deciding what's v1 vs. later determines the shape of the Catalyst build plan more than any single formula decision.
- **Available options:** Same three-way pattern as D8/D9: build to spec, cut from spec and document as future phases, or a mixed per-feature triage.
- **Consequences of each option:** Building everything maximizes fidelity to the original pitch but is the largest scope item on this register; cutting everything is fastest but significantly narrows the "report" experience that has apparently been demoed; a per-feature triage is realistic but requires someone to actually rank each of the ~10 missing features.
- **Recommended option:** Cannot be reasonably recommended in aggregate — recommend triaging feature-by-feature against customer commitments (deck slides tied to specific sales conversations, if any exist) rather than deciding this as one bundled item.
- **Evidence required:** None beyond internal prioritization; the individual worst-cell 20-observation threshold rule should be product-reviewed alongside this to decide if it's the right minimum-sample-size floor or arbitrary.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner (release scope), same track as D8/D9/D25 in the validation report's open questions.
- **Acceptance criteria:** Each missing feature explicitly assigned to v1, a later phase, or cut, with the spec updated to match.
- **Impacted implementation areas:** Modules (`Iu`, `Yg`), Users (`ry`), Trend (`ny`), Records (`qg`), Fix (`Gg`) — see spec §4.3.2–4.3.6.

---

### D12 — Configuration hygiene domain definition and scope

- **Decision ID:** D12
- **Topic:** What the "Configuration Hygiene" domain actually measures, and whether it should apply globally or per-module.
- **Current widget behavior:** `Mg` scores configuration hygiene as the percentage of scannable fields with at least one non-empty value in the extracted sample. It does not assess unused modules, dead workflows, layout sprawl, or duplicate picklists as implied by the domain name. The resulting single global value is inserted identically into every module's score slice, so a module's "overall" score is partly driven by an org-wide number that has nothing to do with that specific module.
- **Current specification behavior:** §6.4 lists Configuration Hygiene as one of nine weighted domains (20 points) without specifying it is a crude field-fill-rate heuristic, and the deck describes it at the org level, not as a per-module input.
- **Exact conflict:** The implementation is narrower than the domain name implies, and its global-value-injected-into-every-slice behavior contradicts the deck's org-level framing.
- **Why it matters:** If a customer drills into a specific module's low score expecting to find module-specific problems, part of that score may actually be an org-wide config signal unrelated to the module — this is misleading in exactly the kind of drill-down workflow the Modules tab exists to support.
- **Available options:**
  1. Keep configuration hygiene as an org-level-only metric (exclude it from module-level score composition), matching the deck's framing.
  2. Build a genuinely module-aware configuration hygiene rule set (assess module-specific config issues), matching the domain name and 20-point weight.
  3. Keep current behavior but rename the domain (e.g., "Field Completeness") to accurately reflect what's measured, and explicitly document the global-value-per-slice behavior as intentional.
- **Consequences of each option:**
  1. Simplest fix, resolves the misleading drill-down issue, but reduces module-level scoring to 8 domains instead of 9 and requires recalculating weight distribution.
  2. Most faithful to the original intent (20-point domain with real signal) but is a nontrivial new rule-authoring effort, especially since the "roughly 70 rule" catalogue is still incomplete (see validation §Missing items).
  3. No behavior change, cheapest, but doesn't resolve the substantive underlying question of whether this domain should influence module drill-downs at all.
- **Recommended option:** Cannot be reasonably recommended — this is entangled with the still-open question of what the full ~70-rule catalogue should contain (open question #26) and depends on whether config hygiene is meant to be a module diagnostic or an org-health signal.
- **Evidence required:** None beyond the rule-catalogue design work referenced in open question #26.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner (domain/rule design), likely resolved alongside the broader rule-catalogue review.
- **Acceptance criteria:** Configuration Hygiene's definition, scope (org-level vs. module-aware), and scoring composition rule are documented and consistent between spec, deck, and code.
- **Impacted implementation areas:** `Mg`, `Sg.compute` domain composition, Modules tab, spec §6.4.

---

### D15-KNOB — Dead `maxExamplesPerRule` configuration

- **Decision ID:** D15-KNOB
- **Topic:** Whether the `maxExamplesPerRule` threshold should be implemented or removed.
- **Current widget behavior:** `maxExamplesPerRule` exists only in the default threshold object; nothing ever reads or enforces it. The actual behavior is a hardcoded cap of 3 stored issues per record-rule invocation (`.slice(0,3)`), while all set-rule issues are retained without any cap.
- **Current specification behavior:** §6.3 documents `maxExamplesPerRule` as a real, presumably configurable threshold.
- **Exact conflict:** A documented, presumably-configurable setting does nothing; the real behavior is a hardcoded, undocumented, and inconsistent (record-rule vs. set-rule) cap.
- **Why it matters:** Minor on its own, but it's exactly the kind of "dead control implies an incomplete refactor" signal the validation report flags as a broader trust concern (technical risk #8) — worth deciding deliberately rather than leaving as accidental debt.
- **Available options:**
  1. Wire `maxExamplesPerRule` up to actually govern the cap (and decide if set-rule issues should also be capped).
  2. Remove `maxExamplesPerRule` from the default object and document the real, fixed cap of 3 as intentional.
- **Consequences of each option:** Option 1 is a small amount of engineering work but delivers the flexibility the spec already claims exists; option 2 is a documentation-only fix but concedes the setting was aspirational and never finished.
- **Recommended option:** Option 2 (document the fixed cap as-is) is the lower-risk default absent evidence anyone needs per-rule-configurable example counts — but this is still a product call, not a foregone conclusion, since it also leaves the set-rule/record-rule inconsistency unresolved either way.
- **Evidence required:** None.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner / engineering lead (low-stakes, can be delegated).
- **Acceptance criteria:** Either the knob is functional and documented, or it is removed from the spec and the fixed cap (record- and set-rule, made consistent) is documented instead.
- **Impacted implementation areas:** Rule evaluator (~195,500–196,500), default threshold object, spec §6.3.

---

### TZ-1 — Timezone and audit "closed" timestamp semantics

- **Decision ID:** TZ-1 *(sourced from validation report Ambiguity #6 and Open Question #12 — not itself a numbered "D" discrepancy, but included here because it directly affects D5/D6-adjacent plausibility rules and any customer-facing timestamp claims)*
- **Topic:** Which timezone governs burst/off-hours plausibility detection, and what timestamp should represent a record being "closed" for freshness/audit purposes.
- **Current widget behavior:** Date parsing, off-hours detection, and any fiscal-year-adjacent calculations run in the browser's local timezone — i.e., whatever timezone the operator's machine happens to be set to, not the CRM org's configured timezone or the customer's business timezone. "Closed" state calculations rely on `Modified_Time` rather than a distinct audit/event timestamp.
- **Current specification behavior:** Does not define an intended org/client timezone for these calculations, and does not specify what field should represent "closed" versus generic last-modification.
- **Exact conflict:** No conflict in the sense of code contradicting a documented spec — the spec is silent, and the code defaults to an operator-local timezone that has no necessary relationship to the org being scanned.
- **Why it matters:** An off-hours or burst-timing plausibility finding computed in the wrong timezone can flag a perfectly normal business-hours record entry as suspicious (or vice versa), and this directly feeds `suspicious` state assignment on named users — the same class of false-positive risk flagged for D6. Using `Modified_Time` as a proxy for "closed" can also misrepresent audit history if records are modified for unrelated reasons after being closed.
- **Available options:**
  1. Use the CRM org's configured timezone (fetch from Zoho org metadata) for all time-based plausibility rules.
  2. Use a per-scan operator-selected timezone (explicit setup control).
  3. Keep browser-local timezone but disclose it clearly in any suspicious-finding explanation shown to the operator.
  4. For "closed" semantics: introduce a distinct audit/close timestamp requirement (if the CRM data model has one) rather than relying on `Modified_Time`.
- **Consequences of each option:** Org-timezone (1) is most correct but requires confirming the metadata is reliably available across all supported CRM configurations (technical evidence). Operator-selection (2) is simple to build but pushes a burden onto the operator to know the right value. Disclosure-only (3) doesn't fix the false-positive risk, only its transparency. For "closed" semantics, using a real audit timestamp (4) is more correct but depends on what's actually available in the target CRM's data model.
- **Recommended option:** Cannot be reasonably recommended — depends on what timezone metadata is reliably available from the CRM API (technical evidence) and whether the false-positive risk from the current default is judged acceptable for suspicious-finding accuracy that names individual users.
- **Evidence required:** Confirm whether org timezone is reliably available via the CRM metadata API in all target Zoho configurations, and whether a true "closed" audit timestamp exists in the data model as distinct from `Modified_Time`.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner (policy) + engineering lead (feasibility of org-timezone metadata).
- **Acceptance criteria:** A documented, single source of truth for the timezone used in all time-based plausibility rules, and a documented definition of "closed" that is not silently `Modified_Time` unless that's an explicit, accepted approximation.
- **Impacted implementation areas:** Plausibility rule engine (burst/off-hours detection), `suspicious` state assignment, any freshness/audit rules relying on close timestamps.

---

## 3. Decisions Requiring Technical Evidence

### D13 — Date-bounded extraction architecture

- **Decision ID:** D13
- **Topic:** Whether the current client-side date-range extraction approach is acceptable for production, or must be replaced with a server-side, date-bounded collector.
- **Current widget behavior:** The live path calls `getAllRecords`, sorts by the selected clock field, and filters the union of current-plus-prior ranges in JavaScript on the client. It stops paging after encountering more than 25 records older than the lower bound. It is not a Bulk Read/COQL date-bounded query, has no watermark/resume capability, and does not forward the evaluator's supported-fields list into the page request.
- **Current specification behavior:** Implies a proper date-bounded collection mechanism without specifying this client-side heuristic.
- **Exact conflict:** The spec doesn't describe (and arguably assumes away) the actual fragility of the current approach: missing/unsorted/null date values, or unexpected SDK paging behavior, can silently produce incomplete scan results with no error surfaced.
- **Why it matters:** This is a correctness and completeness risk that's invisible to the operator — a scan can report a clean score while having silently missed records. It's also flagged as a Catalyst migration architecture risk (durable jobs need partitions, spill/storage strategy, and deterministic windows; loading a full org client-side is explicitly called unsafe).
- **Available options:**
  1. Migrate to COQL or Bulk Read as the primary date-bounded collector for Catalyst, with watermark/resume support.
  2. Keep the client-side heuristic for now (acceptable if this remains a bounded-scope prototype) but add explicit truncation warnings to the operator when the 25-record stop threshold is hit.
  3. Hybrid: keep client-side collection for small/medium orgs, require COQL/Bulk Read above a record-count threshold.
- **Consequences of each option:** Option 1 is the only one that fully resolves the completeness risk but is a substantial architecture investment tied directly to the Catalyst migration (already flagged there); option 2 is fast but leaves a real, disclosed data-completeness gap; option 3 balances effort against risk but adds branching complexity.
- **Recommended option:** Cannot be reasonably recommended independent of the Catalyst migration's overall data-architecture decision (this overlaps migration risk #4 and #7) — but at minimum, option 2's disclosure should be considered a floor, not a full solution, regardless of which long-term path is chosen.
- **Evidence required:** Confirm COQL/Bulk Read API rate limits, latency, and date-filtering capabilities across all target Zoho products (not just CRM) before committing to option 1 or 3; quantify how often null/unsorted date fields actually occur in representative customer data to size the real risk of the current heuristic.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED** (pending technical evidence)
- **Decision owner:** Engineering lead (architecture), with product sign-off on acceptable risk if any interim/hybrid approach is chosen.
- **Acceptance criteria:** A documented extraction architecture with a defined behavior for null/malformed timestamps and a resolution (not just disclosure) for the completeness risk, consistent with the chosen Catalyst migration path.
- **Impacted implementation areas:** Live extraction (`Oh`, `Eg`), Catalyst extraction architecture, Setup screen (any resulting warnings).

---

### D14-EVIDENCE — Actual Zoho scope/visibility behavior *(technical evidence component of D14)*

- **Decision ID:** D14-EVIDENCE
- **Topic:** What a signed-in operator can actually see via the current API calls, and how that compares to what an org-wide Catalyst integration identity would see.
- **Current widget behavior:** The widget calls read-oriented CRM APIs as the signed-in user and does not inspect OAuth scopes, does not detect partial record visibility, and does not distinguish "I saw everything" from "I saw only what my profile permits."
- **Current specification behavior:** Setup copy states scans run "as the signed-in user and respect that profile's access," implying this is understood and handled, without defining what happens when visibility is partial.
- **Exact conflict:** The spec's language implies a considered visibility model; the code has no mechanism to detect or disclose when a scan's org score is actually based on a partial view.
- **Why it matters:** A limited-visibility signed-in user's scan can silently present as a full org score. This is a data-integrity and trust issue distinct from D14-POLICY's authorization-model question — even once the ideal policy is chosen, someone needs to verify what the Zoho platform actually reports about a user's effective visibility so that policy can be enforced or at least disclosed.
- **Evidence required:**
  1. Whether Zoho CRM APIs expose any queryable signal for "this user's visible record count is less than the module's total record count" (e.g., comparing a profile-scoped count against an admin-scoped count).
  2. What OAuth scopes are actually requested/granted in the current SDK integration, and whether they can be introspected at runtime.
  3. How record-level sharing rules, territory management, and role hierarchies affect `getAllRecords`/COQL results in practice, ideally verified against a real or realistic sandboxed org with non-trivial sharing rules.
- **Decision:** **Cannot be made until evidence above is gathered.** This blocks D14-POLICY's acceptance criteria (a policy can't be finalized as "least privilege" without knowing what's technically detectable).
- **Decision owner:** Engineering lead (Zoho platform investigation), reporting findings to the D14-POLICY decision owner.
- **Acceptance criteria for evidence-gathering:** A documented answer to each of the three evidence questions above, sufficient to inform whether partial-visibility detection is technically feasible at all.
- **Impacted implementation areas:** Live extraction client (`Rh`), Setup screen scope/consent UI (currently absent per D10/D14-POLICY).

---

## 4. Decisions Requiring Product Approval — Split Item

### D14-POLICY — Authorization/visibility model *(policy component of D14)*

- **Decision ID:** D14-POLICY
- **Topic:** Whether scans should run as the signed-in operator's identity (current behavior) or as an org-wide Catalyst integration identity, and what consent/scope disclosure is required either way.
- **Current widget behavior:** Runs strictly as the signed-in user; no scope list is shown, no consent is recorded, and no least-privilege enforcement exists beyond whatever the signed-in user's own profile permissions naturally restrict.
- **Current specification behavior:** States scans respect the signed-in user's access but does not specify whether this is the intended long-term model or a stopgap, nor does it define a consent/disclosure requirement.
- **Exact conflict:** The spec asserts a visibility behavior as if it were a considered design choice; there's no evidence anywhere in the spec or code that this was actually decided versus simply being the default of "call the API as whoever's logged in."
- **Why it matters:** This is one of the most consequential architecture decisions on the register. A Catalyst integration user identity would see more records and metadata than the current signed-in widget user, meaning scores computed under the two models are not comparable — and the choice affects the entire authorization/consent UI, not just a backend detail.
- **Available options:**
  1. Keep signed-in-user identity as the permanent model: scores reflect "what this operator can see," with results explicitly labeled as operator-scoped rather than org-wide.
  2. Move to an org-wide Catalyst integration identity: requires an explicit admin-level connection/consent flow, distinct read scopes, and a documented statement of what the integration can see that individual operators might not.
  3. Support both, operator-selectable, with clear UI differentiation of which mode is active and what it implies for score comparability.
- **Consequences of each option:** Option 1 is simplest and lowest-privilege but means org-level reporting/benchmarking claims in the deck are not actually deliverable without an admin running the scan themselves. Option 2 unlocks true org-wide reporting but is a much larger authorization/security build (separate scopes, explicit approvals — see Catalyst migration risk #8) and raises the stakes on D14-EVIDENCE and D7. Option 3 is the most flexible but doubles the design/testing surface and risks operator confusion about what their score actually represents.
- **Recommended option:** Cannot be reasonably recommended — this is the kind of architecture-defining decision the validation report explicitly lists as blocking before Catalyst implementation begins (open questions #14–#15), and it's entangled with D14-EVIDENCE (what's even technically possible) and D7 (what an org-wide identity would be allowed to retain).
- **Evidence required:** See D14-EVIDENCE above; this decision should not be finalized before that evidence is in hand.
- **Decision:** **TBD — PRODUCT DECISION REQUIRED**
- **Decision owner:** Product owner + security/architecture owner (this is a joint call given the authorization-boundary implications).
- **Acceptance criteria:** A documented authorization model, an explicit scope list per domain/product, a defined consent/approval flow if org-wide identity is chosen, and a clear disclosure of visibility scope shown to the operator regardless of which model is chosen.
- **Impacted implementation areas:** Live extraction identity model, Setup screen (consent/scope disclosure — currently absent), Catalyst authorization boundary (migration risk #2, #8), any future org-wide reporting or benchmarking feature.

---

## 5. Decisions Already Determined From Existing Intent

These items have a documented, pre-existing statement of intent (in the spec, deck, or a dormant-but-present code artifact) that the current code contradicts. They are classified as **implementation fixes**, not open product decisions — the correct behavior is already known; the code needs to be brought into line with it.

### D3 — State precedence ordering

- **Classification:** Documentation correction (not a policy question).
- **Detail:** The spec's own §6.1 proposes exactly the precedence order the code already implements explicitly (`Mu`/`gg`: `proper < incomplete < inaccurate < suspicious < suspected_duplicate < confirmed_duplicate`). The spec incorrectly states in its open questions that "no priority constant was found." This is simply a factual error in the spec's own evidence claim — the spec should be corrected to cite the confirmed implementation.
- **Remaining open item:** *Whether this precedence is the correct policy* (as opposed to whether it's implemented) is a separate, still-unresolved question — noted in validation open question #4 — but it is not blocking in the same way as D2/D4/D5, since the current implementation already matches the spec's own proposal. No entry created here beyond this note; escalate only if a future review disputes the ordering itself.

### D16 — Duplicate fix routing and projected-gain math

- **Classification:** Implementation fix (intent is already documented; code contradicts it).
- **Detail:** The spec explicitly states that suspected duplicates route to human review, and only confirmed duplicates ever reach an automatic-adjacent action (spec line ~233: "duplicates route to human review actions, never an automatic write"). The code, however, always assigns `duplication.fuzzy` failures the `fixKey: "merge-duplicates"`, aggregating suspected and confirmed duplicates into the same action — while a `review-duplicates` action definition already exists in the bundle, unused and unbound. The presence of that dormant definition is strong evidence this is a wiring bug against already-agreed intent, not an open design question.
- **Required fix:** Bind `suspected_duplicate` failures to the existing `review-duplicates` action; reserve `merge-duplicates` for `confirmed_duplicate` only (subject to D5's confirmation-policy resolution, since D5 determines what actually qualifies as "confirmed").
- **Secondary fix (same item):** Projected-gain totals for selected Fix actions are currently summed independently per action, which is not guaranteed to equal the actual combined effect when actions share overlapping rule IDs. Fix by rescoring the combined selection rather than summing independent deltas.
- **Decision owner for verification:** Engineering lead; no product sign-off needed beyond confirming D5's resolution before final wiring.

### D6 — Repeated-phone plausibility grouping blank values

- **Classification:** Implementation fix (asymmetric bug, not a design choice).
- **Detail:** The repeated-phone grouping callback groups records by `module::${sf(signature.phone)}` whenever a signature object exists — including when the phone value is empty — so five or more records with blank phones in a module can be flagged as suspicious for sharing a "value" they don't actually share. The equivalent email-grouping path already correctly excludes empty values. Nothing in the spec or deck ever proposed treating blank phones as a shared value; this is an asymmetric implementation bug.
- **Required fix:** Apply the same non-empty check used in the email path to the phone-grouping path.
- **Decision owner for verification:** Engineering lead; recommend product/QA verification of the fix against a sample with blank-phone records before closing.

### D17 — API statistics reset/display

- **Classification:** Implementation fix.
- **Detail:** The request queue's retry/failed counters are a module-level singleton that persists across scans; `runStarted` never resets `apiStats`, so a "new" scan's dispatch count is accurate but its retry/failed counts are cumulative across all prior scans in the session. The failed-call count is already tracked in state but never rendered on the running screen.
- **Required fix:** Reset `apiStats` counters at `runStarted`; surface the already-tracked failed-call count in the running screen UI alongside dispatched/retried.
- **Decision owner for verification:** Engineering lead; no product decision required — this is unambiguously a bug (accurate per-run reporting was clearly the intent, given dispatched/retried are already correctly scoped).

---

## 6. Resolved Decisions

These require no further product or technical input — they are factual/documentation corrections confirmed directly against executable source.

### D1 — Live extraction path exists

- **Resolution:** The spec's claim that the extractor is entirely synthetic with no live extraction path is factually incorrect. The bundle contains a complete live CRM client (`Rh`) that activates when framed inside `window.ZOHO.embeddedApp`/`window.ZOHO.CRM`, discovering modules/fields/users, counting records, paging through records, and evaluating them, with a mock client as fallback.
- **Action:** Correct the spec's §1, §7, and §10 language to describe the live extraction path as implemented, and remove any characterization of the widget as "client-only synthetic demo."
- **Owner:** Spec maintainer. No product approval needed — this is a factual correction.

### D11 — Reconstructed data model mismatch

- **Resolution:** The spec's documented data model (`failedRuleIds[]` array, a persisted/serialized cube entity, a `{clusterId, matchType, matchedFields[]}` duplicate-cluster object) does not match the executable fact model, which uses bitmask `eligible`/`failed` fields plus up to three issue objects per record-rule, an in-memory memoized cube class (not a serialized entity), and duplicate results stored as best-partner pairs (not clusters).
- **Action:** Correct spec §5 to describe the actual current data shapes. Note for the register: whether Catalyst *should* introduce the richer documented model (true clusters, persisted cube) going forward is a separate, forward-looking architecture question — already captured under Catalyst migration risk #5 — and is not blocking for documentation accuracy on the current widget.
- **Owner:** Spec maintainer. No product approval needed for the correction itself.

### D15-COUNT — Rule count misstated

- **Resolution:** The spec states 24 rules; the code implements 22 (16 record rules + 6 set rules).
- **Action:** Correct the spec's rule count and any accompanying rule inventory listing to match the confirmed 22.
- **Owner:** Spec maintainer. No product approval needed — this is a factual count correction, separate from the still-open question of the ~70-rule target catalogue for production (open question #26).

---

## 6a. Outstanding Decisions (Consolidated)

The following remain unresolved as of this document's creation. Each links back to its full entry above.

| ID | Owner | Blocking for Implementation? |
|---|---|---|
| D2 — Scoring formula | Product owner (scoring) | Yes — architecture-affecting |
| D4 — User score formula | Product owner (scoring) | Yes — architecture-affecting |
| D5 — Duplicate scope & confirmation | Product owner + data-integrity owner | Yes — architecture-affecting |
| D7 — Data retention & export minimization | Product owner + privacy/legal | Yes — architecture-affecting |
| D8 — Threshold configurability | Product owner (scope) | No — roadmap/scope only |
| D9 — Setup cost estimate accuracy | Product owner + engineering lead | No — roadmap/scope, pending evidence |
| D10 — Screen behavior gaps | Product owner (scope) | No — roadmap/scope only |
| D12 — Configuration hygiene definition/scope | Product owner (rule design) | No — roadmap/scope, but affects domain-weight math |
| D13 — Date-bounded extraction architecture | Engineering lead + product owner | Yes — architecture-affecting |
| D14-POLICY — Authorization/visibility model | Product owner + security/architecture owner | Yes — architecture-affecting |
| D14-EVIDENCE — Zoho visibility technical evidence | Engineering lead | Yes — blocks D14-POLICY |
| D15-KNOB — `maxExamplesPerRule` | Product owner / engineering lead | No — low-stakes cleanup |
| TZ-1 — Timezone & "closed" semantics | Product owner + engineering lead | Yes — architecture-affecting (feeds `suspicious` state on named users) |

---

## 7. Go/No-Go for Implementation

**Status: NO-GO.**

Implementation of the Catalyst migration must not begin until every item marked **architecture-affecting** in section 6a is resolved:

- D2 (scoring formula)
- D4 (user score formula)
- D5 (duplicate scope & confirmation policy)
- D7 (data retention & export minimization)
- D13 (date-bounded extraction architecture)
- D14-POLICY and D14-EVIDENCE (authorization/visibility model)
- TZ-1 (timezone & audit "closed" semantics)

These items directly determine the data model, authorization boundary, scoring engine, and extraction architecture that everything else in the Catalyst build depends on. Starting engineering work against any one interpretation of these before approval risks building against the wrong contract and having to redo core architecture mid-migration — the exact failure mode the validation report's "Catalyst migration risks" section warns against (see risk #1: "Do not port the bundle as the normative algorithm").

The remaining items (D8, D9, D10, D12, D15-KNOB) are release-scope decisions. They should be resolved before a v1 release commitment is made, but do not need to block the *start* of architecture work on the items above.

**Path to GO:** Once all architecture-affecting decisions are formally approved and this document's "Decision" fields are updated from `TBD — PRODUCT DECISION REQUIRED` to a recorded decision with owner sign-off, this document should be re-issued as v2 with an updated section 1 status summary, and the Go/No-Go status reassessed.
