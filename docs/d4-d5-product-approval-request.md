# Bounded Product Approval Request — D4, D5, TZ-1 and D7

**Purpose:** Request only the smallest missing Product decisions. This document does not authorize implementation and does not amend the product contract.  
**Product authority:** `approved-product-contract.md`  
**Execution boundary:** `implementation-authorization-matrix.md`  
**Date:** 24 August 2026

## Status key

- **PRODUCT DECISION REQUIRED** — Product must choose and approve contract wording.
- **TECHNICAL VERIFICATION REQUIRED** — no Product choice is requested; engineering evidence is outstanding.
- **ALREADY AUTHORIZED** — the contract already fixes the behavior; no new approval is requested.

## D5-1 — Outcome below confidence 0.70

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D5.1 states: “Scores of 0.70–0.90 remain `suspected_duplicate` and route to human review.” It defines direct exact-match confirmation and the `>=0.90` plus two-exact-strong-fields confirmation rule. It does not explicitly assign an outcome below `0.70`.

### Current implementation behavior

`domain/duplicates.py:46` returns `None` below `0.70`. `tests/test_authorized_domain.py:178–179` currently expects this result.

### Why the behavior is not authorized

Returning `None` selects a “no duplicate finding” outcome that is not stated by the contract or separately authorized by the matrix. A passing test documents the implementation but does not turn it into Product policy.

### Smallest possible decision Product must make

Assign exactly one terminal outcome to a pair with confidence below `0.70` when neither direct exact-match confirmation shortcut applies.

### Proposed options

- **Option A — No duplicate finding:** The pair produces neither `suspected_duplicate` nor `confirmed_duplicate`.
- **Option B — Suspected duplicate:** The pair routes to human review despite being below the stated suspected floor.
- **Option C — Product-specified alternative:** Product supplies another existing-state outcome and its routing. A new seventh state is not implied by this option and would require separate approval.

### Recommended option

**No recommendation.** The approved contract names `0.70` as the suspected-band floor but does not explicitly define the negative outcome below it. Treating the threshold's converse as approved would be an inference.

### Exact contract wording required after approval

Insert one selected sentence after D5.1's confidence-band sentence:

- **If Option A:** “Pairs with confidence below `0.70`, where no approved direct exact-match confirmation shortcut applies, produce no duplicate finding.”
- **If Option B:** “Pairs with confidence below `0.70`, where no approved direct exact-match confirmation shortcut applies, are classified as `suspected_duplicate` and route to human review.”
- **If Option C:** “Pairs with confidence below `0.70`, where no approved direct exact-match confirmation shortcut applies, are classified as `[APPROVED EXISTING STATE]` and route to `[APPROVED ACTION OR NO ACTION]`.”

### Tests that would become authorized after approval

- The existing below-`0.70` test becomes an authorized golden test only if Option A is selected.
- Boundary fixtures at `0`, immediately below `0.70`, and exactly `0.70` using the selected outcome.
- Direct exact-ID and exact-email-plus-phone fixtures below `0.70` confirming that approved shortcuts still take precedence.

## D5-2 — Confidence at or above 0.90 without two exact strong fields

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D5.1 says all non-shortcut confirmations require confidence `>=0.90` **and** two strong fields agreeing exactly. It does not explicitly assign the fallback state when the confidence condition passes but the strong-field condition fails. The required golden case says exact email plus fuzzy name falls to `suspected_duplicate`, not confirmed.

### Current implementation behavior

`domain/duplicates.py:41–45` raises `ProductApprovalRequired` for confidence `>=0.90` with fewer than two exact strong fields.

### Why the behavior is not authorized

The exception is an appropriate stop, but no production terminal state is authorized for this edge. Engineering cannot infer that “not confirmed” necessarily means suspected, proper, or no finding.

### Smallest possible decision Product must make

Assign one existing terminal outcome to this edge case.

### Proposed options

- **Option A — Suspected duplicate:** Route the pair to human review.
- **Option B — No duplicate finding:** Do not emit a duplicate state.
- **Option C — Product-specified existing state/action:** Product supplies the exact outcome without introducing an unapproved state.

### Recommended option

**Option A — Suspected duplicate.** This is supported by the already-approved intent that confirmation requires both conditions, suspected cases receive human review, and the exact-email-plus-fuzzy-name golden case must be suspected rather than confirmed.

### Exact contract wording required after approval

Insert one selected sentence after the standard confirmation rule:

- **If Option A:** “A non-shortcut pair with confidence `>=0.90` but fewer than two exact strong-field agreements is `suspected_duplicate` and routes to human review.”
- **If Option B:** “A non-shortcut pair with confidence `>=0.90` but fewer than two exact strong-field agreements produces no duplicate finding.”
- **If Option C:** “A non-shortcut pair with confidence `>=0.90` but fewer than two exact strong-field agreements is classified as `[APPROVED EXISTING STATE]` and routes to `[APPROVED ACTION OR NO ACTION]`.”

### Tests that would become authorized after approval

- Fixtures at exactly `0.90` and above `0.90` with zero and one exact strong-field agreement.
- Exact-email-plus-fuzzy-name cases at/above `0.90` using the approved fallback.
- Confirmation fixtures proving two exact strong fields still produce `confirmed_duplicate`.

## D5-3 — Blank-name candidate handling

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D5.4 keeps the normalized-name-prefix blocking key `|nm|` using the first eight normalized characters. It does not specify what happens when the normalized name is empty or unavailable.

### Current implementation behavior

`domain/duplicates.py:57–58` returns no name-prefix key for an empty normalized name. Other candidate blocks are not implemented in the current bounded slice.

### Why the behavior is not authorized

Omitting the block changes which pairs become candidates. The contract does not explicitly authorize omission, a shared blank-name block, or an incomplete-evaluation outcome.

### Smallest possible decision Product must make

Define whether an empty normalized name creates a name-prefix blocking key.

### Proposed options

- **Option A — No name-prefix key:** An empty normalized name produces no `|nm|` key; the record may still participate through other approved blocking keys.
- **Option B — Controlled blank-name block:** Empty normalized names share a specifically documented candidate block.
- **Option C — Incomplete duplicate evaluation:** Treat absence of the name input as preventing a complete duplicate result for that record/module.

### Recommended option

**Option A — No name-prefix key.** This follows the approved key definition—there are no first eight normalized characters to use—and avoids making blank names match each other. It does not prevent other approved blocks from finding the pair.

### Exact contract wording required after approval

Add one selected sentence to D5.4:

- **If Option A:** “If the normalized name is empty or unavailable, no `|nm|` blocking key is generated; other approved blocking strategies remain applicable.”
- **If Option B:** “If the normalized name is empty or unavailable, generate the controlled blocking key `[APPROVED KEY SEMANTICS]`; this behavior is intentional and must be covered by false-positive tests.”
- **If Option C:** “If the normalized name is empty or unavailable, duplicate evaluation for that record/module is marked `[APPROVED INCOMPLETE STATUS]` and no complete duplicate result is published for it.”

### Tests that would become authorized after approval

- Empty string, whitespace-only and unavailable normalized-name fixtures.
- Proof of whether other approved blocks remain active.
- If Option B, false-positive/load cases for large blank-name blocks.
- If Option C, completion-status fixtures using the approved existing status.

## D5-4 — Product policy versus implementation detail

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D5 explicitly fixes confirmation shortcuts, thresholds/strong-field corroboration, within-module scope, no-loss handling above 40 records, and the first-eight normalized-name block. It references “spec §6.7” for the standard rule but does not identify a filename/version. D5.3 explicitly delegates the deterministic splitting strategy to engineering.

### Current implementation behavior

The bounded classifier consumes a caller-supplied confidence and exact-strong-field count. It does not implement signature normalization, the strong-field list, candidate blocks other than pre-normalized `|nm|`, confidence weights/denominator, or fuzzy similarity. The fixed-chunk/cross-chunk design exists only as a synthetic verification spike.

### Why the behavior is not authorized

The missing mechanics can change candidate membership, confidence and final state. They cannot be imported from an unpinned old/reverse-engineered specification. At the same time, the contract has already declared deterministic splitting mechanics to be engineering work, so Product should not be asked to approve inconsequential data structures or scheduling details.

### Smallest possible decision Product must make

Approve the boundary between normative D5 Product policy and lossless engineering execution, and provide one authoritative source for every normative mechanic.

### Proposed options

- **Option A — Inline normative mechanics:** Add the exact normalization rules, candidate blocking keys, exhaustive strong-field set, field weights, confidence denominator, and fuzzy-similarity algorithm to the product contract. Engineering retains only execution mechanics that cannot change candidate pairs, confidence or classification.
- **Option B — Pin an authoritative specification:** Identify the exact filename/version/hash of the authoritative §6.7, state that D5 contract text overrides it where different, and enumerate which sections are normative Product policy. Engineering retains only lossless execution mechanics.
- **Option C — Delegate more mechanics to engineering:** Product approves behavioral invariants/golden outcomes and explicitly delegates selected normalization/similarity mechanics to engineering, subject to technical verification. Product must enumerate what is delegated; silence is not delegation.

