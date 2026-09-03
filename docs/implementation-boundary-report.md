# Implementation Boundary Report

**Execution boundary:** `implementation-authorization-matrix.md`  
**Product authority:** `approved-product-contract.md`  
**Date:** 17 August 2026

## Implemented now

Only side-effect-free backend domain primitives classified **IMPLEMENT NOW** were added:

- D2 severity coefficients, severity-weighted per-rule domain scoring and applicable/measurable normalization;
- D4 `properPct`, with no numeric minimum floor inferred;
- D3 six-state precedence;
- D5 direct confirmation shortcuts, standard confirmed condition, `[0.70, 0.90)` suspected band, pre-normalized eight-character name-prefix key, and D16 action routing;
- D6 blank repeated-value exclusion;
- D7 literal minimized record/export tuple and a defensive forbidden-key detector;
- D14 explicit-read-scope enforcement;
- TZ-1 genuine close event preference and explicitly disclosed `Modified_Time` approximation;
- D16 combined-selection single rescore;
- D17 fresh per-scan API counters including failed calls.

The implementation raises an explicit authorization-boundary error instead of choosing behavior for D12, zero-eligible rules, or the D5 `>=0.90`/fewer-than-two-strong-fields edge.

No React screen, production API route, OAuth flow, Catalyst table/schema, CRM collector, persisted aggregate, opaque user token, retention policy, delete behavior, threshold UI, estimate, trend behavior or Configuration Hygiene behavior was added.

## Technical verification executed

The synthetic verification runner passed:

| Spike | Result |
|---|---|
| D5 deterministic chunk coverage | PASS for 41, 81 and 101 records; all `n(n-1)/2` pairs covered |
| D13 checkpoint/resume/idempotency | PASS with 2 verified batches and 4 unique minimized synthetic facts |
| TZ-1 timezone conversion | PASS for Asia/Kolkata and a New York DST overlap |
| D14 read-scope guard | PASS; `ZohoCRM.bulk.CREATE` rejected |
| D7 leakage guard | PASS; forbidden nested `stage` detected |
| D2 decimal determinism | PASS across 100 repeated calculations |

The first checkpoint run exposed a nullable composite-key hazard: SQLite allowed a duplicate retried fact when `rule_id` was `NULL`. The synthetic spike now uses a non-null controlled identifier and passes. This is technical evidence only and is not a proposed Catalyst schema.

## Technical verification still outstanding

These require an external Zoho/Catalyst sandbox or confirmed platform configuration and were not converted into product behavior:

1. D14-EVIDENCE visible-vs-total signals, granted-scope introspection, and sharing/territory/role effects.
2. Reliable CRM Administrator-status proof.
3. Real Bulk Read/COQL scopes, limits, paging, expiry, API credits and visibility consistency.
4. Catalyst transaction/conditional-update, scheduler retry, callback and ephemeral-storage guarantees.
5. Per-module genuine close/audit timestamp availability and required Timeline/Audit permissions.
6. Organization timezone values and mappings across every supported Zoho DC/edition.
7. Exact record re-fetch/API cost for the proposed duplicate batch-pair execution design.
8. Production secret storage, encryption and key rotation facilities.

## Product decisions still required

Implementation stopped at these boundaries:

- D4 numeric minimum-record floor.
- Identification/version of the authoritative D5 §6.7 spec, any missing fuzzy-similarity algorithm, and the state for confidence `>=0.90` without two exact strong fields.
- Clarification of the contract's contradictory D4/D5 production-authoring go/no-go wording.
- D7 record-to-job linkage, operational metadata, OAuth-token persistence boundary, server-worker memory interpretation, aggregates/user tokens/user-time results, TTL, deletion triggers and audit retention.
- Zero-eligible-rule calculation/presentation.
- D8 threshold configurability.
- D9 setup cost/runtime estimate behavior.
- D10 Modules, Users, Trend, Records and Fix screen behavior, including partial-result presentation.
- D12 Configuration Hygiene and subsequent D2 revalidation.
- D15-KNOB.
- Automatic prior-period extraction, operator cancellation behavior, aggregate exports and exact approximation-disclosure placement.

## Prohibited behavior not implemented

- No silent D12 exclusion or production overall score.
- No `CREATE`, `.ALL`, write, update, delete, share or mutation OAuth scope.
- No raw CRM payload, source value, blocking key or derived duplicate key persistence.
- No `AggregateContribution`, `ScanAggregate`, opaque user token or persisted user/time aggregate.
- No final result calculated from transient browser/worker state.
- No silent browser/server timezone fallback.
- No silent `Modified_Time` substitution and no skipping it when it is the available required approximation.
- No exact-email-plus-fuzzy-name confirmation shortcut.
- No cross-module duplicate matching.

## Verification commands

```powershell
python -m unittest discover -s tests -v
python spikes\run_synthetic_verifications.py
```

At this checkpoint there is no newly discovered contradiction between the contract and matrix. The previously documented D4/D5 Section 5 wording conflict remains an explicit product-approval stop.
