# Independent validation of the reverse-engineered specification

**Date:** 17 August 2026  
**Scope:** Validation only; no application code was changed.  
**Sources reviewed:** `docs/reverse-engineered-spec.md`; every entry in `reference/original-widget.zip` (`widget.html`, the complete minified JavaScript and CSS bundles, `translations/en.json`, and `logo.png`); and all 31 slides plus notes in `reference/product.pptx`.

## Evidence convention and limitations

The only executable JavaScript supplied is a production-minified, single-line bundle with no source map. JavaScript citations therefore use the archive entry name, minified character offset, and nearby symbol or literal. Offsets are approximate anchors, not stable source-level line numbers. HTML and JSON citations use line numbers. Deck citations use slide numbers.

The PPTX is a build-approval/product-intent document. It can verify intended behavior, but it cannot verify implementation. CSS selectors can verify styling support only; an unused selector is not evidence that a screen or control exists.

Status terms used below:

- **Confirmed:** directly implemented or declared in executable source.
- **Partially confirmed:** a narrower or materially different implementation exists.
- **Contradicted:** executable behavior conflicts with the specification.
- **Not verifiable:** asserted by the deck/spec but not demonstrable from this client artifact.
- **Missing functionality:** required or described behavior has no executable implementation in the widget.

## Executive summary

The specification is a useful product narrative, but it is not a reliable implementation contract. Large portions reproduce deck intent or code copy accurately, while several of the most important technical conclusions are wrong.

The current widget is not merely a client-only synthetic demo. It implements a live, read-only Zoho CRM path using metadata, records, users, record-count and COQL APIs, with paging, throttling and retry logic. It also contains a mock client. The claim that no live extraction path exists is directly contradicted by the bundle.

The scoring description is also materially wrong. Domain scores are severity-weighted averages of per-rule pass rates. The overall score then renormalizes only applicable, measurable domain weights. User “score” is different again: it is simply the percentage of that user's records whose terminal state is `proper`. These are not interchangeable formulas.

The six states and their precedence are implemented explicitly. The production question is therefore not “what does the widget do?” but “is the widget's explicit ordering the intended policy?” The implemented order is `confirmed_duplicate > suspected_duplicate > suspicious > inaccurate > incomplete > proper`.

Duplicate detection is only within a module, includes an undocumented name blocking key, skips blocks larger than 40, and can mark a pair confirmed below 0.90 when email plus phone or a highly similar name agree. Repeated-phone plausibility detection appears to group blank phone signatures together, creating a serious false-positive risk.

The retention claim is overstated. Raw source records are not persisted, and duplicate signatures are cleared, but active scan facts retain record labels, user names, owner names, stage and timestamps. CSV export includes several of these values. A module-global duplicate-pair array also remains in memory after evaluation. This does not meet the report's own “record identifiers and states only” formulation.

Many deck features are absent: actual remediation writes, preview/snapshot/rollback, schedules, alert floors, PDF/SOW generation, true cohort decay, overlays, team/manager rollups, backend-only PII/access and automation scoring, and broader Zoho product support. Implementation should not begin until scoring semantics, duplicate confirmation policy, state precedence, data-minimization boundaries, authorization model and extraction architecture are explicitly approved.

## Section-by-section validation

