# Catalyst Architecture Compliance Review

**Reviewed documents:** `approved-product-contract.md` (authoritative product contract) and `catalyst-architecture.md` (non-authoritative implementation proposal)  
**Review date:** 17 August 2026  
**Implementation status:** **STOP — compliance report only; no implementation code authorized**

## 1. Executive verdict

The architecture is broadly aligned with the approved direction for durable extraction, explicit administrator authorization, visibility caution, timezone handling, minimized record findings, scoring, state precedence and within-module duplicate matching. It correctly states that D14-EVIDENCE is unverified and explicitly identifies its aggregate-contribution design as requiring D7 confirmation.

It is **not yet compliant enough to serve as a production implementation specification**. Three direct conflicts must be corrected or resolved:

1. It silently decides D12's effect on the overall score by excluding Configuration Hygiene from the denominator.
2. It allows a nominal OAuth `CREATE` scope for export-job initiation despite D14-POLICY's approved requirement for explicit read scopes.
3. It permits a close-time rule to become unavailable and not run, whereas TZ-1 requires a disclosed `Modified_Time` approximation when no genuine close/audit timestamp is available.

There are also material D7 gates. Persisted aggregate contributions, opaque user dimension tokens, operational metadata, final aggregate tables and richer transient server-side processing are architecture interpretations—not approved extensions of the D7 tuple. The aggregate-contribution proposal is explicitly **not approved** and must remain blocked. TTL, deletion trigger and audit-log retention are unresolved.

The architecture must not be used to implement D8, D9, D10, D12 or D15-KNOB. D14-EVIDENCE has not passed. The contract itself also contains a go/no-go wording conflict: it says both “NO-GO for user-score and duplicate-detection rule authoring” and that D4/D5 are fully specified and cleared. The conservative interpretation is no production rule implementation until the contract is clarified or re-issued.

## 2. Compliance classification

| Area | Status | Summary |
|---|---|---|
| Contract authority | **Compliant** | Architecture says it is a proposal and distinguishes product decisions from engineering choices. |
| D2 scoring | **Mostly compliant; corrections required** | Formula and coefficients match. Zero-eligible handling is an unlabeled implementation choice. D12 exclusion is a direct unresolved-decision violation. |
| D4 user scoring | **Formula compliant; persistence blocked** | Percent-proper and distinct labeling match. Durable user dimensions depend on the unapproved D7 aggregate proposal. |
| D3 state precedence | **Compliant** | Ordering matches the contract. Pair tie-breaking is an engineering choice that needs labeling. |
| D5 duplicates | **Policy compliant; design incomplete/gated** | Scope and confirmation policy match. Split design is engineering, exact scoring/normalization is not fully restated, and the privacy-compliant re-read design needs technical proof. |
| D7 retention/privacy | **Not production-compliant** | Minimal record tuple is respected in intent, but several additional persisted classes rely on unapproved interpretations. Aggregate contributions are a hard gate. |
| D13 extraction | **Compliant direction; technical gates open** | Durable batches, checkpoints and persisted results match. Provider capability, completion evidence and atomicity remain unverified. |
| D14-POLICY | **One direct conflict** | Admin-authorized organization connection matches. Allowing a `CREATE` scope conflicts with approved read-scope wording. |
| D14-EVIDENCE | **Correctly unverified** | Architecture does not assume it passed. All evidence work remains a production gate. |
| TZ-1 | **One direct conflict** | Org timezone usage matches. `UNAVAILABLE` close rules can contradict the required disclosed `Modified_Time` approximation. |
| D6/D16/D17 fixes | **Partial** | Blank-phone and API-stat fixes are covered; D16 combined rescoring of selected fixes is omitted. |
| D8/D9/D10/D12/D15-KNOB | **D12 violation; others guarded** | D12 is silently resolved for scoring. D8/D9/D10/D15-KNOB are mostly left unresolved, with noted D10 guardrails below. |

## 3. Direct contradictions of approved decisions

### C-01 — D12 is silently excluded from the published score

