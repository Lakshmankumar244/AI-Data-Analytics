# Next Approval Package

**Purpose:** Prepare the next product-approval decision without expanding implementation scope  
**Product authority:** `approved-product-contract.md`  
**Execution boundary:** `implementation-authorization-matrix.md`  
**Audit date:** 17 August 2026

## 1. Status vocabulary

- **APPROVED PRODUCT DECISION** — the product behavior is explicitly approved by the contract. Approval does not imply that platform feasibility or production dependencies have passed.
- **IMPLEMENTATION DECISION** — an engineering mechanism that may be evaluated only within the matrix boundary. It is not product approval.
- **REQUIRES PRODUCT APPROVAL** — the contract or matrix does not specify/authorize the behavior. No default may be selected.
- **TECHNICAL VERIFICATION REQUIRED** — product direction is approved, but Zoho/Catalyst behavior or the proposed engineering mechanism is not proven.
- **BLOCKED** — the component must not be wired into production because a product approval, technical result, or cross-cutting dependency is outstanding.

## 2. Audit conclusion

The current implementation remains a bounded, side-effect-free Python domain library plus tests and synthetic spikes. It contains no React/UI changes, production routes, Catalyst schema, OAuth flow, CRM collector, production persistence, aggregate model, retention behavior or configuration default.

The contract and matrix authorize the implemented formulas/policy fragments as isolated primitives. They do **not** authorize production D4/D5 rule authoring because the contract's Section 5 wording remains contradictory. They also do not authorize the missing D4 floor, missing D5 edge mechanics, D7 production storage, D12 behavior or D14 visibility claims.

One possible authorization-boundary crossing was found in the D5 primitive and test: confidence below `0.70` is converted to `None` (“not a duplicate”) even though the matrix does not separately classify that terminal outcome. It is reported in Section 12 and was not changed.

## 3. Authorized and locally verified

| Component | Status | Local evidence | Production limit |
|---|---|---|---|
| D2 severity coefficients and severity-weighted domain formula | **APPROVED PRODUCT DECISION** | Unit tests verify coefficients, pass-rate weighting and multi-rule observation counting. | Does not prove customer rounding, zero-eligible behavior, persisted inputs or overall publication. |
| D2 applicable/measurable normalization | **APPROVED PRODUCT DECISION** | A unit test excludes an explicitly unmeasurable domain. | D12 remains unresolved; no production overall score is authorized. |
| D3 six states and precedence | **APPROVED PRODUCT DECISION** | Unit test verifies highest-state selection. | No UI or persistence is implemented. |
| D4 `properPct` arithmetic | **APPROVED PRODUCT DECISION** | Unit test verifies `3/4 = 75%`. | Numeric floor, persistence, UI and production-authoring authorization remain blocked. |
| D5 exact strong-ID shortcut | **APPROVED PRODUCT DECISION** | Unit test passes. | Full production detector remains blocked. |
| D5 exact email plus exact phone shortcut | **APPROVED PRODUCT DECISION** | Unit test passes. | No email/phone normalization is implemented. |
| D5 standard confirmation (`>=0.90` and two exact strong fields) | **APPROVED PRODUCT DECISION** | Unit test passes at `0.90`. | Strong-field definitions/spec identity remain gated. |
| D5 suspected interval `[0.70,0.90)` | **APPROVED PRODUCT DECISION** under the matrix | Boundary test at `0.70` passes and routes to review. | The contract's endpoint wording and the `>=0.90`/insufficient-fields edge remain blocked. |
| D5 first-eight normalized-name prefix | **APPROVED PRODUCT DECISION** | Unit test slices an already-normalized input. | Normalization itself is intentionally absent pending authoritative-spec identification. |
| D5 oversized blocks must not lose pairs | **APPROVED PRODUCT DECISION** | Synthetic fixed-chunk spike covers all pairs for 41, 81 and 101 records. | Only the proposed in-memory chunk matrix was tested; no CRM/API feasibility was proven. |
| D6 blank-value grouping exclusion | **APPROVED PRODUCT DECISION** | Unit test proves blank/whitespace/`None` values are excluded. | No record collector or plausibility rule is wired. |
| D7 literal minimized finding shape | **APPROVED PRODUCT DECISION** | Unit test verifies only record ID, module, state, rule/reason IDs and duplicate partner/confidence fields. | No persistence or export route exists; record-to-job linkage is unresolved. |
| D14 explicit-read-scope boundary | **APPROVED PRODUCT DECISION** | Unit/synthetic tests accept `.READ` and reject `.CREATE`. | This proves a local validator, not actual Zoho scopes, admin authorization or visibility. |
| TZ-1 genuine timestamp precedence and disclosed approximation | **APPROVED PRODUCT DECISION** | Tests verify genuine wins; `Modified_Time` produces `APPROXIMATION_DISCLOSED` and disclosure text. | Module source availability and permissions remain technically unverified. |
| D16 routing and combined-selection rescore | **APPROVED PRODUCT DECISION** | Tests verify suspected→review and one combined application/rescore. | No Fix UI/action execution is implemented. |
| D17 per-scan API counters | **APPROVED PRODUCT DECISION** | Unit test verifies a new scan starts failed count at zero. | No running screen or API-call integration is implemented. |