| Specification section | Status | Validation |
|---|---|---|
| 1. Purpose | **Partially confirmed** | The CRM scanner, six states, nine domain definitions, three analytical lenses and remediation guidance exist. “Connects read-only” is behaviorally consistent with called endpoints, but no scope verification exists. PDF output and production Catalyst operation are missing. |
| 2. Actors | **Not verifiable / partially confirmed** | The UI is operator-oriented and names individual CRM users. Stakeholder roles and consulting-sales usage come from the deck, not executable authorization or role logic. |
| 3. Lifecycle | **Partially confirmed** | Reducer phases `boot`, `setup`, `running`, `report`, `error` and reset-to-setup exist. “Reset” is an action, not a phase. Errors are not reachable from every phase, and per-module extraction errors are absorbed into a completed partial report. |
| 4.1 Setup | **Partially confirmed with contradictions** | Org label, depth, clock, ranges, custom dates and module selection exist. Module counts are not loaded or shown at setup. No rule-threshold panel exists. Cost/runtime are cap-based estimates, not records-in-range or credit-budget calculations. No consent/scope list or scheduling action exists. |
| 4.2 Running | **Mostly confirmed** | Per-module progress, completed modules, API dispatch/retry statistics and cancellation exist. Failed-call count is tracked in state but not displayed. Counters have cross-run accuracy risks. |
| 4.3 Report shell | **Confirmed with narrower controls** | Six tabs and shared module/user/attribution filters exist. The filter bar does not offer all controls claimed by individual tab descriptions. |
| 4.3.1 Overview | **Partially confirmed** | Gauge, prior comparison, state bar, domain bars, top-five absolute movers and findings exist. The user score/mover calculation is percent clean, not the weighted health score. No peer benchmark is implemented. |
| 4.3.2 Modules | **Partially confirmed** | Matrix, six visual bands, worst cell and CSV export exist. There is no stage-aware toggle. The worst cell ignores domain cells with fewer than 20 eligible observations, an undocumented rule. Config hygiene is repeated as a global value in slices. |
| 4.3.3 Users | **Partially confirmed with major omissions** | Attribution, bulk-name patterns, minimum-volume treatment, coaching bands and export exist. No team filter, minimum input, bulk toggle, trend sparkline, prior/current column, manager rollup or per-user suggested weak-domain action is implemented. Live user metadata does not populate team/role. |
| 4.3.4 Trend | **Partially confirmed / contradicted** | Daily, weekly, monthly and quarterly grains plus created/modified lines exist. The “cohort” table only shows each creation period's score today and compares adjacent cohorts; it does not rescore a cohort at creation, one month, three months and today. Overlays are absent. |
| 4.3.5 Records | **Partially confirmed / contradicted** | State drill-through, reasons, created-by/date, open-record action and CSV export exist. There is no “send to fix list.” Record labels and user names are displayed/exported, contradicting “identifiers, module, state and reason only.” |
| 4.3.6 Fix | **Partially confirmed / missing execution** | Three waves, selectable actions, effort, counts, projected gains and plan export exist. There are no run controls, previews, writes, snapshots, rollback or SOW generation. Suspected duplicates are incorrectly aggregated into the `merge-duplicates` action despite a dormant `review-duplicates` definition. |
| 5. Data model | **Contradicted in important details** | The executable fact model uses bitmasks plus issue objects and retains labels/names/stage/times. No `failedRuleIds[]` result, persisted cube entity, or cluster object with the documented shape exists. |
| 6.1 Six states | **Confirmed, but open-question text is contradicted** | All six states exist and each fact receives one state. Precedence is an explicit numeric map, not an inference. |
| 6.2 Rule catalogue | **Partially confirmed** | The listed rules are real, but there are 22 total (16 record rules and 6 set rules), not 24. Several descriptions overstate validator behavior or production coverage. |
| 6.3 Thresholds | **Defaults confirmed; editability contradicted** | The default object is exact. No threshold control calls `setRules`; the CSS contains unused threshold styles. `maxExamplesPerRule` is never consumed. |
| 6.4 Domains | **Partially confirmed** | Nine domains and weights are exact; PII and automation are unavailable. Config hygiene is only a crude percentage of scanned fields with at least one value. Overall scoring renormalizes the measurable/applicable weights rather than treating all 100 points as measured. |
| 6.5 Scoring | **Contradicted** | Domain scoring is a severity-weighted mean of per-rule pass rates, not `1 - unique offending records / eligible records`. Overall scoring is normalized by applicable measurable weight. User scoring is percent proper. |
| 6.6 Bands | **Confirmed with one clarification** | Org, three-tier bar, coaching and matrix bands are implemented. The three-tier function is conclusively used for overview domain bars, so it is not an unresolved location. |
| 6.7 Duplicates | **Partially confirmed with algorithmic contradictions** | Signatures, weights and floors exist, but matching is within-module only; there is name blocking and a 40-record block cap; confirmation has shortcut paths that bypass the 0.90 floor/two-strong-field formulation. |
| 6.8 Plausibility | **Confirmed as set-level, but unsafe details omitted** | Six set/record plausibility families exist. Blank-phone grouping, browser-local off-hours interpretation and heuristic close timing create material false-positive risks. |
| 7. Non-functional architecture | **Partially confirmed** | SDK dependency, light-only mode, configuration persistence and retry queue are real. A live CRM extractor is present. Catalyst region, token isolation, consent, Bulk Read, watermark resume and server-side security are not verifiable. |
| 8. Commercial/process constraints | **Mostly deck-only; partially reflected in copy** | Coaching language, reasons, manual suspicious audit and projected gain are reflected in UI/data. Security, “cost before run,” and no-field-value claims are not fully implemented as stated. |
| 9. Data retention | **Contradicted** | Raw page records are transient and signatures are cleared, but the downstream fact/export model retains more than the stated minimal tuple. No retention duration or deletion mechanism exists. |
| 10. Production gaps | **Partly correct, with one major contradiction** | Most listed production capabilities are absent, but the claim that actual live extraction was not found is false. A CRM SDK extraction path is implemented. |
| 11. Open questions | **Partly valid, partly resolved by code** | State precedence and the three-tier band's location are resolved by source. The complete production rule catalogue remains missing. Additional blocking questions are identified below. |

