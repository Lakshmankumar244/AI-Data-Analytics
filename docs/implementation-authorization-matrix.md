# Implementation Authorization Matrix

**Status:** Final authorization classification; no application implementation performed  
**Product authority:** `approved-product-contract.md`  
**Architecture reviewed:** `catalyst-architecture.md`  
**Date:** 17 August 2026

## 1. How to use this matrix

The classifications apply to the smallest component named in each row:

- **IMPLEMENT NOW** — the exact behavior is explicitly authorized by the approved product contract. This does not waive a separate cross-cutting production gate such as D7 persistence approval or D14-EVIDENCE.
- **IMPLEMENT AFTER TECHNICAL VERIFICATION** — the product behavior is approved, but the platform/API mechanism or required evidence is not yet proven. Engineering may execute a non-production spike or evidence test now; production implementation waits for the stated gate.
- **REQUIRES PRODUCT APPROVAL** — the contract does not specify the behavior or parameter. Engineering must not select a default.
- **DO NOT IMPLEMENT** — the behavior conflicts with the contract.

`catalyst-architecture.md` is a design proposal, not product authority. Its internal state names, schemas, algorithms and APIs do not become approved merely by appearing there.

The contract contains one unresolved authorization inconsistency: Section 5 line 205 says user-score and duplicate-detection rule authoring remain NO-GO, while line 207 says D4 and D5 are fully specified and cleared. This matrix therefore authorizes D4/D5 formula/policy libraries, documentation and golden tests where inputs are fully specified, but classifies production D4/D5 rule authoring as requiring clarification. That is a conservative stop, not a new product decision.

## 2. Scoring, state and action components

| Component | Contract basis | Classification | Authorized boundary / required gate |
|---|---|---|---|
| D2 severity coefficients (`critical=3`, `high=2.5`, `medium=2`, `low=1.5`, `info=1`) | D2 Implementation Detail | **IMPLEMENT NOW** | Use exactly these coefficients. |
| D2 per-rule pass rate and severity-weighted domain formula | D2 Implementation Detail | **IMPLEMENT NOW** | A record may contribute to multiple rule observations. Preserve that counting model and label it accurately. |
| D2 applicable/measurable-domain normalization | D2 Implementation Detail | **IMPLEMENT NOW** | Unmeasurable PII/Access and Automation Health domains are excluded, not scored as zero. |
| D2 production overall-score publication while D12 is unresolved | D2 carry-forward plus D12 unresolved | **REQUIRES PRODUCT APPROVAL** | D12 must be resolved and D2 revalidated. Choose neither inclusion nor exclusion now. |
| D2 overall score with D12 silently omitted | D2 carry-forward says revalidate after D12 | **DO NOT IMPLEMENT** | This is the architecture behavior that was removed during remediation. |
| Zero-eligible-rule calculation/applicability behavior | D2 does not specify it | **REQUIRES PRODUCT APPROVAL** | Do not choose exclusion, zero, or another displayed result. Engineering may test numerical options only. |
| Internal numeric precision and rounding that preserves D2 semantics | D2 fixes formula, not representation | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Golden-test deterministic arithmetic. Any customer-facing rounding or copy not already approved remains UI/product-gated. |
| D4 `properPct = proper records / that user's records` | D4 Product Requirement and Implementation Detail | **IMPLEMENT NOW** | Keep it distinct from D2 quality scoring and label it “Percent clean.” |
| D4 coaching bands operating on `properPct` | D4 Implementation Detail | **IMPLEMENT NOW** | Only the already-authoritative band definitions may be used; do not infer missing thresholds. |
| D4 numeric minimum-record floor | D4 says “existing minimum-record floor” but gives no value | **REQUIRES PRODUCT APPROVAL** | The numeric value must be incorporated into or explicitly confirmed under the product authority before production user scoring. |
| D4 threshold editability/read-only UI | D8 unresolved | **REQUIRES PRODUCT APPROVAL** | Do not infer configurability from the prior widget. |
| Durable D4 per-user persistence | D7 tuple omits user dimensions/tokens | **REQUIRES PRODUCT APPROVAL** | No opaque user token or user aggregate may be persisted under the current approval. |
| D4 production rule authoring | Contract Section 5 lines 205 and 207 conflict | **REQUIRES PRODUCT APPROVAL** | Clarify/re-issue the go/no-go statement first. Formula code and fully specified tests may proceed; production authoring may not. |
| Six terminal record states and D3 precedence | D3 carried forward: `proper < incomplete < inaccurate < suspicious < suspected_duplicate < confirmed_duplicate` | **IMPLEMENT NOW** | Apply this exact order and retain underlying rule IDs. |
| D6 blank-phone exclusion in repeated-value grouping | D6 carried-forward implementation fix | **IMPLEMENT NOW** | Blank phone values must not form a repeated-value group. |
| D16 suspected-to-review and confirmed-to-merge routing | D16 carried-forward implementation fix | **IMPLEMENT NOW** | `merge-duplicates` is for confirmed duplicates only. |
| D16 combined-selection action-gain calculation | D16 carried-forward implementation fix | **IMPLEMENT NOW** | Rescore the combined selected changes once; never sum independent gains. |
| D10 Fix-tab presentation of actions/gains | D10 unresolved | **REQUIRES PRODUCT APPROVAL** | Backend calculations do not authorize the screen behavior. |
| D17 per-run API statistics reset and failed-call count | D17 carried-forward implementation fix | **IMPLEMENT NOW** | Reset per scan and surface failed calls on the running screen, without inventing other D10 screen behavior. |