“Locally verified” means the pure Python behavior passed its test. It does not mean Zoho/Catalyst integration, production data handling, visibility, scalability or security has been verified.

## 4. Implemented only as backend/domain primitives

The following files are not connected to `main.py`, Flask routes, React, Zoho or Catalyst:

- `domain/scoring.py` — D2 arithmetic, D4 `properPct`, and an explicit D12 gate.
- `domain/states.py` — six-state enum and precedence.
- `domain/duplicates.py` — partial D5 classifier, prefix-key constructor from pre-normalized input, and D16 routing.
- `domain/privacy.py` — literal D7 tuple object and defensive key-name leakage scan.
- `domain/authorization.py` — syntactic explicit-read scope validator.
- `domain/time_policy.py` — timestamp selection/disclosure and local `zoneinfo` conversion.
- `domain/operations.py` — D6 grouping, D16 combined gain, and D17 counters.
- `domain/errors.py` — explicit product/technical boundary exceptions.

These primitives are **SAFE TO KEEP** as bounded work except for the specific D5 below-floor issue in Section 12, which must not be wired or relied on pending approval.

## 5. D4 decision boundary

### Approved formula

**APPROVED PRODUCT DECISION:** `properPct = 100 × proper_records_for_user / records_for_user`. It is a percent-clean coaching metric, not D2's quality score, and must be labeled distinctly.

**Independent use now:** The arithmetic primitive and fully specified unit tests may be retained and exercised independently. Production authoring, persistence and presentation may not proceed merely because the formula is approved.

### Numeric minimum-record floor

**REQUIRES PRODUCT APPROVAL:** The contract says the existing minimum-record floor applies but does not state its number. The current primitive deliberately applies no floor.

**Independent use now:** The floor cannot be implemented independently. `properPct` may be calculated in an isolated library/test, but a user score must not be surfaced in production until the floor and other dependencies are approved.

### Production-authoring contradiction

The contract says at line 205: “NO-GO for user-score and duplicate-detection rule authoring.” Line 207 says the scoring engine/user score and D5 policy are cleared and may drive architecture, rule-catalogue and golden-test work. D4 is also marked approved and fully resolved elsewhere.

The actual wording therefore resolves D4's formula but does not unambiguously lift the production-authoring NO-GO. The older register and reverse-engineered spec cannot override this contract-level authorization conflict.

**BLOCKED / REQUIRES PRODUCT APPROVAL:** Any additional production D4 authoring.

## 6. D5 decision boundary

### Approved duplicate policy

