# Current Authorization-Boundary Audit

**Scope:** Existing backend/domain code, its tests, and the synthetic verification runner  
**Product authority:** `approved-product-contract.md`  
**Execution boundary:** `implementation-authorization-matrix.md`  
**Reviewed supporting reports:** `next-approval-package.md` and `d4-d5-production-authoring-contradiction.md`  
**Audit date:** 17 August 2026

## 1. Classification rules

Every row below has exactly one classification:

- **AUTHORIZED** — the exact behavior is explicitly approved by the product contract.
- **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** — the contract approves the outcome and delegates or necessarily permits this non-product-facing mechanism.
- **REQUIRES PRODUCT APPROVAL** — the behavior, parameter, terminal outcome, external representation, or implementation authorization is not fixed by the contract.
- **REQUIRES TECHNICAL VERIFICATION** — product behavior is approved, but this mechanism or platform assumption is not proven.
- **PROHIBITED** — the contract or matrix expressly disallows the behavior.

Passing a unit test does not change a classification. The decision register, reverse-engineered specification and old widget were not used to infer approval.

## 2. Executive finding

The domain package is not wired to production routes, UI, OAuth, Zoho APIs, Catalyst storage or collectors. Most implemented functions are either exact approved primitives or boundary guards.

The following implemented behavior is outside explicit product approval:

1. `duplicates.py:46` maps confidence below `0.70` to `None`; the contract/matrix do not explicitly authorize that terminal outcome. **REQUIRES PRODUCT APPROVAL.**
2. `tests/test_authorized_domain.py:178–179` encodes the same below-floor result as expected behavior. **REQUIRES PRODUCT APPROVAL.**
3. D2/D4 arithmetic uses a 28-digit Decimal context. This is not customer rounding, but it is an unverified numerical implementation choice. **REQUIRES TECHNICAL VERIFICATION.**
4. TZ-1's exact disclosure sentence is implementation-authored copy; the requirement to disclose is approved, but the exact customer-facing wording is not. **REQUIRES PRODUCT APPROVAL** before it is exposed.
5. TZ-1's timestamp resolver treats a supplied `None` genuine timestamp as absence; production use requires proof that `None` means genuinely unavailable rather than not fetched, inaccessible or failed. **REQUIRES TECHNICAL VERIFICATION.**

No other current domain behavior was found to cross the product-authorization boundary. Several safe guards and spikes remain non-production engineering mechanisms as classified below.

## 3. D2 — scoring

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Severity coefficients `3/2.5/2/1.5/1` | `scoring.py:8–14` | **AUTHORIZED** | Exact D2 coefficients. |
| Per-rule pass rate and severity-weighted domain mean | `scoring.py:55–78` | **AUTHORIZED** | Exact D2 formula. |
| Multiple rule observations may count the same record more than once | Represented by independent `RuleObservation` inputs; tested at `test_authorized_domain.py:52–59` | **AUTHORIZED** | D2 expressly adopts rule-observation counting. |
| Reject negative counts or `offending > eligible` | `scoring.py:24–30` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Input integrity preserves the approved formula and selects no customer behavior. |
| Refuse an empty rule set | `scoring.py:59–63` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | This is a stop rather than a score/default. The resulting product behavior still needs approval before wiring. |
| Refuse a zero-eligible rule | `scoring.py:64–67` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | The matrix requires a product decision; raising prevents an inferred result. |
| Decimal internal precision of 28 digits | `scoring.py:50–52,69–70,98–99` | **REQUIRES TECHNICAL VERIFICATION** | The contract does not define numerical representation. Verify deterministic accuracy; customer rounding remains separately unapproved. |
| Filter explicitly `applicable` and `measurable` domains | `scoring.py:90–92` | **AUTHORIZED** | Exact D2 normalization rule. |
| Require `d12_resolved_and_revalidated=True` before overall normalization | `scoring.py:81–88` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | It prevents silent D12 exclusion. No production caller exists. |
| Calculate an overall score after the caller asserts D12 is resolved | `scoring.py:90–106` | **AUTHORIZED** | The formula itself is approved; current production use is blocked until the assertion can truthfully be supplied. |
| Publish an overall score while D12 is unresolved or silently omit Configuration Hygiene | Not implemented | **PROHIBITED** | Conflicts with D2's D12 revalidation requirement and matrix boundary. |

