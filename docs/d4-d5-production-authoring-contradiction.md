# D4/D5 Production-Authoring Contradiction Resolution Report

**Scope:** D4/D5 production-authoring authorization only  
**Product authority:** `approved-product-contract.md`  
**Execution boundary:** `implementation-authorization-matrix.md`  
**Date:** 17 August 2026

## Executive conclusion

The authoritative product contract contains an unresolved internal contradiction about whether production user-score and duplicate-detection rule authoring may proceed.

The contract clearly approves the D4 formula and D5 policy. It also states that both are fully resolved and cleared for specified architecture, rule-catalogue and golden-test work. However, the contract's implementation reassessment explicitly retains a NO-GO for user-score and duplicate-detection rule authoring. No condition, owner or later sentence explicitly withdraws that NO-GO.

The product decision register is an older source that the contract expressly updates; it cannot override the updated contract. The reverse-engineered specification describes observed/intended mechanics but is not identified by filename/version as a product-approval instrument and cannot authorize production implementation. Neither resolves the contradictory go/no-go statements.

**Classification: REQUIRES PRODUCT APPROVAL.** Product must explicitly state whether production D4 user-score authoring and production D5 duplicate-detector authoring are authorized now, or remain blocked and, if blocked, what condition releases each block. No implementation change is authorized by this report.

## Exact conflicting statements

| ID | Source and location | Exact statement | Effect |
|---|---|---|---|
| C1 | `approved-product-contract.md`, Section 5, line 205 | “Updated status: Conditional GO for architecture and extraction work; NO-GO for user-score and duplicate-detection rule authoring.” | Explicitly blocks production D4/D5 rule authoring. |
| C2 | `approved-product-contract.md`, Section 5, line 207 | “Cleared to proceed: Scoring engine (domain/overall formula per D2, user score per D4) ... and the full duplicate-detection policy (D5, all four sub-decisions) are now fully specified and may be used to author Catalyst architecture, the rule catalogue, and golden test cases for the areas they cover.” | Says D4/D5 are cleared, but explicitly names architecture/catalogue/tests rather than unambiguously authorizing production rule code. “Scoring engine” makes the scope ambiguous. |
| C3 | `approved-product-contract.md`, D4, lines 42–53 | D4 status is “Approved”; `properPct` is selected; “no engineering change is required for the formula itself.” | Resolves formula behavior, but does not explicitly supersede C1's production-authoring NO-GO. |
| C4 | `approved-product-contract.md`, D5, lines 57–84 | D5 status is “Approved — all four sub-decisions resolved,” followed by required confirmation, scope, overflow and blocking behavior plus golden cases. | Resolves the stated duplicate policy, but does not explicitly supersede C1's production-authoring NO-GO. |
| C5 | `approved-product-contract.md`, Section 2, line 164 | “None remaining. D4 and D5 ... are now fully resolved.” | Confirms decision completeness, not implementation authorization. It conflicts with any reading of C1 that assumes D4/D5 remain blocked because their product behavior is unresolved. |
| C6 | `approved-product-contract.md`, D16 carry-forward, line 180 | Merge routing is “subject to D5's still-open confirmation policy, once specified.” | Directly stale against D5's approved/fully resolved status in C4 and C5. It demonstrates that older unresolved wording remains in the contract. |
| C7 | `approved-product-contract.md`, Section 5, lines 209–210 | The explicit “Still blocking” list names D14-EVIDENCE and D8/D9/D10/D12/D15-KNOB, but not D4 or D5. | Suggests D4/D5 are no longer decision blockers, but does not expressly cancel C1's authoring NO-GO. |
| C8 | `approved-product-contract.md`, Section 5, line 212 | Full GO is to be reassessed after D14-EVIDENCE results. | May imply the remaining architecture-wide gate is D14-EVIDENCE, but it does not state whether C1's D4/D5 NO-GO is independently lifted before or after that event. |

## Source-authority analysis

### Approved product contract

This is the only current product authority. Its own usage rule says approved decisions may drive the rule catalogue and golden tests, while unresolved items must not drive implementation. D4 and D5 are not listed in Section 4's unresolved table.

That establishes that the D4 formula and D5 product policy are resolved. It does not establish which of these mutually incompatible implementation readings product intended:

1. C1 is stale and production D4/D5 authoring is now allowed.
2. C1 is deliberate: policy libraries/catalogue/tests are allowed, but production rules remain blocked.
3. C1 is deliberate only until D14-EVIDENCE or another unstated gate passes.

Selecting among these readings would change implementation authorization and therefore would be a new product decision.

### Product decision register

`product-decision-register.md` lines 16–17 and 411–435 mark D4/D5 unresolved and the migration NO-GO. That register predates the approval update. The contract states at lines 3–5 that it is the register “updated with the approval table” and is authoritative for approved decisions. Therefore:

- the register explains where the older NO-GO language came from;
- its old D4/D5 `TBD` statuses are superseded by the contract's approved D4/D5 entries;
- it cannot resolve whether C1 was intentionally retained or accidentally left stale.