## Confirmed items

1. **Reducer lifecycle and cancellation.** The reducer defines the five phases and preserves scan configuration on reset. An `AbortController` is used by Cancel. Evidence: `app/assets/widget-DzJ0ge9W.js` offsets ~200,892–204,704 (`Lg`, `Tg`).

2. **Mock fallback and live client selection.** The mock generator supplies five seeded modules and users. Live mode requires the SDK, CRM namespace and iframe context; otherwise the app selects the mock client. Evidence: bundle offsets ~143,000–154,900 (`Nh`, `tf`, `Mh`, `Lh`); `app/widget.html` lines 10–16.

3. **Live CRM read path.** The live client calls `CRM.META.getModules`, `CRM.META.getFields`, `CRM.API.getRecordCount` or COQL, `CRM.API.getAllRecords`, and `CRM.API.getAllUsers`; it can open a selected record in CRM. Evidence: bundle offsets ~154,764–159,700 (`Rh`).

4. **Retry/throttle behavior.** Requests run through a queue with concurrency 3, a 60 ms minimum interval, four retries and exponential backoff for selected network/rate-limit errors. Evidence: bundle offsets ~153,072–154,620 (`ef`).

5. **Six terminal states and explicit ordering.** The state arrays, labels and numeric precedence map are present. Evidence: bundle offsets ~186,646–188,100 (`Zt`, `Mu`, `gg`).

6. **Rule inventory.** There are 16 per-record rules (`zn`) and six set rules (`sa`), covering completeness, validity, freshness, integrity, plausibility and duplication. Evidence: bundle offsets ~169,000–186,700; registries at ~179,351 and ~186,646.

7. **Default thresholds and depth/range choices.** The numerical defaults, depth caps and six quick ranges are present. Evidence: bundle offsets ~198,300–200,560 (`ro`, `Lf`, `or`, `Pf`).

8. **Shared report slicing.** Facts can be sliced by module, user, attribution, clock, range and state; six report tabs use a shared filter bar. Evidence: bundle offsets ~188,630–192,600 (`Sg`), ~204,721 (`$g`), and ~226,463 (`Wg`).