## 4. D4 — user percent clean

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| `properPct = 100 × proper / total` | `scoring.py:42–52` | **AUTHORIZED** | Exact approved D4 formula. |
| Reject negative counts or `proper > total` | `scoring.py:44–47` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Input integrity only. |
| Raise on `total_records == 0` | `scoring.py:48–49` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | It refuses to invent a score. Any surfaced zero-record behavior still requires product approval. |
| Apply no minimum-record floor | `scoring.py:42–52` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | The primitive deliberately computes formula only; it does not choose the unresolved floor. |
| Numeric minimum-record floor | Not implemented | **REQUIRES PRODUCT APPROVAL** | Contract references an existing floor but states no number. |
| Production D4 rule authoring/wiring | Not implemented | **REQUIRES PRODUCT APPROVAL** | Contract line 205 says NO-GO while line 207 says D4 is cleared; authoritative materials do not resolve the authorization conflict. |
| Persisted user score, UI display, or comparability presentation | Not implemented | **REQUIRES PRODUCT APPROVAL** | D7/D10 dependencies are unresolved even though the formula is approved. |

The `properPct` primitive can remain independently. It cannot independently authorize a surfaced production user score.

## 5. D5 — duplicate detection

### 5.1 Classification and confirmation

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Exact strong-identifier match confirms directly | `duplicates.py:30–31` | **AUTHORIZED** | Exact D5.1 shortcut. |
| Exact email plus exact phone confirms directly | `duplicates.py:32–33` | **AUTHORIZED** | Exact D5.1 shortcut. |
| Confidence `>=0.90` plus at least two exact strong fields confirms | `duplicates.py:34–38` | **AUTHORIZED** | Exact standard confirmation condition. |
| Confidence `[0.70,0.90)` becomes suspected duplicate | `duplicates.py:39–40` | **AUTHORIZED** | Reads D5's suspected band together with confirmation beginning at `>=0.90`; the unresolved exactly-`0.90`/insufficient-fields case is stopped separately. |
| Confidence `>=0.90` with fewer than two exact strong fields raises `ProductApprovalRequired` | `duplicates.py:41–45` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | The contract does not assign the fallback state; raising prevents an inference. |
| Confidence below `0.70` returns `None` | `duplicates.py:46` | **REQUIRES PRODUCT APPROVAL** | This selects a non-duplicate terminal outcome not explicitly classified by the contract/matrix. It must not be wired or treated as a golden behavior. |
| Test asserts below-`0.70` is not a duplicate | `test_authorized_domain.py:178–179` | **REQUIRES PRODUCT APPROVAL** | Passing test documents code, not product authorization. |
| Confidence range validation `[0,1]` and nonnegative strong-field count | `duplicates.py:21–25` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Defensive input validation; it defines no duplicate policy. |
| Exact email plus fuzzy-name direct confirmation | Not implemented | **PROHIBITED** | D5 expressly removes this shortcut. |

### 5.2 Candidate generation and blocking

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| First eight characters of an already-normalized name form the `|nm|` block | `duplicates.py:49–59` | **AUTHORIZED** | D5.4 keeps this exact blocking strategy. |
| Prefix block includes the module in the constructed key | `duplicates.py:59` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Implements approved within-module-only scope without adding cross-module matching. |
| Blank pre-normalized name returns no name-prefix key | `duplicates.py:57–58` | **REQUIRES PRODUCT APPROVAL** | The contract does not state the candidate-generation outcome for an absent/blank normalized name. No production caller currently relies on it. |
| Name/email/phone/company/strong-ID normalization | Not implemented | **REQUIRES PRODUCT APPROVAL** | The contract does not pin the authoritative `spec §6.7` filename/version; no old spec default may be imported. |
| Email, phone and strong-ID block construction | Not implemented | **REQUIRES PRODUCT APPROVAL** | Exact mechanics are not present in the contract text and authoritative spec identity is unresolved. |
| Cross-module candidate matching | Not implemented | **PROHIBITED** | D5.2 restricts v1 to within-module. |
| Persisted raw, HMAC, hashed or digested blocking keys/fingerprints | Not implemented | **PROHIBITED** | D7/matrix prohibit this persistence. |