### Reverse-engineered specification

`reverse-engineered-spec.md` documents the observed `properPct` behavior and a duplicate algorithm in Section 6.7. It can provide technical evidence about prior behavior. It does not contain a product go/no-go authorization and is not identified by the contract with a pinned filename/version as an approval instrument.

The specification therefore cannot lift C1. Even if it fully specified every D4/D5 algorithm, technical completeness would not answer whether product authorized production authoring.

### Implementation Authorization Matrix

The matrix is the execution boundary, not additional product approval. It already classifies both “D4 production rule authoring” and “D5 production detector/rule authoring” as **REQUIRES PRODUCT APPROVAL** because of C1/C2. It resolves engineering conduct—stop—but does not resolve the underlying product contradiction.

## Narrow product decision required

Product must provide an explicit answer to both questions:

1. **D4 production authorization:** Is production implementation of the approved `properPct` user-score formula authorized now, subject to separate gates such as the unresolved numeric minimum floor, D7 persistence and D10 UI; or is all production D4 authoring still NO-GO?
2. **D5 production authorization:** Is production implementation of the approved D5 confirmation/blocking policy authorized now, subject to separately documented unresolved matching internals and technical verification; or is all production duplicate-detector authoring still NO-GO?

If either remains NO-GO, the approval must name its release condition. Possible conditions are not proposed here because choosing one would invent product behavior or authorization.

Until the contract is clarified or re-issued:

- existing bounded D4/D5 pure-domain work and fully authorized tests remain as accepted;
- no additional production D4/D5 authoring is authorized;
- no architecture or specification inference may be used to lift the stop.

## Remaining D14-EVIDENCE verification gates

These are technical evidence tasks, not product decisions:

1. Determine whether Zoho exposes a reliable signal that the integration identity's visible record count is below the module's true total.
2. Determine whether requested and actually granted OAuth scopes can be introspected at runtime and how missing grants are detected.
3. Verify the effect of private sharing, explicit record sharing, profiles, role hierarchy and territory management using a realistic sandbox.
4. Compare visibility behavior across standard record APIs, COQL, Bulk Read and available count APIs under the same identities.
5. Test an Administrator-profile identity and deliberately restricted identities against known fixture totals.
6. Establish a reliable CRM Administrator-status signal; application-admin status alone is insufficient.
7. Define evidence-backed visibility-assurance criteria, warnings, expiry and retest behavior. Do not label visibility “full” or guaranteed without proof.
8. Verify inaccessible-module, inaccessible-field and partial-result signals returned by each selected API.
9. Record results by Zoho API version, CRM edition, data center and tested sharing configuration; a sandbox pass is not universal proof.

## Remaining Zoho/Catalyst platform feasibility gates

These may be investigated with sandbox/synthetic data but must not become product behavior merely because a spike passes:

### Zoho feasibility

1. Verify the exact read-only scopes for Organization, Users/admin proof, module metadata, standard records, COQL, Bulk Read, Timeline and Audit access. Flag any `CREATE`-named requirement; do not add it.
2. Measure Bulk Read and COQL criteria support, date filtering, module/field coverage, paging, page-token/result expiry, callbacks, API credits, latency and stable ordering across supported editions/data centers.
3. Verify organization ID, environment and data-center binding across authorization, refresh, reauthorization and revocation.
4. Verify exact record re-fetch by persisted ID membership and visibility consistency for duplicate work.
5. Verify genuine close/audit timestamp sources and permissions per supported module; where absent, verify `Modified_Time` availability for the required disclosed approximation.
6. Verify Organization API timezone values and their IANA mappings across supported data centers/editions.

### Catalyst feasibility

1. Prove Data Store conditional-update/transaction semantics for leases, compare-and-set transitions, staging promotion and idempotent commit.
2. Prove Job Scheduling delivery, retry, timeout and duplicate-execution behavior.
3. Prove callback authenticity/correlation handling; callbacks must remain wake-up hints rather than trusted result evidence.
4. Prove temporary worker storage is non-durable and securely cleared, or require streaming.
5. Verify server-only table access, tenant/org ownership enforcement, application authentication and CSRF protections.
6. Verify the supported secret-storage, encryption, authenticated-encryption key handling and rotation mechanism with synthetic credentials.
7. Crash-test every proposed batch transition and prove resume without lost or double-counted facts.
8. Verify provider/parsed/unique/persisted count reconciliation, checksums and successor-page completeness with synthetic data only until D7 persistence is approved.
9. Load-test deterministic oversized-block pair coverage and duplicate re-read cost without persisted raw, hashed or digested blocking keys.

## Final status

**D4/D5 production-authoring authorization: REQUIRES PRODUCT APPROVAL.**

No authoritative existing material resolves the implementation go/no-go contradiction. This report stops at that boundary. It makes no contract, matrix, architecture, UI, route, schema, OAuth, collector, persistence, aggregate, retention or implementation change.