**Severity:** Critical  
**Contract:** D12 remains unresolved and D2 must be revalidated after D12 is settled (`approved-product-contract.md` lines 38, 185–197, 210).  
**Architecture:** “D12's unresolved domain is not evaluated or included in a published denominator” (`catalyst-architecture.md` line 263), repeated in the scoring section (`line 509`).

Excluding Configuration Hygiene is itself one of the possible product outcomes. It changes the domain basis and published overall score, so it is not a neutral engineering deferral.

**Required correction:** The scoring engine may be prototyped against D2 for approved domains, but no production overall score whose denominator depends on D12 may be published until D12 is resolved and D2 is revalidated. The architecture must say “overall-score publication blocked by D12,” not “D12 excluded.”

### C-02 — A `CREATE` OAuth scope is allowed despite the read-scope policy

**Severity:** Critical  
**Contract:** D14-POLICY requires explicit read scopes for the integration identity (`approved-product-contract.md` lines 123–129).  
**Architecture:** It permits a scope whose API operation is named `CREATE` to start an asynchronous export (`catalyst-architecture.md` line 154).

The fact that the API operation creates only an export job may make the scope technically necessary, but the contract did not approve a semantic exception to “read scopes.” Disclosure and allowlisting do not convert it into an approved product decision.

**Required resolution:** Verify whether the close/audit and extraction design can use read-only endpoints/scopes. If a nominal `CREATE` scope is technically unavoidable, obtain explicit product/security approval and update the contract before production authorization work. Until then, that capability is blocked.

### C-03 — Close-time rules may be disabled instead of using the required disclosed approximation

**Severity:** High  
**Contract:** Where a genuine close/audit timestamp is unavailable, the rule catalogue must document `Modified_Time` as an explicit, disclosed approximation (`approved-product-contract.md` lines 153–158).  
**Architecture:** It defines `UNAVAILABLE` and says a close-dependent time rule does not run in that state (`catalyst-architecture.md` line 241).

This can remove a rule that the approved contract expects to run using a disclosed approximation. `UNAVAILABLE` is compliant only if neither a genuine event nor `Modified_Time` exists or can be retrieved; the architecture does not state that restriction.

**Required correction:** Use `APPROXIMATION_DISCLOSED` with `Modified_Time` whenever no genuine event exists but `Modified_Time` is available. Reserve `UNAVAILABLE` for a technically verified absence/inaccessibility of both sources, and report the rule as unmeasurable rather than silently omitting it.

## 4. Silent resolution of unresolved product decisions

### U-01 — D12 denominator behavior

This is the direct violation in C-01. It must be removed before implementation.

### U-02 — D10 partial-result presentation

**Architecture:** It proposes showing “diagnostic partial counts” as an implementation decision (`catalyst-architecture.md` line 212) and requires visibility status to be displayed (`lines 672, 682`).

Backend visibility state and suppression of an authoritative score are architecture concerns under D14. The exact screen presentation of partial counts is a screen behavior and therefore touches unresolved D10. The architecture correctly says selling/labeling a partial score needs a product decision, but it still proposes a presentation outcome.

**Guardrail:** Implement only backend status/evidence contracts. Do not implement how partial counts, warnings, banners or drill-downs appear until D10 is approved, except for a minimal safety block that prevents an authoritative result from being represented as complete.

### U-03 — D10 time/user result capability must not become approved UI behavior

The architecture proposes persisted time-bucket aggregates and three user attribution dimensions (`catalyst-architecture.md` lines 384–399, 523–534). These are already blocked by D7, but their existence must also not be used to infer approval of missing Users/Trend screen behavior under D10.

**Guardrail:** Treat these only as proposed backend capabilities. No Trend, cohort, user filter, team/manager rollup or user-export behavior is authorized by this architecture.

### U-04 — D8 remains unresolved despite a versioned rule configuration

The architecture says the backend accepts versioned rule configuration while declining to choose an editable/read-only UI (`catalyst-architecture.md` line 34). This is acceptable only if “versioned” means release-managed rule configuration, not operator-configurable thresholds.

**Guardrail:** Do not expose threshold mutation endpoints or UI, and do not infer client-specific threshold editing, until D8 is approved.

### U-05 — D9, D15-KNOB