### 5.3 Confidence calculation and strong fields

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Caller supplies an already-calculated confidence | `PairEvidence.confidence`, `duplicates.py:13–19` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | The classifier consumes evidence but does not calculate it. It must not be wired until the upstream calculation is approved. |
| Caller supplies `exact_strong_field_count` | `duplicates.py:16` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | The approved rule requires a count; the field definitions themselves are not selected. |
| Weighted confidence formula, weights and missing-field denominator | Not implemented | **REQUIRES PRODUCT APPROVAL** | Requires a confirmed authoritative spec or explicit contract approval. |
| Fuzzy string-similarity algorithm | Not implemented | **REQUIRES PRODUCT APPROVAL** | No authoritative algorithm is pinned. |
| Exact strong-field definitions | Not implemented | **REQUIRES PRODUCT APPROVAL** | Examples in the contract do not authorize an exhaustive field set. |

### 5.4 Tie-breaking and splitting

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Deterministic pair/partner tie-breaking | Not implemented | **REQUIRES PRODUCT APPROVAL** | No product-visible tie-break is specified. A lossless internal ordering could later be an engineering choice but is not currently implemented. |
| Blocks over 40 must be split without missing comparisons | Expressed only by synthetic spike | **AUTHORIZED** | Exact approved D5.3 outcome. |
| Fixed chunks of 40 plus complete cross-chunk upper-triangular evaluation | `spikes/run_synthetic_verifications.py:27–49` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | D5 delegates deterministic no-loss splitting mechanics. This remains spike-only. |
| Pair-count verification for 41/81/101 records | Synthetic runner | **REQUIRES TECHNICAL VERIFICATION** | Local PASS proves mathematical coverage for fixtures, not CRM/API runtime, memory, idempotency or privacy. |
| Skip blocks over 40 | Not implemented | **PROHIBITED** | Directly conflicts with D5.3. |
| Production D5 detector/rule authoring | Not implemented | **REQUIRES PRODUCT APPROVAL** | Contract line 205/207 authorization contradiction remains unresolved. |

## 6. D6 — repeated-value blank handling

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Exclude `None`, empty and whitespace-only values from grouping | `operations.py:10–20` | **AUTHORIZED** | Implements D6's blank-phone exclusion and preserves the established email behavior. |
| Generic utility can be called for values other than phone/email | Function signature at `operations.py:10–12` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Generic code reuse is non-product-facing; applying it to another product rule would require separate authorization. |
| Normalize or threshold repeated values | Not implemented | **REQUIRES PRODUCT APPROVAL** | No thresholds/defaults are selected here. |

## 7. D7 — minimization and privacy guards

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Literal minimized finding fields | `privacy.py:8–18` | **AUTHORIZED** | Matches D7 tuple. |
| Require record ID/module and bound confidence to `[0,1]` | `privacy.py:20–26` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Defensive integrity for the approved tuple. |
| Project the minimized tuple to a dictionary | `privacy.py:28–41` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | No route/file persistence exists; field set remains within D7. |
| Serialize duplicate confidence as a string | `privacy.py:36–39` | **REQUIRES TECHNICAL VERIFICATION** | Exact transport representation is not product-approved and must be verified before any export/API use. |
| Forbid obvious names/stages/source/contact/timestamp/user/dimension keys | `privacy.py:44–64` | **AUTHORIZED** | Enforces D7 exclusions; forbidding more persistence does not add product behavior. |
| Recursively detect forbidden key names | `privacy.py:67–79` | **REQUIRES TECHNICAL VERIFICATION** | It is a defensive heuristic, not proof against values hidden under unexpected keys or logs/traces. |
| Operational metadata, job linkage, aggregates, opaque user tokens, durable exports or retention defaults | Not implemented | **REQUIRES PRODUCT APPROVAL** | These are outside the approved D7 tuple and must not be created unless an exact future decision authorizes them. |
| Persisted raw source fields, blocking keys, or raw/HMAC/hashed/digested duplicate fingerprints | Not implemented | **PROHIBITED** | Current D7/matrix boundary expressly excludes these durable forms. |

## 8. D13 — durable extraction/jobs

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Production durable batch/job model | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | Product direction is approved; exact Zoho/Catalyst mechanism is unverified and D7 blocks production persistence. |
| Temporary SQLite checkpoint/resume/idempotency example | `spikes/run_synthetic_verifications.py:52–132` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Synthetic spike only; not a Catalyst schema. |
| Non-null synthetic uniqueness key after retry hazard discovery | Spike lines 63–74 and fixtures | **REQUIRES TECHNICAL VERIFICATION** | Demonstrates a local SQLite property, not Catalyst uniqueness/transaction semantics. |
| Browser/transient-only authoritative final result | Not implemented | **PROHIBITED** | D13 requires persisted batch results. |
| Collector selection, watermark, leases, completion fence and final aggregation | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | Approved direction, unverified mechanisms; persistence shape also needs D7 approval. |