## 3. Duplicate detection components

| Component | Contract/spec basis | Classification | Authorized boundary / required gate |
|---|---|---|---|
| D5 within-module-only v1 scope | D5.2 | **IMPLEMENT NOW** | Leads, Contacts, Accounts and Vendors are not compared across modules. |
| Exact strong-identifier direct confirmation | D5.1 | **IMPLEMENT NOW** | Exact match only. |
| Exact email plus exact phone direct confirmation | D5.1 | **IMPLEMENT NOW** | Both fields must agree exactly. |
| Exact email plus fuzzy-name direct-confirmation shortcut | D5.1 explicitly removes it | **DO NOT IMPLEMENT** | The pair falls through to the standard confidence policy. |
| Standard confirmation threshold | D5.1 | **IMPLEMENT NOW** | Confidence `>=0.90` plus two exact strong-field agreements. |
| Suspected duplicate band `[0.70, 0.90)` | D5.1 and D16 | **IMPLEMENT NOW** | Route this stated interval to human review. |
| Pair with confidence `>=0.90` but fewer than two exact strong-field agreements | D5 requires both conditions for confirmation but does not explicitly assign the fallback terminal state | **REQUIRES PRODUCT APPROVAL** | Do not infer suspected, proper or another state unless the authoritative existing spec explicitly resolves this edge. |
| Normalized-name first-eight-character `|nm|` blocking key | D5.4 | **IMPLEMENT NOW** | Keep and formally document it. Raw blocking keys must remain transient under D7. |
| Oversized block behavior | D5.3 | **IMPLEMENT NOW** | Blocks above 40 must be split deterministically with no missed comparisons. |
| Fixed 40-record chunks plus complete cross-chunk matrix | D5.3 leaves splitting mechanics to engineering | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove all pair coverage, stable ordering, idempotency and feasible runtime. Another deterministic no-loss strategy may be used without changing product policy. |
| Identity/version of the “spec §6.7” incorporated by D5 | D5 references spec §6.7 but the contract does not pin a filename/version | **REQUIRES PRODUCT APPROVAL** | Confirm which existing specification/version is authoritative before importing spec-only mechanics. This matrix does not declare `reverse-engineered-spec.md` authoritative by itself. |
| Signature normalization defined only in a confirmed authoritative spec §6.7 | D5.1/D5.4 incorporate the standard-rule/spec direction | **IMPLEMENT NOW** | Once the authoritative file/version is confirmed, use only its exact definitions. Do not substitute architecture-invented normalization. |
| Field weights and confidence denominator defined only in a confirmed authoritative spec §6.7 | Contract's standard-rule reference | **IMPLEMENT NOW** | Once the authoritative file/version is confirmed, freeze its exact documented values/formula in golden fixtures, subject to the Section 5 production-authoring inconsistency. |
| Exact strong-field set defined only in a confirmed authoritative spec §6.7 | Contract D5.1 plus its standard-rule reference | **IMPLEMENT NOW** | Once the authoritative file/version is confirmed, use only that set; do not add plausible fields. |
| Fuzzy string-similarity algorithm where no authoritative definition exists | Contract/spec describe a `0–1` similarity but do not define the algorithm in the reviewed text | **REQUIRES PRODUCT APPROVAL** | Do not select Levenshtein, Jaro-Winkler, token similarity or another implementation silently. |
| Any additional field, normalization, weight, blocking key or shortcut absent from the contract/authoritative spec | Not specified | **REQUIRES PRODUCT APPROVAL** | No architecture default is authorized. |
| Persisted raw/HMAC/digested signatures or blocking keys | D7 excludes blocking-key raw values and does not approve derivatives | **DO NOT IMPLEMENT** | Keep source signatures/keys transient; no durable index or queue payload. |
| Batch-pair re-read duplicate execution plan | Engineering mechanism for D5 completeness under D7 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove exact record re-fetch, visibility consistency, API cost, crash recovery and no durable key leakage. |
| Deterministic representative-partner tie-break | Not product-specified; may be internal if it changes no state/evidence | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | May be used only as a lossless internal/display ordering rule. If it hides pairs or changes user-visible meaning, product approval is required. |
| D5 production detector/rule authoring | Contract Section 5 lines 205 and 207 conflict | **REQUIRES PRODUCT APPROVAL** | Clarify/re-issue the go/no-go statement first. Policy documentation and explicitly specified golden tests may proceed. |