9. **Band functions.** `Zh`, `Xh`, `Ng`, and `Iu` implement the documented thresholds. `Xh` is used by the overview domain score bars. Evidence: bundle offsets ~165,318, ~192,688, ~225,247 and ~235,247.

10. **Only configuration is locally persisted.** The scan object itself is not written to local storage. The live client reads an org variable if available and otherwise uses local storage, but saving always uses local storage. Evidence: bundle offsets ~158,300–158,960 and ~202,013–204,200.

11. **PII/access and automation are unavailable.** Both are explicitly marked unmeasurable with backend-required explanations. Evidence: bundle offsets ~163,000–165,200 and ~197,500.

12. **No remediation write implementation.** Every action definition is `runnableHere: false`; the Fix screen only selects actions and downloads a plan. Evidence: bundle offsets ~207,120–211,500 (`Fg`) and ~231,500–235,200 (`Gg`).

## Discrepancies

### D1 — Live extraction is implemented (critical specification error)

The spec says the extractor is entirely synthetic and that no live extraction path exists. The bundle has a complete `Rh` Zoho client and selects it when framed with `window.ZOHO.embeddedApp` and `window.ZOHO.CRM`. It discovers modules/fields/users, counts records, pages through records and evaluates them. Evidence: `app/assets/widget-DzJ0ge9W.js` offsets ~154,645–159,700 and ~193,990–197,950. This changes the migration baseline, security analysis and production-gap assessment.

### D2 — Scoring formula is materially different

For each domain, the code computes each rule's pass rate, multiplies it by a severity factor (`critical 3`, `high 2.5`, `medium 2`, `low 1.5`, `info 1`), then averages those weighted rule scores. `eligible` and `offending` totals may count a record more than once across rules. The overall score divides by the sum of applicable, measurable weights, so the unmeasurable seven points are excluded rather than contributing zero. Evidence: bundle offsets ~188,630–191,000 (`Sg.compute`). This contradicts §6.5 and makes phrases such as “X of Y eligible records fail at least one rule” mathematically unsafe.

### D3 — State precedence is explicit, not inferred

`Mu` assigns `proper:0`, `incomplete:1`, `inaccurate:2`, `suspicious:3`, `suspected_duplicate:4`, `confirmed_duplicate:5`; `gg` chooses the greatest value. Evidence: bundle offsets ~187,800–188,100. Specification §6.1 and open question 1 incorrectly say no priority constant was found.

### D4 — User score is percent clean, not the weighted score

`Sg.byUser` computes the slice, then stores `score = properPct` if the record floor is met. Coaching bands operate on this percent-clean value. Evidence: bundle offsets ~192,000–192,700. Module and org scores use the weighted domain formula. The spec's single “score” concept and user data model conceal this semantic difference.

### D5 — Duplicate scope and confirmation differ from the stated algorithm

- Blocking keys are prefixed with module, so comparisons do not occur across Leads, Contacts, Accounts and Vendors.
- A normalized-name prefix block (`|nm|` using the first eight normalized characters) exists but is omitted from the spec.
- Blocks containing more than 40 records are skipped entirely.
- Exact strong ID confirms directly.
- Exact email plus exact phone, or exact email plus name similarity of at least 0.90, can confirm without the configured 0.90 confidence floor. The displayed confidence can therefore be below 0.90.
- The result retained per record is only its best partner; the transient global pair list is not the documented cluster model.

Evidence: bundle offsets ~183,943–186,650 (`fg`, `pg`, `Eu`, `Mf`). The deck's product wording is on slides 5–7; it does not validate these code-level shortcuts.

### D6 — Repeated-phone plausibility can group missing values (critical false-positive risk)

The phone grouping callback returns `module::${sf(signature.phone)}` whenever a signature object exists. A signature object is created for every fact, even if the phone is empty. Thus five or more records with blank phone values in a module can be treated as sharing a mobile value and marked suspicious. The email path correctly checks for a non-empty email. Evidence: bundle offsets ~181,122–181,900 (`Cf`) and ~193,268 (`jg`). This conflicts with the requirement that suspicious findings be conservative and defensible.