**APPROVED PRODUCT DECISION:**

- within-module only for v1;
- exact strong identifier confirms directly;
- exact email plus exact phone confirms directly;
- exact email plus fuzzy name is not a confirmation shortcut;
- otherwise confirmation requires confidence `>=0.90` and two exact strong-field agreements;
- the matrix authorizes `[0.70,0.90)` as suspected and D16 routes it to human review;
- blocks over 40 are split deterministically without missing comparisons;
- the normalized-name first-eight-character `|nm|` blocking key is kept/documented.

### Mechanics explicitly authoritative in the contract

The bullets above are authoritative. The contract also authorizes engineering to choose a deterministic no-loss splitting strategy. The fixed 40-record/cross-chunk matrix is an **IMPLEMENTATION DECISION**, not the only approved algorithm.

### Mechanics still unspecified or authority-gated

**REQUIRES PRODUCT APPROVAL:**

- which filename/version is the authoritative “spec §6.7” incorporated by the contract;
- the fuzzy string-similarity algorithm if the confirmed authoritative spec does not define it;
- the fallback state for confidence `>=0.90` with fewer than two exact strong-field agreements;
- the terminal outcome below confidence `0.70`, because the matrix does not separately classify it;
- any normalization, field, strong-field designation, weight, denominator, shortcut or blocking key absent from the contract and confirmed authoritative spec;
- whether production D5 detector/rule authoring is authorized despite the contract's line-205 NO-GO.

The reverse-engineered spec contains candidate normalization/weight mechanics, but neither the contract nor matrix pins that file/version as the authoritative existing spec. It cannot be imported silently.

### Technical verification still required

**TECHNICAL VERIFICATION REQUIRED:**

- exact CRM record re-fetch by ID and visibility consistency;
- stable/deterministic ordering;
- all within-/cross-chunk pair coverage under the selected execution plan;
- crash/retry/idempotency behavior;
- API credits, latency, memory and runtime for oversized blocks;
- proof that no raw, hashed or digested blocking key crosses storage, queue, log or trace boundaries.

The synthetic pair-count spike proves combinatorial coverage only. It does not prove CRM/API feasibility or production privacy.

## 7. D7 persistence boundary

### Authorized

**APPROVED PRODUCT DECISION:**

- rich working facts may exist in active browser-session memory and must be cleared at session end;
- any persisted/exported record finding is limited to record ID, module, state, rule/reason identifiers, and duplicate confidence/partner reference where applicable;
- persisted/exported names, labels, stages and source field values are forbidden;
- duplicate persistence/export is limited to pair reference, confidence and state;
- raw duplicate blocking-key values are forbidden;
- a minimized streaming record export is permitted by the matrix, although no route was created.

The current `MinimizedRecordFinding` is only an in-process type. It is not a Catalyst schema or persistence implementation.

### Blocked

**REQUIRES PRODUCT APPROVAL / BLOCKED:**

- whether rich backend-worker memory qualifies as the approved “active session” tier;
- record-to-scan/batch linkage;
- connection/job operational metadata and its exact fields/purposes;
- OAuth refresh-token persistence under D7's literal boundary;
- any persisted result or summary beyond the literal approved tuple;
- durable generated export files;
- TTL, deletion triggers and audit-log retention;
- production connection-deletion data semantics.

No aggregate rows, opaque user tokens, fingerprints, user/time aggregates or retention defaults are proposed in this package. They remain unimplemented and blocked.

## 8. D12 verification

Repository search found no Configuration Hygiene evaluator, domain inclusion/exclusion list, weight, slice or persistence behavior in implementation code.

`scoring.py:81–88` requires an explicit `d12_resolved_and_revalidated=True` assertion before the generic overall-normalization function runs. No production caller exists. The default/current path therefore does not silently exclude Configuration Hygiene.