## 4. D7 persistence, privacy and export components

| Component | Contract basis | Classification | Authorized boundary / required gate |
|---|---|---|---|
| Rich facts in active browser-session memory | D7 Implementation Detail | **IMPLEMENT NOW** | Clear them at session end; never export or persist them. |
| Rich facts in backend worker memory | D7 says “active session” but does not define server-worker scope | **REQUIRES PRODUCT APPROVAL** | Engineering may verify ephemeral controls, but product/privacy must confirm that a worker operation qualifies. |
| Persisted/exported record tuple | D7 Implementation Detail | **IMPLEMENT NOW** | Record ID, module, state, rule/reason IDs, and duplicate confidence/partner reference only. |
| Persisted/exported names, labels, stages, source values or value-bearing reason text | D7 expressly forbids them | **DO NOT IMPLEMENT** | Applies to Data Store, object storage, queues, logs, traces, errors and exports. |
| Persisted raw duplicate blocking keys | D7 expressly excludes them | **DO NOT IMPLEMENT** | Includes normalized email, phone and statutory-ID key values. |
| `scan_id`/`batch_id` linkage inside the approved record tuple | Not listed by D7 | **REQUIRES PRODUCT APPROVAL** | Approve an exact record-to-job linkage mechanism before production persistence. |
| Connection/job operational metadata | Needed by D13/D14/TZ-1 but not exempted by D7's literal wording | **REQUIRES PRODUCT APPROVAL** | Approve each class, field, purpose, access, retention and deletion rule. |
| Encrypted OAuth refresh-token persistence | D14 requires an org connection, but D7's persistence boundary is literal and token storage details are not approved | **REQUIRES PRODUCT APPROVAL** | Security feasibility can be tested with synthetic credentials; production storage awaits D7 boundary approval. |
| `AggregateContribution` rows | Not in D7 tuple | **REQUIRES PRODUCT APPROVAL** | No production table is authorized. |
| Opaque/hashed/keyed user tokens | Not in D7 tuple | **REQUIRES PRODUCT APPROVAL** | Pseudonymization does not create approval. |
| Persisted user/time/domain/rule aggregates or `ScanAggregate` | Not in D7 tuple | **REQUIRES PRODUCT APPROVAL** | Approve exact schemas and purposes before implementation. |
| Durable generated export files | D7 retention duration is unresolved | **REQUIRES PRODUCT APPROVAL** | Streaming a minimized export is allowed; retaining generated files is not. |
| Minimized streaming record export | D7 explicitly governs CSV/export minimization | **IMPLEMENT NOW** | Fixed allowlist only; no arbitrary CRM fields or user tokens. |
| Aggregate/user/time exports | Exact minimized forms not approved by D7 | **REQUIRES PRODUCT APPROVAL** | Remain disabled. |
| TTL, deletion triggers and audit-log retention | D7 expressly leaves them open | **REQUIRES PRODUCT APPROVAL** | No production default or connection-deletion behavior may be inferred. |
| Production `DELETE /connections/{id}` data-deletion semantics | Depends on unresolved D7 deletion trigger/retention | **REQUIRES PRODUCT APPROVAL** | Revoking access for security can be designed separately; data deletion/preservation behavior is not authorized. |