### D7 — Data retention and export are not identifiers/states only

Each fact retains `label`, creator/modifier/owner IDs and names, timestamps and stage, plus issue messages. Some messages embed source values—for example an invalid picklist value or dummy name. The record-list export includes record label, creator, modifier, owner, stage, dates and those messages. The Records export includes creator name/date. `Eu` retains duplicate pair IDs, confidence, reasons and blocking keys after a scan until another duplicate run; those keys can contain normalized statutory IDs, emails or phones. Evidence: bundle offsets ~196,000–197,950 (fact construction), ~218,153–221,000 (`Bg`), ~245,754–249,400 (`qg`), and ~184,308–186,300 (`Eu`). The UI note at ~221,000 says “Identifiers and states only,” but the actual state and CSV mappings contradict it.

### D8 — Thresholds are not operator-editable in the UI

The defaults and reducer action exist, but no rendered control invokes `setRules`. CSS selectors such as `.control-grid.thresholds`, `.rule-groups`, and `.toggle-row` are unused by the JavaScript. The stage-aware, minimum-record and exclude-bulk settings therefore have no setup controls. Evidence: bundle offsets ~199,629, ~200,892–204,400 and ~251,302–255,000; CSS bundle selectors exist on its single minified line. This contradicts §§4.1, 4.3.2, 4.3.3 and 6.3.

### D9 — Setup cost estimates are not based on records in range

The setup estimate uses the selected depth cap (100,000 for full), assumes 200 records per request, adds fixed metadata calls, and multiplies by 1.2 seconds to estimate minutes. It does not load module counts during setup, query records-in-range, inspect the org credit budget, or show a hard ceiling. Evidence: bundle offsets ~251,302–254,950 (`ty`). The deck asks for record count, credit consumption and runtime before commit (slide 14), but the code only provides a rough cap-based estimate.

### D10 — Several screen behaviors are overstated

- **Modules:** no stage-aware toggle; “worst cell” ignores cells with fewer than 20 eligible rule observations. Evidence: ~235,247–238,200 (`Iu`, `Yg`).
- **Users:** no team/minimum/bulk controls and no trend sparkline. Live `getUsers` does not retain role/team, so live team cells are blank. Evidence: ~157,700 and ~259,846–264,100 (`ry`).
- **Trend:** the cohort table has only records, score today and an adjacent-cohort reading—not the four age checkpoints. Evidence: ~255,049–259,450 (`ny`).
- **Records:** no send-to-fix-list action; record label and user name are shown. Evidence: ~245,754–249,400 (`qg`).
- **Fix:** no run control, preview or SOW button. Evidence: ~231,500–235,200 (`Gg`).

### D11 — The reconstructed data model does not match executable state

The scan's `facts` contain bitmask fields `eligible` and `failed`, a terminal `state`, and up to three issue objects per record rule plus set-rule issues. There is no `failedRuleIds[]` property. The “cube” is an in-memory class with memoized slices, not a serialized pre-aggregated cube. Duplicate results are pairs, not `{clusterId, matchType, matchedFields[]}` clusters. User entries contain a nested computed slice and use percent proper. Evidence: bundle offsets ~188,630–197,950.

### D12 — Configuration hygiene is not the described domain

`Mg` scores configuration as the percentage of scannable fields that have at least one non-empty value in the extracted sample. It does not assess unused modules, dead workflows, layout sprawl or duplicate picklists. The same global value is inserted into every module slice. Evidence: bundle offsets ~197,969–198,250 and `Sg.compute` around ~190,000. This makes module-level overall scores partly dependent on an org-global heuristic.

### D13 — Date-bounded extraction is client-side and assumption-dependent