`test_authorized_domain.py:74–89` invokes the function with `True` only to exercise D2 normalization with an explicitly unmeasurable domain. That test does **not** prove D12 resolution, Configuration Hygiene behavior or production overall-score authorization.

**REQUIRES PRODUCT APPROVAL / BLOCKED:** D12 definition, scope, weight/inclusion treatment and D2 revalidation. The overall function must not be wired to production before those approvals.

## 9. D14 boundary

### D14-POLICY

**APPROVED PRODUCT DECISION:** An explicit CRM administrator authorizes an organization-specific integration; requested access is disclosed; explicit read scopes are used; operator-personal visibility is not the intended model; prior user-scoped comparisons are not directly comparable.

The current implementation only validates scope-name suffixes. It does not implement or prove the connection policy.

### D14-EVIDENCE

**TECHNICAL VERIFICATION REQUIRED:** D14-EVIDENCE is defined but unexecuted. The local tests do not prove administrator status, granted scopes, module completeness or org-wide visibility.

No code or report may claim guaranteed org-wide visibility. Production visibility levels, incomplete-visibility detection and warnings remain blocked until evidence exists; D10 separately controls their UI presentation.

## 10. TZ-1 verification

`time_policy.py:28–41` selects a genuine timestamp first. It uses `Modified_Time` only when the caller supplies no genuine timestamp, and then always returns `APPROXIMATION_DISCLOSED` plus the explicit disclosure text. If neither timestamp is available, it returns `UNAVAILABLE`.

No caller, route or module mapping exists. Therefore there is currently no silent production substitution.

**TECHNICAL VERIFICATION REQUIRED:** Before wiring the primitive, engineering must prove per module that a genuine close/audit source is unavailable, verify Timeline/Audit/field permissions, and confirm `Modified_Time` availability. A missing value caused by an API/permission failure must not be treated as proof that no genuine source exists.

The exact UI placement/copy treatment of the required disclosure remains **REQUIRES PRODUCT APPROVAL** under D10; the requirement to disclose is already approved.

## 11. What the 25 tests and synthetic runner prove

### Tests prove

- the current pure functions produce the asserted D2/D3/D4/D5/D6/D7/D14/TZ-1/D16/D17 results for their fixtures;
- explicit boundary exceptions occur for zero-eligible D2, unresolved D12 and the D5 high-confidence/insufficient-fields edge;
- non-read scope strings are rejected locally;
- the literal D7 export projection omits scan/batch IDs and obvious forbidden keys;
- `Modified_Time` receives approximation status/disclosure in the tested path.

### Tests do not prove

- that every test expectation is product-authorized; the below-`0.70` D5 expectation is specifically questioned;
- production D4/D5 authoring authorization;
- the D4 numeric floor, coaching thresholds, D5 fuzzy algorithm or authoritative spec identity;
- D12 behavior or permission to publish an overall score;
- actual storage/log/export leakage resistance; the detector checks key names and can miss values under unexpected keys;
- Zoho OAuth/admin/visibility behavior, real scopes or API completeness;
- Catalyst authentication, transaction, job, secret or ephemeral-storage behavior;
- production performance, concurrency, rate limits, crash behavior or data residency.

### Synthetic runner proves

- the proposed fixed-chunk algorithm covered all mathematical pairs for 41, 81 and 101 synthetic records;
- a temporary SQLite checkpoint example resumed two batches without duplicate rows after its non-null uniqueness correction;
- local `zoneinfo` represented one New York DST overlap and Asia/Kolkata offset as expected;
- the local read-scope and key-name leakage guards fired for their fixtures;
- repeated Decimal calculation returned the same value.

### Synthetic runner does not prove

- Catalyst schema/transaction/lease/idempotency semantics—the temporary SQLite tables are not a proposed production schema;
- Zoho record ordering, re-fetch, Bulk Read/COQL paging, expiry, visibility or cost;
- all timezones, DST/fiscal boundaries, Zoho timezone identifiers or module close sources;
- complete privacy controls or absence of blocking-key derivatives;
- an approved customer rounding/display rule for the long Decimal result.