## 5. D13 extraction, jobs and aggregation components

| Component | Contract basis | Classification | Authorized boundary / required gate |
|---|---|---|---|
| Durable server-side date-bounded batch/job model | D13 Product Requirement | **IMPLEMENT NOW** | Replace best-effort browser pagination. |
| Persist every batch result for checkpoint/resume/audit | D13 Implementation Detail | **IMPLEMENT NOW** | The persisted shape must separately comply with D7; D13 does not override D7. |
| Remove the “stop after more than 25 older records” collector heuristic | D13 Implementation Detail | **IMPLEMENT NOW** | It must not remain the primary collector. |
| Bulk Read versus COQL collector selection | D13 gives examples and requires capability confirmation | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify scopes, limits, date criteria, paging, result expiry, credits, latency and module coverage. Read-only OAuth remains mandatory. |
| Bulk/audit collector requiring a `CREATE`-named OAuth scope | D14-POLICY authorizes explicit read scopes only | **DO NOT IMPLEMENT** | Use a read-only alternative or obtain a contract amendment. |
| Exact watermark/page-token/resume semantics | D13 leaves them to engineering | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove no skipped/double-counted records and recovery after token/job expiry. |
| Lease, compare-and-set, staging and idempotency mechanics | Engineering mechanism supporting D13 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove Catalyst transaction/conditional-update and scheduler semantics first. |
| Batch and scan internal state machines | Engineering mechanism supporting D13 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Internal state names may be implemented after transition/crash tests; they do not authorize D10 UI labels. |
| Count/checksum/successor-page completion fence | D13 requires verifiable completeness | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove provider/parsed/unique/persisted reconciliation against sandbox fixtures. |
| Final calculation from persisted verified batch results | Engineering architecture required by the approved D13 direction and migration constraint | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove reproducibility from a D7-approved persisted representation; never use transient browser state. |
| Final calculation from transient browser/worker state | Conflicts with D13 durable persisted-batch requirement | **DO NOT IMPLEMENT** | No authoritative result may depend on transient state. |
| Automatic prior-period/trend extraction | D13 does not mandate it; D10 Trend behavior is unresolved | **REQUIRES PRODUCT APPROVAL** | Include prior periods only in an independently approved scan scope. |
| Null/malformed selected-clock handling | D13 explicitly leaves it to engineering | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify detectability and fail-closed mechanics. Any user-visible presentation remains D10-gated. |
| Scan cancellation initiated by an operator | Not specified by the contract | **REQUIRES PRODUCT APPROVAL** | Internal safe stop on token revocation/security failure may be engineered; a product cancel feature is not authorized. |

## 6. D14 authorization and visibility components