The live path uses `getAllRecords`, sorted by the selected clock, then filters the union of current and prior ranges in JavaScript. It stops after encountering more than 25 records older than the lower bound. It is not a Bulk Read/COQL date-bounded collector, has no watermark resume, and does not pass the supported `fields` list from the evaluator into the page request. Evidence: bundle offsets ~159,600–162,000 (`Oh`) and ~193,990–197,950 (`Eg`). Missing/unsorted/null dates or SDK paging behavior can yield incomplete results.

### D14 — Read-only and permission claims are assumptions, not enforcement

The called data APIs are read-oriented, and writes are absent, but the widget does not inspect OAuth scopes, show a scope list, record consent, enforce least privilege or detect partial record visibility. Setup explicitly says scans run as the signed-in user and respect that profile's access. Evidence: bundle offsets ~251,600 and live-client calls ~154,764–159,700. A signed-in user's limited visibility can silently turn a partial view into an apparent org score.

### D15 — Rule count and unused configuration are misstated

There are 22 rules, not 24. `maxExamplesPerRule` occurs only in the default object and is never enforced. Per-record evaluation instead hard-caps stored issues to three per rule invocation (`kl.slice(0,3)`), while all set-rule issues are retained. Evidence: registries at ~179,351 and ~186,646; default at ~199,629; evaluator at ~195,500–196,500.

### D16 — Fix routing and projected gains are unsafe

`duplication.fuzzy` always has `fixKey: "merge-duplicates"`, so suspected and confirmed duplicate failures aggregate into the merge action. A `review-duplicates` definition exists but is not bound to a rule. Projected gain is calculated by removing all failures for an action's rule IDs; the UI then sums independently calculated gains for selected actions, which is not guaranteed to equal the combined rescored result when actions overlap. Evidence: bundle offsets ~184,320, ~207,120–211,500 and ~216,648–217,500 (`$f`).

### D17 — API statistics can be misleading across scans

The request queue is a module-level singleton. Its retry/failed counters are cumulative, while the per-run wrapper's dispatch count is new. `runStarted` does not reset `apiStats`. The running screen displays dispatched and retried but not failed. Evidence: bundle offsets ~153,072–154,620, ~200,892–204,200 and ~249,621–251,250.

## Missing items

The following are absent from executable source, even where the deck describes them:

- Catalyst authentication, token vault, per-org tenancy/isolation and India-region enforcement.
- OAuth scope verification, consent record, profile/permission discovery and an org-wide service identity.
- Bulk Read jobs, COQL date paging as the primary collector, watermark resume, resumable jobs and an enforced API-credit ceiling.
- PII/access and automation-health evaluators.
- Approximately 48 additional rules needed to reach the deck's “roughly 70” launch catalogue.
- A durable aggregation cube, scan history, comparable prior scan storage and benchmark feed.
- True creation-cohort ageing snapshots and event overlays.
- Team, territory and manager rollups; live role/team mapping.
- Rule-threshold editor, stage-aware toggle, minimum-user-volume control and bulk-account toggle.
- PDF/SmartBrowz output, Generate SOW, schedules, alert floors and monthly reporting.
- Remediation preview, exact before/after display, write execution, snapshot retention and rollback.
- Side-by-side duplicate review, survivorship policy capture and safe merge workflow.
- Desk, Books, Creator, People and Analytics collectors/rule packs.
- Data-retention duration, deletion jobs, subject/access procedures and audit logs.
- Seeded acceptance harness, false-positive metrics, runbook and rollback-of-a-bad-rule process.

## Ambiguities