No silent resolution was found. Recording actual job usage does not decide D9's pre-run estimate. The architecture neither implements nor removes `maxExamplesPerRule`. Preserve that boundary.

## 5. Implementation decisions presented too close to product approval

These are not necessarily wrong, but their status must be corrected before the architecture becomes an implementation specification.

| ID | Architecture statement | Compliance issue | Required treatment |
|---|---|---|---|
| M-01 | D13 is labeled as approving “final results are computed from persisted, verified batch results” (`line 458`). | The contract approves persisted batch results for resume/audit (`contract` lines 108–114); the final-aggregation source is a sound architecture requirement but not explicitly product-approved there. | Relabel as an **implementation decision required to satisfy D13**, not as quoted approved product behavior. |
| M-02 | `scan_id` and `batch_id` are included inside a block labeled “APPROVED PRODUCT DECISION — D7” (`lines 345–356`). | The approved minimal tuple does not list these operational envelope fields (`contract` line 97). | Keep only under the separately labeled operational-metadata interpretation and gate that interpretation. |
| M-03 | Zero-eligible rules are excluded from domain calculation (`line 502`). | Mathematically necessary, but the contract does not state the zero-eligible rule behavior. | Label as an implementation decision and add a golden case; obtain product confirmation if it changes displayed applicability. |
| M-04 | Unknown timezone blocks time-dependent rules (`line 222`). | Safe behavior, but TZ-1 does not specify the failure policy. | Label explicitly as implementation fail-closed behavior and test it. Do not call it product-approved. |
| M-05 | Fixed chunks of at most 40 and full cross-chunk comparisons (`lines 437–444`). | D5 approves deterministic splitting but leaves the algorithm to engineering. | Label the whole subsection as an implementation decision; validate no edge misses. |
| M-06 | Best duplicate state plus confidence/partner-ID tie-breaking (`line 448`). | D3 defines terminal-state precedence, but partner tie-breaking is not product-approved. | Label as deterministic engineering behavior; ensure all pairs remain available so tie-breaking cannot hide policy-relevant evidence. |
| M-07 | Null/malformed timestamps make the scan incomplete and non-publishable (`line 298`). | The contract explicitly leaves null/malformed handling to architecture, and the document labels it correctly. | Retain as implementation choice, but do not later describe it as product policy. |
| M-08 | Incomplete module/visibility prevents authoritative score publication (`lines 212, 284, 556, 682`). | A defensible D13/D14 fail-closed design, but not stated as an approved product decision. | Keep labeled as implementation safety behavior; presentation remains D10-blocked. |
| M-09 | Prior-period batches are mandatory in the completion fence (`lines 253, 462`). | The contract does not approve automatic prior-period extraction here, and Trend behavior is within unresolved D10. | Make prior batches conditional on an independently approved scan scope; do not require them solely because the architecture says so. |
| M-10 | Explicit connection-deletion/test-data purge may be supported (`line 405`). | D7 deletion triggers remain unresolved. | A technical delete primitive may exist, but when it runs and what it preserves must remain blocked by retention policy. |

## 6. D7 data-retention and privacy review

### 6.1 Compliant elements

- Raw CRM records, Bulk Read files, names, labels, stages, source timestamps, signatures, blocking keys and audit values are prohibited from persistence and export (`catalyst-architecture.md` lines 360–374).
- Persisted reason text is value-free and keyed by controlled reason IDs (`lines 345–358`).
- Duplicate persistence is limited to pair reference, state and confidence; raw blocking keys are excluded (`lines 411–435`).
- Durable generated export storage is excluded while retention duration is unresolved (`lines 598–604`).
- The architecture explicitly flags aggregate contributions as unapproved (`lines 380–399, 620, 662, 707`).

### 6.2 Hard gate — aggregate contributions and opaque user dimensions

**Status:** Not approved.  
**Architecture:** `AggregateContribution` contains dimension type/key, time bucket, rule/domain/severity, eligible/offending and state counts; user keys are scan-scoped tokens derived from Zoho user IDs (`lines 384–399`).

This exceeds D7's approved tuple. Hashing/tokenizing a user ID does not automatically remove privacy or re-identification concerns, especially when the mapping is rehydrated from Zoho. The proposal must not be implemented until the contract explicitly permits the aggregate schema, purposes, export rules and retention.