| Component | Contract basis | Classification | Authorized boundary / required gate |
|---|---|---|---|
| Explicit CRM-admin-authorized organization connection | D14-POLICY | **IMPLEMENT NOW** | Separate it from an operator's personal widget login. |
| Organization-specific server-side OAuth authorization-code flow | D14-POLICY direction; exact mechanism needs API proof | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify organization binding, callback/state handling, token refresh/revocation and DC endpoints. |
| Explicit least-privilege read-scope manifest and admin disclosure | D14-POLICY | **IMPLEMENT NOW** | Scope per selected product/module; do not add `.ALL`, create, write, delete or mutation scopes. |
| Positive CRM Administrator-status verification | Required by D14-POLICY; API signal not proven | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Connection must not be treated as admin-authorized based solely on an application role. |
| Requested-versus-granted scope introspection | D14-EVIDENCE item 2 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify whether runtime introspection exists and how missing capability is detected. |
| D14-EVIDENCE sandbox test harness and evidence collection | D14-EVIDENCE plan is explicitly defined | **IMPLEMENT NOW** | Execute visible-vs-total, scope, sharing, territory and role tests now using a realistic sandbox. Evidence collection is not the production connection implementation. |
| Claim of guaranteed org-wide visibility before evidence | D14-EVIDENCE explicitly forbids this assumption | **DO NOT IMPLEMENT** | Admin authorization alone is insufficient proof. |
| Production visibility assurance levels/criteria | D14-EVIDENCE results are not yet known | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Define criteria from actual evidence; do not allow `ACTIVE_VISIBILITY_TESTED` merely because OAuth succeeded. |
| Detection/reporting of incomplete visibility | D14-EVIDENCE requires gaps to feed back into implementation | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Determine reliable signals first. Exact warning/partial-result UI remains D10-gated. |
| Comparison incompatibility between prior user-scoped and new org-identity scans | D14-POLICY Implementation Detail | **IMPLEMENT NOW** | Clearly label them as not directly comparable. |
| User-facing partial-score/count presentation | D10 unresolved | **REQUIRES PRODUCT APPROVAL** | Backend may record incomplete status; screen behavior is not authorized. |

## 7. TZ-1 components

| Component | Contract basis | Classification | Authorized boundary / required gate |
|---|---|---|---|
| Retrieve CRM organization timezone at scan setup | TZ-1 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Behavior is approved; verify Organization API values and supported DC/edition mappings. |
| Apply the organization timezone to burst, off-hours and fiscal-adjacent calculations | TZ-1 | **IMPLEMENT NOW** | Never use operator/browser/server timezone as a silent substitute. |
| Immutable timezone snapshot and UTC range conversion | Engineering design supporting TZ-1 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Golden-test DST gaps/overlaps, boundaries and IANA mapping. Persistence of the snapshot remains D7-gated. |
| Silent browser/Catalyst/server timezone fallback | Conflicts with TZ-1 | **DO NOT IMPLEMENT** | If timezone cannot be established, do not silently evaluate with another zone. |
| Genuine module close/audit timestamp where available | TZ-1 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify the authoritative field or audited transition per module and required API permissions. |
| `Modified_Time` as explicitly disclosed approximation when no genuine timestamp exists | TZ-1 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify genuine-source absence and `Modified_Time` availability, then apply the mandatory disclosure. |
| Silent `Modified_Time` substitution | TZ-1 expressly forbids an undisclosed proxy | **DO NOT IMPLEMENT** | Approximation disclosure is mandatory. |
| Skip a close-time rule merely because no genuine timestamp exists while `Modified_Time` is available | Conflicts with TZ-1 fallback requirement | **DO NOT IMPLEMENT** | Use the disclosed approximation. `UNAVAILABLE` applies only if neither source can be accessed. |
| User-facing wording/location of approximation disclosures | TZ-1 requires disclosure but D10 screens remain unresolved | **REQUIRES PRODUCT APPROVAL** | The disclosure must exist; its exact screen behavior/copy placement needs approval unless already specified elsewhere in the contract. |

## 8. Unresolved product-decision components