### Recommended option

**Option A — Inline normative mechanics.** The approved D5 intent emphasizes a defined, defensible confirmation policy, and mechanics that change candidates or confidence directly affect that policy. Keeping normative behavior in the authoritative contract avoids ambiguity about which old specification/version governs. The recommendation does not supply the missing values.

### Exact contract wording required after approval

Add a D5 subsection using this structure, with every bracket completed by Product:

> **D5.5 — Normative matching mechanics.** Product policy includes: signature fields `[APPROVED FIELDS]`; exhaustive strong-field set `[APPROVED STRONG FIELDS]`; normalization `[APPROVED RULES PER FIELD]`; candidate blocking keys `[APPROVED KEYS AND EMPTY-VALUE RULES]`; confidence weights `[APPROVED WEIGHTS]`; considered-field denominator `[APPROVED FORMULA]`; fuzzy similarity `[APPROVED ALGORITHM AND PARAMETERS]`; and the terminal outcomes in D5.1. Engineering may choose only lossless execution mechanics—work scheduling, data structures, deterministic chunk size/order, retry/idempotency and a representative-pair ordering that preserves all pair evidence—provided golden tests prove identical candidate pairs, confidence and classifications.

If Option B is selected, replace the normative list with:

> “The normative D5 matching mechanics are `[`**APPROVED FILE**``, version/hash ``**APPROVED VERSION/HASH**``]`, Section `[APPROVED SECTIONS]`. This contract overrides that source wherever they differ. Engineering may choose only lossless execution mechanics that do not change candidate pairs, confidence, classifications or retained pair evidence.”

If Option C is selected, Product must add:

> “The following are normative Product policy: `[APPROVED LIST]`. The following are delegated implementation details: `[EXPLICIT DELEGATED LIST]`. Delegated choices must pass `[APPROVED INVARIANT/GOLDEN TEST SET]` and may not change approved states, thresholds, scope or review/merge routing.”

### Tests that would become authorized after approval

- Golden normalization fixtures for every approved field.
- Candidate-block membership fixtures including empty values.
- Strong-field enumeration and exact-agreement fixtures.
- Exact weighted-confidence and missing-field denominator fixtures.
- Fuzzy-similarity fixtures with approved algorithm/parameters.
- Threshold boundary fixtures and all D5 contract golden cases.
- Invariance tests proving alternative lossless execution plans produce identical pairs/confidence/states.

### Already-authorized and technical-only D5 mechanics

- **ALREADY AUTHORIZED:** Within-module scope, exact shortcuts, confirmation conditions, the approved suspected interval, no skipped blocks above 40, the `|nm|` strategy and D16 review/merge routing.
- **TECHNICAL VERIFICATION REQUIRED:** Fixed chunk sizing/order, cross-chunk scheduling, exact re-fetch, stable ordering, idempotency, API/runtime cost, and proof that no blocking key or derivative crosses a durable boundary. These do not require Product approval if they preserve the approved behavior.
- **PRODUCT DECISION REQUIRED:** Any product-visible tie-break or any tie-break that discards pair evidence. A lossless internal representative ordering remains an engineering detail subject to verification.

## D4-1 — Numeric minimum-record floor

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D4 states that `properPct` is “gated by the existing minimum-record floor before the score is surfaced,” but the contract does not state the numeric value.

### Current implementation behavior

`domain/scoring.py:42–52` calculates `properPct` only. It applies no floor and is not wired to a production surface.

### Why the behavior is not authorized

The formula is authorized, but no numeric floor may be inferred from the old widget, old specification, decision register or configuration defaults. Without the number, production surfacing cannot meet the approved gate.

### Smallest possible decision Product must make

State the exact integer record count at which a D4 user score becomes eligible to be surfaced.

### Proposed options

- **Option A — Confirm a fixed v1 floor:** Product supplies the exact integer `[N]`.
- **Option B — Approve a versioned policy value:** Product supplies the exact initial integer `[N]` and states that changing it requires a new Product-approved policy version. This does not authorize UI configurability under D8.
- **Option C — Remove the floor:** Amend D4 to surface `properPct` without a minimum. This changes already-approved intent and must be explicit.

### Recommended option

**No recommendation.** The contract supplies no approved statistical, commercial or UX basis for selecting a number or removing the floor.

### Exact contract wording required after approval

- **If Option A:** “The v1 D4 minimum-record floor is `[APPROVED INTEGER N]`. A user's `properPct` is surfaced only when `records_for_user >= N`; below `N`, no user score is surfaced.”
- **If Option B:** “The initial D4 minimum-record floor for policy version `[APPROVED VERSION]` is `[APPROVED INTEGER N]`. A user's `properPct` is surfaced only when `records_for_user >= N`. Any change requires a newly approved policy version and does not imply D8 UI configurability.”
- **If Option C:** “D4 has no minimum-record floor; `properPct` may be surfaced for any user with at least one eligible record.”

### Tests that would become authorized after approval

- Eligibility fixtures at `N-1`, `N`, and `N+1` for Options A/B.
- Zero-record handling using separately approved wording/behavior if it can become visible.
- Proof that the floor gates surfacing only and does not alter `properPct` arithmetic.

## D4-2 — Decimal precision

**Status: TECHNICAL VERIFICATION REQUIRED**

### Current contract wording

D4 approves the `properPct` formula but does not specify internal Decimal precision or customer-facing rounding.

### Current implementation behavior

`domain/scoring.py` uses Python Decimal with a 28-digit local context and returns an unrounded Decimal from the domain primitive.

### Why this is not a Product approval request

Internal deterministic precision that preserves the approved formula is an engineering concern under the authorization matrix. It requires numerical verification. Any customer-facing rounding/display rule would be a separate Product/UI decision and is not proposed here.

### Smallest required action

No Product decision. Engineering must verify deterministic results, boundary stability and a documented internal representation before production use.

### Proposed options

Not applicable; this is not a Product decision.

### Recommended option

**No recommendation.** Engineering verification must provide evidence first.

### Exact contract wording required after approval

None. If Product later wants a customer-facing rounding rule, that rule must be separately approved and added to the contract.

### Tests that would become authorized after approval

No tests await Product approval here. Technical verification should cover repeating decimals, threshold-adjacent values, cross-runtime reproducibility and proof that internal precision does not alter approved classifications.

## TZ-1 — Exact customer-facing approximation disclosure

**Status: PRODUCT DECISION REQUIRED** for exact copy; **ALREADY AUTHORIZED** for the disclosure requirement; **TECHNICAL VERIFICATION REQUIRED** for module/source availability.

### Current contract wording

TZ-1 requires a genuine close/audit timestamp where available. Where it is not available, `Modified_Time` must be an “explicit, disclosed approximation rather than silently substituting it.” The contract does not approve exact customer-facing wording or placement.

### Current implementation behavior

`domain/time_policy.py:15–18` contains this sentence:

> “Modified_Time is used as an approximation because no genuine close/audit timestamp is available for this module.”

The resolver attaches it only to the `APPROXIMATION_DISCLOSED` result when the caller supplies no genuine timestamp and does supply `Modified_Time`.

### Why the exact wording is not authorized

The behavioral obligation to disclose is approved. The exact copy is implementation-authored and could become customer-facing. The contract has not approved its wording, localization or placement. Separately, engineering must prove that “no genuine timestamp is available” is true per module; a failed/not-fetched permission path is not proof.

### Smallest possible decision Product must make

Approve exact disclosure copy, or explicitly delegate final wording under approved mandatory content requirements.

### Proposed options

- **Option A — Approve current copy exactly:** Use the existing sentence verbatim.
- **Option B — Product supplies replacement copy:** Product provides the exact approved sentence.
- **Option C — Approve mandatory content, delegate copy:** Every disclosure must identify `Modified_Time`, call it an approximation, state that a genuine close/audit timestamp was unavailable, and identify the affected module/rule; final copy/localization follows an approved content-review process.

### Recommended option

**No recommendation.** The current sentence is factually aligned with TZ-1, but no approved voice, localization or screen-placement standard is present in the reviewed authority.

### Exact contract wording required after approval

- **If Option A:** “When TZ-1 uses `Modified_Time`, display exactly: ‘Modified_Time is used as an approximation because no genuine close/audit timestamp is available for this module.’”
- **If Option B:** “When TZ-1 uses `Modified_Time`, display exactly: ‘[PRODUCT-APPROVED COPY]’.”
- **If Option C:** “Every customer-facing TZ-1 approximation disclosure must identify `Modified_Time`, state that it is an approximation, state that no genuine close/audit timestamp was available for the affected module/rule, and be approved through `[APPROVED CONTENT PROCESS]`. The approximation must never be silent.”

### Tests that would become authorized after approval

- Exact-copy snapshot/assertion for Options A/B.
- Mandatory-content validation and localization/content-review fixtures for Option C.
- Existing semantic tests remain authorized: genuine timestamp wins, approximation is disclosed, and `UNAVAILABLE` occurs only after both sources are verified inaccessible.

## D7-1 — Operational metadata boundary

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D7 says anything exported or persisted must be reduced to the minimal record tuple. D13 separately requires durable jobs and persisted batch results; D14-POLICY requires an organization connection; TZ-1 requires organization timezone use. The contract does not expressly distinguish record-derived findings from system operational/control metadata.

### Current implementation behavior

No Catalyst persistence or schema exists. The bounded `MinimizedRecordFinding` contains only the approved tuple and deliberately excludes scan/batch linkage.

### Why the behavior is not authorized

Production D13/D14/TZ-1 cannot operate durably without some control metadata, but treating it as exempt from D7 would be an interpretation. Conversely, applying the literal tuple to all system metadata makes the approved durable job/connection direction infeasible. Product/privacy must define the boundary.

### Smallest possible decision Product must make

State whether D7's tuple restriction applies to all persisted system data or specifically to record-derived findings/exports, and—if a separate operational class is permitted—approve its exact categories and purposes.

### Proposed options

- **Option A — Literal all-persistence boundary:** Only the D7 minimal tuple may be persisted. No separate operational metadata class is authorized; production D13/D14 persistence remains blocked pending another design/contract change.
- **Option B — Narrow operational control-plane class:** The minimal tuple remains mandatory for record-derived findings/exports. A separate, non-record operational class is allowed only for Product-approved tenant/org connection references; scan/batch identity; job state/checkpoints; provider opaque job/page references; counts/checksums/controlled errors; timezone/policy/scope versions; and completion evidence. No CRM source field values, names, stages, record timestamps, blocking keys, fingerprints, aggregates or user-attribution tokens are permitted.
- **Option C — Product-supplied narrower class:** Product supplies a smaller exact category list sufficient for the approved next platform slice.

### Recommended option

**Option B — Narrow operational control-plane class.** D13 explicitly requires durable resumable batch state, D14-POLICY requires an organization connection, and TZ-1 requires organization timezone behavior. This option reconciles those approved decisions while retaining D7's prohibition on rich/record-derived persistence. It does not approve a schema or any aggregate/user-token persistence.

### Exact contract wording required after approval

- **If Option A:** “D7's minimal tuple restriction applies to all Catalyst-persisted data without an operational-metadata exception. D13/D14 production persistence remains blocked until a separately approved mechanism is available.”
- **If Option B:** “D7's minimal tuple restriction governs all record-derived findings and exports. Catalyst may separately persist non-record operational control metadata solely to implement D13, D14-POLICY and TZ-1: `[APPROVED CATEGORY LIST]`. This class must not contain CRM source field values, names/labels/stages, record-level source timestamps, raw or derived duplicate blocking keys/fingerprints, aggregate result rows, user-attribution identifiers/tokens or value-bearing errors. Exact fields, access controls and deletion linkage require privacy/security review before schema implementation.”
- **If Option C:** “D7 permits only the following non-record operational metadata outside the minimal finding tuple: `[PRODUCT-APPROVED CATEGORIES AND PURPOSES]`. All unlisted persisted data remains prohibited.”

### Tests that would become authorized after approval

- Field/category allowlist tests for the approved operational class.
- Negative leakage tests for all explicitly forbidden record-derived/value-bearing classes.
- Ownership/tenant isolation and deletion-linkage tests after technical design approval.
- No schema test becomes authorized merely from category approval; Catalyst schema remains a later engineering/security gate.

## D7-2 — Organization OAuth credential persistence

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D14-POLICY approves an admin-authorized organization connection but does not specify credential storage. D7's literal persistence wording does not exempt encrypted refresh-token material.

### Current implementation behavior

No OAuth flow, token storage or schema exists.

### Why the behavior is not authorized

An offline organization connection normally requires durable credential material, but technical necessity does not override D7. Product/privacy must explicitly authorize or reject this data class before engineering selects a storage mechanism.

### Smallest possible decision Product must make

Decide whether encrypted organization refresh-credential material may be persisted as a restricted connection secret.

### Proposed options

- **Option A — Permit encrypted credential persistence:** Treat it as a separate restricted secret class, never as record/result data, subject to technical verification of encryption, key separation, access and revocation.
- **Option B — Do not permit persistence:** Production offline connection remains blocked unless engineering verifies a non-persistent mechanism compatible with D14-POLICY.

### Recommended option

**Option A — Permit encrypted credential persistence.** D14-POLICY approves a server-side organization connection rather than an operator session; durable refresh capability is ordinarily necessary to execute unattended resumable D13 jobs. This recommendation does not approve a storage service, schema, key facility or retention period.

### Exact contract wording required after approval

- **If Option A:** “Encrypted organization refresh-credential material may be persisted solely as a restricted connection-secret data class for D14-POLICY. It must be encrypted with authenticated encryption, use key material stored separately, be inaccessible to the client, never appear in logs/exports, and be revoked/deleted under the separately approved credential lifecycle. Platform feasibility remains subject to technical verification.”
- **If Option B:** “Organization OAuth refresh-credential material must not be persisted. Production D14-POLICY/D13 operation remains blocked until an approved non-persistent authorization mechanism is verified.”

### Tests that would become authorized after approval

- If Option A: synthetic secret encryption/decryption, key-separation, access-denial, log-redaction, rotation and revocation tests after the platform mechanism is technically selected.
- If Option B: tests proving no credential survives the active authorization operation.

## D7-3 — Retention duration and deletion triggers

**Status: PRODUCT DECISION REQUIRED**

### Current contract wording

D7 explicitly states that TTL, deletion trigger and audit-log retention duration remain open.

### Current implementation behavior

No production retention, deletion or durable export behavior exists.

### Why the behavior is not authorized

Any default duration or deletion event would invent Product/privacy policy. Encryption and data minimization do not answer how long approved data may remain.

### Smallest possible decision Product must make

For each Product-approved persisted data class, provide its TTL, deletion triggers and permitted audit retention. If Product is not ready to supply them, production persistence remains blocked.

### Proposed options

- **Option A — Approve explicit values now:** Product/privacy supplies exact TTL, trigger and audit-retention values per approved class.
- **Option B — Defer:** Keep all production persistence and durable generated exports blocked while technical work remains synthetic/non-production.

No numeric duration is proposed in this request.

### Recommended option

**No recommendation.** No legal, contractual, customer or operational evidence in the approved materials supports a duration.

### Exact contract wording required after approval

- **If Option A:** “Retention policy version `[APPROVED VERSION]`: `[APPROVED DATA CLASS]` TTL = `[APPROVED DURATION]`; deletion triggers = `[APPROVED EVENTS]`; audit retention = `[APPROVED DURATION AND ALLOWED FIELDS]`. The policy for every other class remains `[APPROVED STATUS]`.”
- **If Option B:** “Production persistence and durable generated export storage remain blocked until Product/privacy approves TTL, deletion triggers and audit-log retention for every persisted data class.”

### Tests that would become authorized after approval

- TTL boundary and expiry tests for each approved class.
- Every approved deletion-trigger test, including cascade/linkage behavior.
- Audit allowlist and retention-expiry tests.
- Proof that unapproved classes are never retained.

## D7 exclusions — no approval requested

- **ALREADY AUTHORIZED / PROHIBITED TO PERSIST:** CRM source values, names, labels, stages, value-bearing reasons and raw duplicate blocking-key values.
- **Not proposed for approval:** aggregate contribution rows, persisted user/time/domain/rule aggregates, opaque or hashed user tokens, raw/HMAC/hashed/digested duplicate fingerprints, or durable aggregate exports.
- No retention default is suggested. Until D7-3 is decided, production persistence remains blocked.

## Minimum decisions required before the next implementation slice

For the next bounded **D4/D5 domain-policy slice**, Product need decide only:

1. The exact D4 numeric minimum-record floor.
2. D5 outcomes below `0.70` and at/above `0.90` without two exact strong fields.
3. D5 blank-name blocking behavior.
4. The authoritative D5 normative mechanics and the boundary delegated to engineering.

TZ-1 disclosure copy is required only before customer-facing approximation text is exposed. D7 operational metadata, credential and retention decisions are required only before any Catalyst connection/job persistence slice. None of these approvals, if granted, modifies code automatically or lifts the existing production-authoring NO-GO without an explicit contract change.