1. **Built artifact provenance.** There is no source map, package manifest, unminified source, test suite, build commit or dependency lockfile. Exact source lines and original names cannot be recovered reliably.
2. **SDK behavior.** The supplied archive does not define the semantics, limits or authorization behavior of the externally loaded Zoho Embedded App SDK. Its remote script is a runtime supply-chain dependency (`app/widget.html` line 15).
3. **Meaning of `proper`.** It means “no implemented applicable rule failed,” not necessarily “data is correct.” Unmeasured domains and missing fields/API visibility can still yield `proper`.
4. **Severity semantics.** Severity weights are embedded numerical scoring coefficients, but neither the spec nor deck approves those exact values.
5. **Duplicate policy.** “Strong identifier,” cross-module matching, account context, cluster transitivity, block overflow and confirmation shortcuts need a formal policy.
6. **Clock/time zone.** Date parsing, off-hours detection and fiscal-year calculations run in the browser's local time zone. The intended org/client time zone is not defined.
7. **Sample interpretation.** The scanner selects newest records from the current-plus-prior window. Whether rates can be extrapolated, especially for clusters and bursts, is not established.
8. **Partial failure policy.** A module error does not fail the scan. It is unclear whether a partial report should be scoreable or releasable.
9. **Configuration score scope.** The deck calls configuration hygiene org-level, yet the current overall/module rollups include the same global value in every slice.
10. **Retention boundary.** “Field values discarded after evaluation” does not define whether names, labels, reason strings, timestamps, lookup labels and duplicate keys are field values or dimension keys.

## Technical risks

1. **False accusations:** blank repeated phones, local-time off-hours rules, simplistic dummy-value heuristics and modified-time-as-close-time can create suspicious findings about named users.
2. **Score non-reproducibility:** org/module scoring, user percent-clean scoring and deck examples use different semantics; rule eligibility and severity can change scores without changes in record quality.
3. **Double counting:** domain eligible/offending totals aggregate rule observations, not unique records, while UI copy describes records.
4. **Incomplete live scans:** profile-limited access, module-level swallowed errors, paging assumptions, sample caps and the 100,000 ceiling can silently omit data.
5. **Duplicate misses and misclassification:** blocks over 40 are skipped; matching is not cross-module; best-partner facts lose cluster topology; shortcut confirmation can bypass the stated confidence policy.
6. **PII leakage:** names, record labels, dates, stages and ownership data are retained in memory and exported despite minimal-data claims.
7. **Memory/performance:** the entire fact set, issue lists and signatures are held in browser memory for set-level rules. The “full” mode can reach 100,000 per module and runs pair work client-side.
8. **Dead/misleading controls:** `setRules`, `maxExamplesPerRule`, `review-duplicates` and unused CSS imply incomplete refactors. UI copy can claim safeguards not enforced by code.
9. **Projection error:** summing independent action gains may overstate the selected remediation outcome.
10. **External runtime dependency:** the SDK is loaded from a remote URL with no integrity pin, and SDK absence silently selects synthetic data.

## Catalyst migration risks

1. **Do not port the bundle as the normative algorithm.** First freeze an approved rule and score contract with golden test fixtures. The deck, spec and bundle currently describe different mathematics.
2. **Backend identity changes result semantics.** A Catalyst integration user may see more records and metadata than the current signed-in widget user. Scores will not be comparable unless the visibility model is explicit.
3. **Python parity requires a conformance suite.** JavaScript date parsing, regexes, floating-point rounding, string normalization and Jaro-Winkler-style similarity must be reproduced intentionally, not accidentally.
4. **Set-level rules need bounded batch architecture.** Bursts, repeated values and duplicates require partitions, spill/storage strategy and deterministic windows; loading a full org into one function is unsafe.
5. **The cube must be redesigned, not serialized from `Sg`.** The current “cube” recomputes and memoizes in browser memory. Catalyst needs durable dimensional facts, versioned rule results and reproducible slices.
6. **Retention must be enforced at schema and export boundaries.** Decide whether labels, names, reasons, timestamps and keys are permitted, encrypt what remains, set TTLs, and prove deletion.
7. **Jobs need idempotency and resume.** Current extraction has no watermark or durable job state. Catalyst retries must not duplicate facts, API usage or actions.
8. **Action centre requires a separate authorization boundary.** Read scans and write remediations should use distinct scopes, explicit approvals, immutable snapshots and tested rollback.
9. **Multi-product scope is not a straightforward extension.** Desk/Books/Creator/People/Analytics have different APIs, identifiers, permissions, rate limits and data-residency implications.
10. **Data-region claims require deployment evidence.** Nothing in the widget proves Catalyst India placement, log residency, backup locality or third-party PDF processing locality.