## 9. D14-POLICY — authorization

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Accept only nonempty scope strings ending in `.READ` | `authorization.py:9–18` | **AUTHORIZED** | Enforces explicit read scopes. |
| Reject `.ALL`, `.CREATE`, `.WRITE`, `.UPDATE`, `.DELETE`, `.SHARE` and other non-READ suffixes | `authorization.py:4–17` | **AUTHORIZED** | Consistent with contract/matrix read-only boundary. |
| Exact Zoho scope allowlist/capability mapping | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | Real scope names and operation requirements must be verified. |
| Admin-authorized org connection, consent disclosure and org binding | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | Product behavior is approved; API/platform proof is outstanding. |
| Individual operator personal-session authorization | Not implemented | **PROHIBITED** | Conflicts with D14-POLICY. |

## 10. D14-EVIDENCE — visibility evidence

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Live D14-EVIDENCE test harness/results | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | No Zoho sandbox evidence was collected. |
| Administrator-status proof, granted-scope introspection, sharing/territory/role tests, visible-vs-total signal | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | These are the contract's defined evidence tasks. |
| Claim of guaranteed org-wide visibility | Not implemented | **PROHIBITED** | D14-EVIDENCE explicitly remains unverified. |
| Production visibility assurance levels/warnings | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | Evidence must define reliable criteria; UI remains D10-gated. |

## 11. D16 — duplicate actions and projected gain

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Suspected duplicate routes to `review-duplicates` | `duplicates.py:62–65` | **AUTHORIZED** | Exact D16 fix. |
| Confirmed duplicate routes to `merge-duplicates` | `duplicates.py:62–65` | **AUTHORIZED** | Exact D16 fix. |
| Apply all selected actions to one candidate and rescore once | `operations.py:23–33` | **AUTHORIZED** | Exact D16 combined-rescore requirement. |
| Gain is combined score minus baseline score | `operations.py:31–33` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Direct numerical expression of projected gain; no UI/rounding is selected. |
| Action ordering/conflict resolution inside `apply_combined` | Supplied by caller, not implemented | **REQUIRES PRODUCT APPROVAL** | The contract forbids independent summing but does not specify conflicting-action semantics. |
| Fix UI or action execution | Not implemented | **REQUIRES PRODUCT APPROVAL** | D10 and production action scope remain unresolved. |

## 12. D17 — API statistics

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| New scan receives zeroed counters | `operations.py:36–46` | **AUTHORIZED** | D17 requires per-run reset. |
| Failed-call count exists | `operations.py:41` | **AUTHORIZED** | D17 requires the tracked failed count. |
| `dispatched`, `completed` and `retried` internal counters | `operations.py:38–40` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Internal telemetry supports per-run stats; no UI representation is selected. |
| Surface failed count on a running screen | Not implemented | **AUTHORIZED** | D17 explicitly requires surfacing it. React/UI work remains outside this audit task and must not be added here. |

## 13. TZ-1 — timezone and close/audit time

| Implemented behavior | Location | Classification | Audit basis |
|---|---|---|---|
| Genuine timestamp wins when supplied | `time_policy.py:28–34` | **AUTHORIZED** | Exact TZ-1 preference. |
| `Modified_Time` used only when genuine timestamp argument is absent | `time_policy.py:35–40` | **AUTHORIZED** | Exact approved fallback condition at the domain-policy level. |
| Approximation status accompanies `Modified_Time` | `time_policy.py:9–12,35–40` | **AUTHORIZED** | TZ-1 requires explicit disclosure, not silent substitution. |
| Exact disclosure sentence | `time_policy.py:15–18` | **REQUIRES PRODUCT APPROVAL** | Requirement is approved; customer-facing wording/placement is not fixed and D10 remains unresolved. |
| Treat `genuine_timestamp=None` as proof that no genuine source is available | Implicit input contract at `time_policy.py:28–41` | **REQUIRES TECHNICAL VERIFICATION** | Production caller must distinguish verified absence from API/permission/not-fetched failure. |
| Return `UNAVAILABLE` when both inputs are absent | `time_policy.py:41` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Stops evaluation only when the caller has verified both sources inaccessible; caller verification is outstanding. |
| Convert an aware instant with Python `ZoneInfo` | `time_policy.py:44–54` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Implements approved org-timezone use without fallback. |
| Raise `TechnicalVerificationRequired` for unknown timezone | `time_policy.py:48–53` | **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION** | Refuses silent browser/server fallback. |
| Zoho organization timezone retrieval, IANA mapping coverage, DST/fiscal boundaries and module source mapping | Not implemented | **REQUIRES TECHNICAL VERIFICATION** | Local fixture tests do not verify Zoho/platform behavior. |
| Silent `Modified_Time` or browser/server timezone substitution | Not implemented | **PROHIBITED** | Directly conflicts with TZ-1. |