## 12. Possible implementation boundary crossing

| File/location | Issue | Classification | Required action |
|---|---|---|---|
| `functions/ai_data_analytics_function/domain/duplicates.py:46` | `classify_pair` returns `None` for confidence below `0.70`, selecting a terminal non-duplicate outcome not separately classified by the matrix. | **REQUIRES PRODUCT APPROVAL / BLOCKED** | Do not wire or rely on this branch. No automatic fix was made. |
| `tests/test_authorized_domain.py:178–179` | The test `test_below_floor_is_not_a_duplicate` locks the same outcome as expected behavior. | **REQUIRES PRODUCT APPROVAL / BLOCKED** | Treat the test as documenting the current implementation, not as authorization. Do not use it as a golden product fixture pending approval. |

No other accidental boundary crossing was found. In particular, the synthetic SQLite tables are confined to a temporary technical spike and are expressly not production schema.

## 13. Exact proposed approval questions

These questions intentionally select no answer.

### Immediate D4/D5 authorization questions

1. **D4 production authorization:** “Does the approved D4 `properPct` decision authorize production user-score rule authoring now, subject to separately resolving the numeric floor, D7 persistence and D10 presentation, or does the contract's Section 5 NO-GO remain in force? If it remains in force, what explicit condition releases it?”
2. **D4 floor:** “What exact numeric minimum-record floor must gate D4 `properPct` before a user score may be surfaced?”
3. **D5 production authorization:** “Does the approved D5 policy authorize production duplicate-detector rule authoring now, subject to separately resolving unspecified mechanics and technical verification, or does the contract's Section 5 NO-GO remain in force? If it remains in force, what explicit condition releases it?”
4. **D5 authoritative spec:** “Which exact filename and version is the authoritative existing specification referenced as `spec §6.7` by D5?”
5. **D5 high-confidence edge:** “What terminal outcome applies when duplicate confidence is `>=0.90` but fewer than two exact strong fields agree?”
6. **D5 below-floor edge:** “What terminal outcome applies when duplicate confidence is below `0.70` and no direct exact-match confirmation shortcut applies?”
7. **D5 fuzzy similarity:** “If the confirmed authoritative specification does not define the fuzzy string-similarity algorithm, which exact algorithm and normalization parameters are approved?”

### Other required product decisions

8. **D2 zero eligible:** “How must a rule with zero eligible observations affect its domain calculation, applicability status and any displayed result?”
9. **D7 server memory:** “Does D7's approved active-session memory tier include transient backend-worker memory; if so, what exact lifecycle/security boundary defines the end of that session?”
10. **D7 persistence boundary:** “Does D7 permit persistence of any connection/job operational metadata or record-to-job linkage outside the literal minimized record tuple; if so, what exact fields, purposes and access boundaries are approved?”
11. **D7 credentials:** “Under D7, is encrypted organization OAuth credential persistence authorized; if so, what exact data class and deletion/retention treatment applies?”
12. **D7 duration/deletion:** “What TTL, deletion triggers and audit-log retention periods apply to each approved persisted data class?”
13. **D7 exports:** “May generated minimized export files be stored durably; if so, for how long and under what deletion trigger?”
14. **D8:** “For v1, is threshold configuration editable, read-only or absent from the UI?”
15. **D9:** “For v1, must setup show a real records-in-range cost/runtime estimate, a clearly labeled approximation, or no estimate?”
16. **D10:** “What exact behavior is approved for each unresolved Modules, Users, Trend, Records and Fix screen state, including incomplete/partial results and required approximation disclosures?”
17. **D12:** “What is the approved definition, scope and score treatment of Configuration Hygiene, and how must D2 be revalidated after that decision?”
18. **D15-KNOB:** “Must `maxExamplesPerRule` be implemented as a product setting or removed?”
19. **Prior-period extraction:** “Which approved scan scopes, if any, require automatic prior-period extraction?”
20. **Operator cancellation:** “Is an operator-facing scan cancellation behavior approved; if so, what result/data state must cancellation produce?”