## Questions that must be resolved before implementation

### Scoring and state policy

1. Is the authoritative domain formula unique offending records, severity-weighted per-rule pass rates, or another method? How are multiple failures on one record counted?
2. Are unavailable domains excluded and remaining weights renormalized, or is an overall score withheld until all required domains are measurable?
3. Should user score be percent proper or the same weighted domain score used for org/modules? Which value drives coaching bands?
4. Is the implemented state precedence approved? If not, what deterministic multi-failure policy applies, and must all underlying states remain queryable?
5. Is configuration hygiene allowed to affect module/user slices, or only the org score?
6. What are the approved severity coefficients and rounding rules?

### Duplicate and plausibility policy

7. Are duplicates matched within a module, across modules, or both? Which module pairs are valid?
8. What exactly is a strong identifier, and can email plus phone/name confirm below 0.90?
9. How should oversized blocks, transitive clusters, record survivorship and one-record/multiple-cluster cases be handled?
10. Must suspected duplicates always route to review and confirmed duplicates alone route to merge?
11. What minimum precision/false-positive threshold must every suspicious rule meet before named-user display is enabled?
12. Which timezone governs bursts/off-hours, and what audit/event timestamp represents “closed” rather than using `Modified_Time`?
13. Should missing phone/email values be excluded from repeated-value grouping? (They should be unless product policy says otherwise.)

### Extraction, permissions and failure policy

14. Will scans use the signed-in user's visibility or an org-wide integration identity? How will partial visibility be disclosed?
15. What exact read scopes are required for each domain/product, and who grants/revokes them?
16. What are the hard per-run credit ceiling, concurrency limits, business-hour rules and resume semantics?
17. Is a scan with one failed/truncated module invalid, partial-but-displayable, or releasable with a qualified score?
18. What is the authoritative date-bound query and behavior for null/malformed timestamps?
19. Which live modules and Zoho products are in v1 of the Catalyst migration?

### Data model, privacy and retention

20. Which values may persist: record ID, module, state, rule IDs, reason, user ID/name, label, stage, timestamps, duplicate partner/key and confidence?
21. Which of those values may be displayed, exported, printed or sent through PDF generation?
22. What are the TTL, deletion trigger, backup retention, audit-log retention and per-org purge requirements?
23. Are reason strings allowed to embed source field values or user names? If not, define structured reason templates.
24. Is the aggregation cube built from record-level retained facts or irreversible aggregates, and how are rules rescored after a rule-version change?

### Product scope and acceptance

25. Which deck features are required for the first production release versus later phases: PDF, schedules, alerts, benchmarks, SOW, actions and rollback?
26. Where is the reviewed ~70-rule catalogue, including applicability, eligibility, severity, state, fix, prevention and test fixtures?
27. What golden seeded datasets and expected scores/states will be used for JavaScript-to-Python parity and regression testing?
28. Who approves named-user findings, and when must the system suppress individuals and show team-level results only?
29. What precision, recall, runtime and API-credit acceptance thresholds define production readiness?
30. Which document becomes authoritative after these questions are answered: a corrected specification, a versioned rule catalogue, or executable conformance tests?

## Conclusion

Implementation should pause until the critical discrepancies—live extraction scope, scoring, state precedence, duplicate confirmation, suspicious-rule safety, data minimization and authorization—are resolved in an approved contract. The existing bundle is valuable as a prototype and source of test cases, but it should not be treated as the production specification without correction.