Without approval, durable D4 user scoring and durable time aggregation are blocked. The architecture correctly states this consequence; implementation must preserve it.

### 6.3 Operational metadata interpretation is also a gate

The architecture persists CRM org ID, timezone, authorizing user ID, encrypted refresh tokens, field-plan identifiers, query hashes, provider job IDs, counts, checksums, errors and completion manifests (`lines 140, 249–261, 310–321, 376–378, 610–625`). Much of this is necessary for D13/D14/TZ-1, but D7 literally says anything persisted must be reduced to the minimal tuple.

The architecture labels this an implementation interpretation, which is good, but the interpretation still needs explicit privacy/security acceptance. At minimum, classify each field as connection secret, operational metadata, CRM metadata or record-derived data; define purpose, access, retention and deletion behavior; and confirm that the D7 tuple restriction was intended for record-level findings rather than all system metadata.

### 6.4 Final aggregate persistence

`ScanAggregate` stores scores/counts outside the literal record tuple (`lines 527–538, 623`). Even without user identifiers, persisted aggregate results are additional data. Their allowance must be confirmed alongside Section 9.4 rather than assumed merely because they contain no raw values.

### 6.5 Transient worker memory interpretation

D7 explicitly allows rich “in-session” working facts in memory (`approved-product-contract.md` line 96). The architecture extends this to backend worker memory during an active operation (`catalyst-architecture.md` line 374). This is necessary for server-side evaluation but is still an interpretation of “session.” It needs a security acceptance defining maximum lifetime, crash behavior, swap/core-dump/log controls and proof that temporary files are not durable.

### 6.6 Duplicate child-task privacy risk

The proposed `block_digest_in_memory_context` (`line 444`) is ambiguous. If a digest or child-task payload crosses a queue/persistence boundary, it may be a persisted derivative of an email/phone/statutory-ID blocking key and is not approved. Child work must either remain inside one transient worker context or re-read/reconstruct data without persisting the digest. This must be verified by design and tests.

### 6.7 Retention duration and deletion remain open

TTL, deletion trigger and audit-log duration are explicitly unresolved in both documents (`contract` line 99; `architecture` lines 401–405, 604, 664). No production persistence can be enabled until these are approved. Encryption does not substitute for a retention policy.

## 7. Exact behavior review

### 7.1 Scoring (D2)

**Matches:** Severity coefficients, per-rule pass-rate weighting, applicable/measurable domain normalization, exclusion of unavailable PII/Access and Automation Health, and rule-observation counting (`architecture` lines 482–511; `contract` lines 29–38).

**Does not exactly match / incomplete:**

- D12 is excluded instead of remaining unresolved (C-01).
- Zero-eligible rule handling is added without product labeling (M-03).
- Rounding/precision and deterministic numerical representation are unspecified. They must be engineering-defined and golden-tested without changing formula semantics.
- D16's requirement to compute selected fix gains from a combined rescored selection is absent (`contract` line 180). The architecture mentions routing only (`architecture` lines 421, 452, 680). No action-gain implementation is compliant until combined rescoring is designed and tested; independent gain summation is forbidden.

### 7.2 User scoring (D4)

**Matches:** `proper / records`, minimum-floor gating, coaching basis and distinct “Percent clean” labeling (`architecture` lines 513–523; `contract` lines 42–53).

**Gates:** Persistent user aggregation is not permitted by D7 yet. The architecture must not implement opaque user tokens or user aggregate export before approval. D8 still controls whether the floor is editable in UI.

### 7.3 State precedence (D3)

**Matches:** `proper < incomplete < inaccurate < suspicious < suspected_duplicate < confirmed_duplicate` (`architecture` lines 472–480; `contract` line 174).

**Engineering-only:** Pair tie-breaking and how all underlying pair evidence is exposed are not product-approved. Keep all rule IDs/pairs so the engineering tie-break cannot erase facts.

### 7.4 Duplicate behavior (D5 and D16)