No question in this package proposes aggregate rows, opaque user tokens, fingerprints or retention defaults. Those remain blocked unless product independently authorizes an exact replacement contract.

## 14. Technical/platform verification queue

### D14-EVIDENCE

1. Visible-record count versus a known/true module total signal.
2. Requested-versus-granted OAuth scope introspection.
3. Administrator-profile proof.
4. Effects of profiles, private sharing, explicit sharing, role hierarchy and territories.
5. Visibility consistency across standard records, COQL, Bulk Read and count APIs.
6. Inaccessible module/field and partial-record signals.
7. Evidence-backed assurance levels, expiry/retest behavior and non-guarantee wording.
8. Results by API version, CRM edition, data center and sharing configuration.

### Zoho feasibility

1. Exact read-only scopes for Organization, Users, metadata, modules, COQL, Bulk Read, Timeline and Audit APIs; flag any non-read requirement without adding it.
2. Bulk Read/COQL date criteria, limits, paging, token/result expiry, callbacks, credits, latency, stable ordering and module/field coverage.
3. Organization/environment/data-center binding, refresh, revocation and reauthorization.
4. Exact ID re-fetch and visibility consistency for duplicate work.
5. Genuine close/audit sources, permissions and `Modified_Time` availability per module.
6. Organization timezone values and IANA mappings across supported editions/data centers.

### Catalyst feasibility

1. Data Store transaction/conditional-update behavior for leases, compare-and-set, staging and idempotency.
2. Job Scheduling delivery, timeout, retry and duplicate execution.
3. Callback authenticity/correlation behavior.
4. Temporary worker storage lifecycle/clearing or streaming requirement.
5. Application authentication, CSRF, tenant/org isolation and server-only table access.
6. Secret storage, authenticated encryption and key rotation using synthetic credentials.
7. Crash/retry proof for every proposed batch transition.
8. Count/checksum/successor-page completeness using synthetic data until D7 permits persistence.
9. Duplicate re-read performance and no blocking-key derivative leakage.

## 15. Decision handoff

### A. SAFE TO KEEP

- The isolated domain primitives for D2, D3, D4 arithmetic, approved D5 branches, D6, literal D7 projection, D14 read-scope guard, TZ-1 disclosure, D16 and D17.
- The explicit `ProductApprovalRequired`/`TechnicalVerificationRequired` stops.
- The 25 tests as engineering regression tests, except that the below-`0.70` D5 test is not an approved golden product fixture.
- The synthetic verification runner as non-production evidence tooling only.

### B. REQUIRES PRODUCT APPROVAL

- All questions in Section 13, especially D4/D5 production authorization, D4 floor, D5 authoritative mechanics/edge states, D7 boundaries, D8/D9/D10/D12/D15-KNOB and zero-eligible behavior.
- The identified D5 below-`0.70` implementation/test outcome.

### C. REQUIRES TECHNICAL VERIFICATION

- All D14-EVIDENCE, Zoho and Catalyst tasks in Section 14.
- D5 execution feasibility and privacy, TZ/module sources, timezone mappings and deterministic numeric representation.

### D. MUST NOT BE IMPLEMENTED YET

- Production D4/D5 rule wiring.
- Any D12 evaluator, exclusion, weight or production overall score.
- React/UI behavior, production routes, OAuth flow, collectors or Catalyst schema.
- Production persistence, operational metadata, record-job linkage, credentials, aggregates, user/time summaries, opaque tokens, fingerprints, durable exports or retention/deletion defaults.
- Non-read OAuth scopes, guaranteed org-wide visibility, silent timezone fallback or silent `Modified_Time` substitution.
- Any unapproved configuration default or inferred answer to Sections 12–13.