## 14. Test and spike status

The existing 25 tests were run after this read-only audit and passed. The synthetic runner also passed its five local verification groups.

These results confirm that the audit changed no behavior. They prove only the current pure-function fixtures and synthetic mechanisms. They do not convert any **REQUIRES PRODUCT APPROVAL** or **REQUIRES TECHNICAL VERIFICATION** row into **AUTHORIZED**.

Notably:

- the below-`0.70` D5 test passes but remains unauthorized;
- the `d12_resolved_and_revalidated=True` test exercises formula mechanics but does not resolve D12;
- the temporary SQLite spike is not Catalyst evidence or a production schema;
- the scope validator does not prove actual Zoho grants/capabilities;
- the timezone tests do not prove Zoho timezone values or genuine module close sources;
- the D7 key-name detector is not a complete leakage proof.

## 15. Exact decisions required from Product before the next implementation step

No further production D4/D5 step should begin until Product answers this smallest set:

1. **Production-authoring authorization:** State separately whether production D4 user-score authoring and production D5 duplicate-detector authoring are authorized now, or remain NO-GO; for each NO-GO, state its release condition.
2. **D4 floor:** State the exact numeric minimum-record floor required before `properPct` may be surfaced.
3. **D5 authoritative mechanics:** Identify the exact authoritative `spec §6.7` filename/version, or explicitly approve the exhaustive normalization, strong-field set, confidence formula/weights/denominator and fuzzy-similarity algorithm.
4. **D5 unresolved outcomes:** State the terminal outcome for (a) confidence below `0.70`, (b) confidence `>=0.90` with fewer than two exact strong-field agreements, and (c) blank/missing input for the normalized-name prefix block.

Those four decisions unblock only a subsequent bounded D4/D5 domain slice. They do not authorize UI, routes, OAuth, collectors, persistence, aggregates or production deployment.

Before any overall-score slice, Product must separately resolve D12 and zero-eligible-rule behavior. Before any persistence or integration slice, the D7 product gates and D14/Zoho/Catalyst technical gates remain mandatory; they are not folded into the four D4/D5 questions above.

## 16. Final boundary

- **AUTHORIZED:** Exact contract formulas, state precedence, approved D5 branches/policy, D6 blank exclusion, literal D7 tuple, explicit read-scope rule, D16 fixes, D17 reset/failed counter, and TZ-1 genuine/disclosed-fallback semantics.
- **IMPLEMENTATION DETAIL AUTHORIZED UNDER AN APPROVED DECISION:** Defensive validation/stops, internal data objects, generic non-product-facing helpers, and the synthetic deterministic chunk/checkpoint mechanisms.
- **REQUIRES PRODUCT APPROVAL:** D4/D5 production authorization, D4 floor, D5 missing mechanics/outcomes, exact TZ disclosure copy, D2 zero-eligible customer behavior, D12, D7 operational metadata/linkage/credentials/aggregates/tokens/exports/retention boundaries and unresolved D10/action behavior.
- **REQUIRES TECHNICAL VERIFICATION:** Numerical representation, D5 API/runtime/privacy, D7 leakage controls, D13 jobs, D14-POLICY feasibility, all D14-EVIDENCE, Zoho timezone/close sources and Catalyst platform semantics.
- **PROHIBITED:** Cross-module matching, email-plus-fuzzy-name shortcut, skipped oversized blocks, non-read OAuth, visibility guarantees, silent timezone/`Modified_Time` fallback, transient-only authoritative final results, persisted source values/blocking keys/fingerprints, and any production behavior that contradicts the current contract.

No code, test, UI, route, schema, OAuth flow, collector, persistence, configuration or authoritative document was modified by this audit.