**Matches:** Within-module v1 scope; exact strong-ID shortcut; exact email+exact phone shortcut; removal of email+fuzzy-name shortcut; standard 0.90/two-strong-field confirmation; suspected review; documented eight-character name block; deterministic evaluation of oversized blocks (`architecture` lines 409–444; `contract` lines 57–84).

**Incomplete/gated:**

- The architecture does not restate the authoritative signature normalization, field weights, similarity formula or exact definition of strong fields referenced by the contract's “standard rule.” Those must be imported unchanged from the authoritative rule catalogue/spec and covered by golden tests; the batch architecture must not invent replacements.
- Exact re-fetch-by-batch-ID capability, API limits, stable ordering and the O(batch²) comparison cost are unverified.
- The proposed block splitting is engineering design, not product approval.
- D16 combined fix-gain rescoring is missing.
- The contract has stale wording at line 180 saying D5 is “still-open,” although D5 is approved above. Use approved D5 Section 1 and request a contract cleanup; do not reopen D5.

### 7.5 Timezone and close/audit behavior (TZ-1)

**Matches:** CRM org timezone retrieval at scan planning, immutable scan snapshot, org-timezone bucketing, DST-aware conversion, and genuine close/audit event preference (`architecture` lines 216–243; `contract` lines 148–158).

**Conflict:** `UNAVAILABLE` must not bypass the required disclosed `Modified_Time` approximation when that field is available (C-03).

**Verification required:** Timezone values across supported DCs/editions; IANA mapping; fiscal boundaries; DST gaps/overlaps; module-specific genuine close sources; Timeline/Audit permissions; and approximation disclosure.

### 7.6 Extraction and completion (D13)

**Matches:** Durable server jobs, date-bounded planning, persisted batch results, checkpoint/resume, removal of the 25-old-record heuristic and auditable completeness (`architecture` lines 245–339, 454–470, 540–596; `contract` lines 103–114).

**Engineering choices needing verification:** Bulk Read versus COQL selection; null timestamp fail-closed behavior; exact page-token resume; callback-as-hint model; lease/compare-and-set semantics; staging atomicity; count/checksum rules; schema drift; and exact re-fetch for duplicate comparison.

**Guardrail:** Final aggregation from persisted results is required by the proposed design and the prior architecture instruction, but should be labeled implementation architecture rather than an additional approved product decision.

### 7.7 Authorization and visibility (D14)

**Matches:** Explicit CRM-admin action, organization-specific OAuth, separate server-side connection, disclosure, no signed-in widget identity, comparability warning and no full-visibility assumption (`architecture` lines 119–214; `contract` lines 118–144).

**Conflict:** Nominal `CREATE` scope exception (C-02).

**Unverified:** Admin status signal, granted-scope introspection, sharing/territory/role effects, count comparison signal and endpoint consistency. `ACTIVE_VISIBILITY_TESTED` must not be reachable in production until D14-EVIDENCE results define its exact criteria.

## 8. Verification gates before production implementation

No production implementation or production data processing may proceed past the relevant boundary until these gates are closed.

### 8.1 Product/contract gates

1. **D14-EVIDENCE:** Execute the approved plan; do not infer an outcome.
2. **D7 aggregate schema:** Explicitly approve or reject aggregate contributions, time buckets, scan-scoped user tokens and `ScanAggregate` persistence.
3. **D7 operational metadata:** Confirm the record-tuple rule's boundary and approve the exact operational/connection metadata classes.
4. **D7 transient worker interpretation:** Confirm rich backend memory is permitted under “in-session,” with lifecycle controls.
5. **D7 retention:** Approve TTL, deletion triggers and audit-log retention.
6. **D12:** Resolve Configuration Hygiene and revalidate D2 before publishing overall scores.
7. **OAuth export scope:** Approve any technically necessary non-READ scope or redesign to remain read-only.
8. **TZ-1 fallback:** Correct the `UNAVAILABLE` behavior and approve module-specific approximation disclosures.
9. **Contract go/no-go ambiguity:** Reconcile `approved-product-contract.md` line 205 (NO-GO for D4/D5 authoring) with lines 164 and 207 (fully resolved/cleared). Use the conservative NO-GO until clarified.
10. **D8, D9, D10, D15-KNOB:** Resolve separately before implementing their affected UI/rules. No inference is allowed.