| Decision/component | Contract status | Classification | Required treatment |
|---|---|---|---|
| D8 threshold configurability UI | Not approved | **REQUIRES PRODUCT APPROVAL** | Do not choose editable, deferred or read-only behavior. |
| D9 setup cost/runtime estimate | Not approved | **REQUIRES PRODUCT APPROVAL** | Actual backend telemetry may be collected, but must not become a promised estimate or label. |
| D10 Modules screen gaps | Not approved | **REQUIRES PRODUCT APPROVAL** | No architecture/API capability implies screen authorization. |
| D10 Users screen gaps | Not approved | **REQUIRES PRODUCT APPROVAL** | D4 formula approval does not approve user-screen persistence or behavior. |
| D10 Trend screen gaps | Not approved | **REQUIRES PRODUCT APPROVAL** | No automatic prior-period extraction or persisted time aggregates. |
| D10 Records screen gaps | Not approved | **REQUIRES PRODUCT APPROVAL** | D7 tuple approval does not define the record-screen experience. |
| D10 Fix screen gaps | Not approved | **REQUIRES PRODUCT APPROVAL** | D16 calculation/routing does not define the UI. |
| D12 Configuration Hygiene definition/scope/weight interaction | Not approved | **REQUIRES PRODUCT APPROVAL** | No evaluator, slice, weight, inclusion or exclusion behavior may be selected. Revalidate D2 afterward. |
| D15-KNOB `maxExamplesPerRule` | Not approved | **REQUIRES PRODUCT APPROVAL** | Neither implement nor remove it; do not disguise another engineering limit as this knob. |

## 9. Cross-cutting architecture components

| Component | Contract basis | Classification | Authorized boundary / required gate |
|---|---|---|---|
| React client as control/presentation surface; server owns tokens/jobs/results | Supports D13/D14 security boundary | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify Catalyst authentication, CSRF, tenant isolation and server-only table access. D10 still controls missing screens. |
| Tenant/org authorization checks on every API/storage/job operation | Required to preserve D14 organization isolation | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove ownership enforcement and multi-tenant isolation before production. |
| Token/secret encryption and key rotation | Security mechanism needed for D14 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Verify the actual Catalyst secret/key facility with synthetic credentials; production persistence remains D7-gated. |
| Raw CRM payloads or Bulk Read files in durable object storage | Conflicts with D7 minimization | **DO NOT IMPLEMENT** | Stream or use only an approved ephemeral mechanism. |
| Ephemeral worker storage | Supports D7 if it is truly non-durable | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Prove lifecycle/clearing; server-worker rich-memory use also requires D7 product/privacy approval. |
| Provider retry/backoff/circuit-breaker mechanics | Engineering mechanism supporting D13/D17 | **IMPLEMENT AFTER TECHNICAL VERIFICATION** | Configure per provider operation after rate-limit/retry tests; do not treat these as D8 rule thresholds. |
| Application UI for connection, progress, results, warnings, cancellation and exports | Only some underlying behaviors are approved; D10 is unresolved | **REQUIRES PRODUCT APPROVAL** | Implement only already-existing/explicitly approved surfaces after mapping each element; do not infer missing screen behavior from endpoints. |

## 10. Authorization summary

Engineering may immediately implement contract-exact libraries, schemas limited to the literal D7 record tuple, policy documentation, golden fixtures with fully specified inputs, D14-EVIDENCE test tooling, and the explicit prohibitions in this matrix.

Engineering may run sandbox/synthetic feasibility work for Catalyst jobs, OAuth/admin proof, visibility, collectors, timestamps, duplicate batching, encryption and numeric determinism. Those components do not become production-authorized merely because a spike succeeds.

Production persistence remains blocked by D7 decisions about operational metadata/linkage, aggregates, server-worker memory and retention. Production org-wide visibility claims remain blocked until D14-EVIDENCE is completed. Production overall-score publication remains blocked by D12. D8, D9, D10 and D15-KNOB remain wholly unresolved. The D4/D5 production-authoring inconsistency in the contract must be clarified before those rule implementations are authorized for production.