### 8.2 Authorization/visibility technical gates

11. Prove how CRM administrator status is detected for the authorizing identity.
12. Determine whether requested/granted scopes are introspectable and how missing grants are detected.
13. Test record sharing, private modules, roles, profiles, territories and hierarchy in a realistic sandbox.
14. Determine whether Bulk Read, COQL, standard record and count APIs apply identical visibility.
15. Define the evidence levels and expiry/retest policy for `visibility_assurance`; never name a level “full” without proof.
16. Verify token revocation, reauthorization, multi-DC endpoints and org/environment binding.

### 8.3 Extraction/resume technical gates

17. Verify Bulk Read and COQL criteria, limits, credits, latency, result lifetime, page-token expiry and module/field coverage for target editions/DCs.
18. Prove Data Store transaction/conditional-update semantics needed for leases, staging promotion and idempotency.
19. Prove Job Scheduling retry/delivery semantics and callback authenticity assumptions.
20. Demonstrate crash recovery at every batch state with no lost or double-counted facts.
21. Validate provider/parsed/unique/persisted count reconciliation and successor-page completeness.
22. Validate null/malformed timestamp detection and fail-closed behavior.
23. Verify worker temporary storage is non-persistent and cleared; otherwise require streaming.

### 8.4 Duplicate technical gates

24. Import and freeze the exact signature normalization, weights, similarity and strong-field definitions; do not infer them from the architecture.
25. Prove exact record re-fetch from persisted batch ID membership.
26. Load-test the triangular batch-pair plan and quantify API credits/runtime.
27. Prove all within- and cross-chunk candidate pairs are evaluated for blocks above 40.
28. Prove no raw/digested blocking key crosses a persistence, queue, log or trace boundary.
29. Run every D5 golden case plus boundary cases at 0.70 and 0.90.
30. Verify suspected/confirmed action routing and D16 combined rescoring.

### 8.5 Time/scoring/privacy/security gates

31. Verify org timezone retrieval and IANA conversion across DST and supported DCs.
32. Verify genuine close/audit sources per v1 module and disclosed `Modified_Time` fallbacks.
33. Run D2/D3/D4 golden fixtures, including zero-eligible rules, multi-rule double contribution, unavailable domains, minimum floor and terminal-state precedence.
34. Verify encryption/key rotation and identify the approved Catalyst secret/key mechanism.
35. Run automated storage/log/export leakage tests for every forbidden D7 field class.
36. Approve and test purge behavior only after retention triggers/durations are decided.

## 9. Required architecture changes before review sign-off

No implementation should begin from the current architecture text. After this report is reviewed, the architecture should be revised to:

1. Remove the D12 exclusion decision and mark production overall-score publication blocked.
2. Remove or contract-gate the nominal `CREATE` scope exception.
3. Make `Modified_Time` the disclosed fallback where TZ-1 requires it; restrict `UNAVAILABLE` appropriately.
4. Relabel final aggregation, zero-eligible behavior, chunking and duplicate tie-breaking as implementation decisions.
5. Move `scan_id`/`batch_id`, operational metadata and `ScanAggregate` out of the block labeled as approved D7 tuple; mark them as privacy gates.
6. Keep `AggregateContribution` and opaque user/time dimensions explicitly unapproved and non-implementable.
7. Add the missing D16 combined-rescoring requirement.
8. Make prior-period extraction conditional rather than architecture-mandatory unless separately approved.
9. Ensure partial-result presentation and all missing screen behavior remain D10-blocked.
10. Add the contract's internal go/no-go ambiguity as an explicit stop condition.

## 10. Final compliance decision

**Decision: NOT APPROVED FOR PRODUCTION IMPLEMENTATION.**

Permitted next work is limited to reviewing this compliance report, correcting the architecture, and executing non-production technical verification spikes that do not implement unresolved product behavior or process production CRM data. D14-EVIDENCE remains unpassed. The D7 aggregate-contribution proposal remains unapproved. D8, D9, D10, D12 and D15-KNOB remain unresolved and must not be inferred or implemented.
