# Functional Specification Document (FSD)

**Product name:** CRM Data Health Scanner  
**Application type:** Standalone Catalyst + React application  
**Document type:** Functional Specification / Functional Requirements Specification  
**Status:** Describes the system **as implemented** in this repository  
**Version:** 1.0  
**Date:** 20 September 2026  
**Classification:** Internal product and engineering specification  

---

## Document control

| Item | Value |
|---|---|
| Document ID | FSD-CRM-DH-001 |
| Title | CRM Data Health Scanner — Functional Specification |
| Source of truth | This repository’s implemented code, APIs, Data Store usage, tests, and Catalyst configuration |
| Supersedes (for this application) | `docs/functional-specification.md` (Zoho widget reverse-engineering; **not** the standalone app) |
| Does not supersede | `docs/approved-product-contract.md` and `docs/product-decision-register.md` as product-policy records. Where those documents approve rules that the current engine does **not** implement, this FSD states the **implemented** behavior and lists the gap under limitations. |
| Change authority | Product + engineering. This document must be updated when implemented behavior changes. |

**Revision history**

| Version | Date | Description |
|---|---|---|
| 1.0 | 2026-09-20 | Initial FSD of the standalone Catalyst application (Zoho CRM and Salesforce CRM). |

**Requirement ID convention**

| Prefix | Area |
|---|---|
| FR-AUTH | Application authentication |
| FR-CON | CRM connection management |
| FR-ZO | Zoho CRM |
| FR-SF | Salesforce CRM |
| FR-SCN | Scan lifecycle |
| FR-WRK | Workers / asynchronous processing |
| FR-EXT | Extraction |
| FR-DQ | Data quality |
| FR-ANL | Analytics / scoring |
| FR-RPT | Reports |
| FR-FIX | Fix plan |
| FR-SEC | Security / privacy |
| FR-NFR | Non-functional |

Status values used on requirements: **Implemented**, **Partial**, **Not implemented**.

---

## 1. Introduction

### 1.1 Purpose

This document specifies the **currently implemented** functions of the CRM Data Health Scanner: what users can do, how scans run, how quality is measured, what is stored, and what is reported.

It is written so a reader who has never seen the application can understand the product without reading source code. Implementation detail appears only where it explains behavior, integration, reliability, security, data, or constraints.

### 1.2 Scope

**In scope (implemented):**

- Catalyst application authentication
- Connecting Zoho CRM and Salesforce CRM
- Creating, running, viewing, trending, and deleting scans
- Provider-specific extraction (Zoho Bulk Read; Salesforce Bulk API 2.0 Query)
- File Store persistence of exports
- Batch data-quality processing
- Reports: Overview, Users, Modules, Trend, Records, Fix
- Historical scan list owned by the authenticated application user

**Out of scope (not claimed as current product capability):**

- HubSpot or any CRM other than Zoho CRM and Salesforce
- Writing or updating CRM records
- Role-based access control (RBAC) inside the application
- Automated remediation in the CRM
- Configuration / PII / automation domain scoring (stored as not applicable)
- Duplicate pair confirmation as a first-class record state in the listing API
- Quarter / fiscal-year scan windows (UI shows them; API rejects them)

### 1.3 Intended audience

Business stakeholders, product managers, business analysts, developers, QA, data engineers, CRM administrators, and future maintainers.

### 1.4 Product overview

CRM Data Health Scanner is a **read-only diagnostic application**. An authenticated Catalyst user connects a CRM, chooses modules/objects and a time window, and runs a **scan**. The system extracts records from the CRM, evaluates completeness and validity (and additional domain metrics where the engine can measure them), stores aggregates and sample findings, and presents a report.

It is a **standalone web application**, not the original Zoho CRM embedded widget. The widget remains a visual/UX reference only.

**Currently supported CRM providers**

| Provider | Status |
|---|---|
| Zoho CRM | Implemented |
| Salesforce CRM | Implemented |
| HubSpot and others | Not implemented (future) |

### 1.5 Definitions and acronyms

| Term | Meaning in this product |
|---|---|
| Application user | The person signed into Catalyst. Identity comes from Catalyst Authentication, not from the CRM. |
| Connected CRM user | The CRM login identity stored on the connection (name/email of the person who authorized OAuth). |
| CRM record owner | The owner of a CRM record (`Owner` in Zoho; `OwnerId` in Salesforce). May be a user, or in Salesforce a Queue/Group. |
| Connection | A persisted OAuth link to one CRM org/user for one application user. |
| Active connection | The single connection currently selected for new scans (exclusive across Zoho and Salesforce). |
| Module / object | Zoho: module API name (e.g. `Accounts`). Salesforce: sObject API name (e.g. `Account`). |
| Scan | One durable analysis job (`scan_jobs`) for a connection, clock, range, depth, and module set. |
| Module run | Per-module progress row (`scan_module_runs`). |
| Bulk job | One provider extract job persisted in `bulk_read_jobs` (Zoho Bulk Read or Salesforce Query). |
| Pipeline task | Durable worker instruction (`pipeline_tasks`). |
| Finding | A stored quality issue on a CRM record (`record_quality_findings` / `record_quality_issues`). |
| Analytics result | Persisted aggregate JSON for a module/metric (`analytics_results`). |
| Report | The UI for a **completed** scan. |
| File Store | Catalyst File Store folder holding extract files. |
| DQ | Data quality. |
| OAuth | Authorization protocol used to connect CRMs. |
| SOQL | Salesforce Object Query Language. |
| Bulk Read | Zoho CRM bulk export API. |
| Bulk API 2.0 Query | Salesforce asynchronous query job API. |
| PKCE | Proof Key for Code Exchange, used on Salesforce authorization. |
| ZCQL | Catalyst Data Store query language. |

### 1.6 References

| Document / artifact | Role |
|---|---|
| This repository | Implemented behavior |
| `react-app/src/data/client.js` | Frontend API contract |
| `functions/ai_data_analytics_function/api/router.py` | HTTP API routes |
| `docs/approved-product-contract.md` | Product policy approvals (may exceed current engine) |
| `docs/product-decision-register.md` | Decision history |
| `catalyst.json` | Catalyst project packaging |

---

## 2. Business context

### 2.1 Problem

CRM records accumulate missing fields, invalid values, stale activity, unassigned or inactive owners, and inconsistent identity data. Operators need a **repeatable, read-only** way to measure that quality without installing a CRM widget or writing back to the CRM.

### 2.2 Goals (as implemented)

- Connect Zoho CRM or Salesforce CRM with OAuth.
- Extract selected modules/objects for a time window.
- Score completeness, validity, and additional domains when measurable.
- Show which modules and which owners contribute to poor quality.
- Provide a **manual** fix plan (recommendations), not CRM writes.
- Keep prior scans for history and trend.

### 2.3 Non-goals (current)

- Multi-tenant consulting RBAC
- Writing to CRM
- Billing / commercial packaging inside the app
- Generic “any CRM” connector framework

---

## 3. Actors and user roles

The application does **not** implement named roles (admin, analyst, viewer). Anyone who can authenticate to Catalyst and own connections can use the full implemented surface.

| Actor | How they appear | What they can do |
|---|---|---|
| Application user | Catalyst authenticated user (`user_id`) | Connect CRMs, run scans, view/delete own scans and reports |
| Connected CRM user | Stored on `zoho_connections` / `salesforce_connections` | Identity of the OAuth grant; not a login to this app |
| CRM record owner | Zoho `Owner` / Salesforce `OwnerId` | Subject of Users-tab analytics; not an application login |
| CRM organization | Zoho org id/name or Salesforce Organization | Tenant of extracted data |
| Zoho CRM / Salesforce | External systems | Source of records via APIs |

**FR-AUTH-001** — The system shall treat Catalyst Authentication as the only application identity.  
**Status:** Implemented.  
CRM OAuth does not log the user into the application. Application login does not grant CRM API access until a connection exists.

---

## 4. System overview

### 4.1 Logical architecture

```
Application user
  → Catalyst Authentication
  → React application
  → HTTP Function (control plane)
       → scan create / OAuth / reports / history
       → pipeline_tasks
  → Provider Job Function
       → Zoho worker  or  Salesforce worker
       → CRM extract APIs
       → File Store
       → batch DQ processing
       → analytics_results / findings
  → React report
```

Three independently deployed Catalyst functions:

| Function | Type | Role |
|---|---|---|
| `ai_data_analytics_function` | Advanced I/O (HTTP) | APIs, OAuth, scan control, reports |
| `ai_data_analytics_worker` | Job Function | Zoho extract + DQ |
| `ai_data_analytics_salesforce_worker` | Job Function | Salesforce extract + DQ |

Job pools (configured on the HTTP function):

- Zoho: `ANALYTICS_WORKER_JOB_POOL_NAME` / `ANALYTICS_WORKER_FUNCTION_NAME` (defaults in config: `aiDataAnalyticsWorkerPool` / `ai_data_analytics_worker`)
- Salesforce: `SALESFORCE_WORKER_JOB_POOL_NAME` / `SALESFORCE_WORKER_FUNCTION_NAME` (defaults: `sfDataAnalyticsWorkerPool` / `ai_data_analytics_salesforce_worker`)

### 4.2 Navigation map (actual routes)

```
Catalyst login (/__catalyst/auth/login on 401/403)
        ↓
   /                 Setup (new scan)     default landing
   /connect          Connect to CRM
   /scans            Reports (history)
   /scans/{scanId}   Running scan
   /scans/{scanId}/report   Report (completed scans)
```

Phases in client state: `boot` → `home` | `setup` | `connect` | `running` | `report` | `error`.

### 4.3 Provider boundary

Extraction stays **provider-native** (Zoho field names vs Salesforce field names). Downstream reporting uses stored aggregates and findings. The system does **not** rename Salesforce `Opportunity` to Zoho `Deals` or Salesforce `CreatedDate` to `Created_Time`.

Some quality **policies** in the processing engine are still keyed by Zoho module/field names. Salesforce objects therefore do not receive every Zoho-named business-critical or duplication rule. That is documented in §12 and §20.

---

## 5. Core concepts

1. **Data Health application user** — Catalyst user who owns connections and scans.
2. **CRM connection** — Stored OAuth credentials and org identity for one provider.
3. **Active CRM connection** — The one connection with `is_active = true` for that user across **both** provider tables.
4. **Connected CRM user** — Name/email of the CRM identity that granted OAuth.
5. **CRM record owner** — Owner of each extracted record.
6. **CRM organization** — Zoho org or Salesforce Organization.
7. **CRM module/object** — Extract unit.
8. **Scan** — One analysis of selected modules in a window.
9. **Module scan** — One module’s extract + process lifecycle.
10. **Bulk extraction job** — Provider job row in `bulk_read_jobs`.
11. **Pipeline task** — Worker unit of work.
12. **Data-quality finding** — Record with missing/invalid issues.
13. **Analytics result** — Module-level aggregate.
14. **Report** — UI over completed scan analytics.
15. **Historical scan** — Prior `scan_jobs` for the user’s connections.

---

## 6. Application authentication

### 6.1 Entry

The React app loads and calls connection and scan-history APIs with same-origin credentials.

**FR-AUTH-002** — If an API returns HTTP 401 or 403, the client shall redirect the browser to Catalyst login at `{origin}/__catalyst/auth/login`.  
**Status:** Implemented.

**FR-AUTH-003** — HTTP APIs shall obtain the current user from Catalyst Authentication (`get_current_user`) and shall not trust client-supplied user-id headers.  
**Status:** Implemented. Inactive Catalyst users are rejected.

There is no in-app username/password form.

### 6.2 Authorization model

Scans and reports are authorized by **ownership of the CRM connection** that created the scan. There is no intra-app RBAC.

---

## 7. CRM connection management

### 7.1 Shared active-connection model

**FR-CON-001** — The system shall allow an application user to hold multiple Zoho and Salesforce connections, and shall keep **at most one** connection active across both providers.  
**Status:** Implemented (`activate_exclusive_connection`).

Activation of one row sets `is_active = true` and `last_selected_at`, and clears `is_active` on every other Zoho and Salesforce row for that user. On failure, previous actives are restored.

The UI connection key is `{provider}:{connectionId}` (e.g. `salesforce:48465…`).

**FR-CON-002** — New scans shall use the exclusive-active connection. If both a Zoho and a Salesforce row are marked active (data anomaly), scan create prefers the later `last_selected_at` / ROWID.  
**Status:** Implemented.

**Disconnect / delete connection:** No connection-delete API is implemented. Scan delete does **not** delete the connection.

### 7.2 Zoho CRM connection

**FR-ZO-001** — The system shall connect Zoho CRM using OAuth 2.0 authorization code with `access_type=offline` so a refresh token is issued.  
**Status:** Implemented.

| Step | Behavior |
|---|---|
| Start | `GET /api/zoho/consent` redirects to Zoho Accounts authorize URL |
| Scope | Module, field, user, org, layout, workflow, search, and **bulk.read** scopes (see `ZOHO_SCOPE`) |
| Callback | `GET /api/zoho/callback` exchanges code, stores tokens on `zoho_connections` |
| Status | `connected` |
| Listing | `GET /api/zoho/connection` |
| Activate | `POST /api/zoho/connections/{id}/activate` |
| Token refresh | Uses stored refresh token against Zoho Accounts; updates `access_token` and `token_expires_at` |
| Failure | User is asked to reconnect (`ZOHO_CONNECTION_REQUIRED` / token errors) |

Stored connection fields used in behavior: `user_id`, `access_token`, `refresh_token`, `token_expires_at`, `status`, `is_active`, `last_selected_at`, `zoho_org_id`, `organization_name`, `connected_name`, `connected_email`, `accessible_modules`.

### 7.3 Salesforce CRM connection

**FR-SF-001** — The system shall connect Salesforce using OAuth 2.0 authorization code + PKCE (S256), scope `api refresh_token id`, with `prompt=consent`.  
**Status:** Implemented.

| Step | Behavior |
|---|---|
| Start | `GET /api/salesforce/consent` |
| Login host | `SALESFORCE_LOGIN_URL` (configured `https://login.salesforce.com`) |
| Redirect URI | `SALESFORCE_REDIRECT_URI` (HTTP function `/api/salesforce/callback`) |
| Callback | Exchanges code + `code_verifier`; requires `access_token`, `refresh_token`, and `instance_url` |
| Identity | Salesforce Identity URL for user/org ids and connected name/email |
| Persist | `salesforce_connections` |
| Listing | `GET /api/salesforce/connection` |
| Activate | `POST /api/salesforce/connections/{id}/activate` |
| Token refresh | See FR-SF-002 |
| Metadata | `GET /api/salesforce/metadata` (org + queryable objects) |

**FR-SF-002** — On access-token expiry (or unparsable expiry), the system shall refresh using `grant_type=refresh_token`. If Salesforce returns a new `refresh_token`, the system shall persist it; if omitted, the stored refresh token shall remain. Failed refresh shall not overwrite stored tokens.  
**Status:** Implemented.

Refresh maps HTTP/config failures to `TOKEN_REFRESH_FAILED` (502 on metadata). Missing stored refresh token maps to `REFRESH_TOKEN_MISSING`.

**Config note:** HTTP `catalyst-config.json` in repo includes login URL and redirect URI. `SALESFORCE_CLIENT_ID` and `SALESFORCE_CLIENT_SECRET` must exist in the **live** Catalyst function environment or refresh fails.

**FR-SF-003** — Salesforce owner directory (`Users` and `Group` of type Queue/Regular) shall be cached in `salesforce_connection_owners` at Salesforce scan create, using the same connection as the scan. Sync failure shall not block scan creation.  
**Status:** Implemented in source. Live table population requires the HTTP function that contains this hook to be deployed.

---

## 8. Scan functionality

### 8.1 Creating a scan

**UI:** Setup (`/`) after an active connection.

User selects:

- Modules/objects (from Zoho `accessible_modules` or Salesforce metadata objects)
- Depth: `quick` \| `presales` \| `deep` \| `full` (UI default `presales`)
- Clock: `created` or `modified`
- Range: `7d`, `30d`, `90d`, `all` (UI also shows quarter, FY, and custom; see validation)

**FR-SCN-001** — The system shall create a scan only when at least one accessible module/object is selected, depth is one of the four supported values, clock is created or modified, and range is `7d`, `30d`, `90d`, or `all`.  
**Status:** Implemented.

| Clock | Zoho field | Salesforce field |
|---|---|---|
| created | `Created_Time` | `CreatedDate` |
| modified | `Modified_Time` | `LastModifiedDate` |

Rolling windows are computed in UTC at create time (`now − N days` through `now`). `all` stores no `from_utc` (open start). `qtr` and `fy` raise a validation error requiring organization calendar metadata.

**FR-SCN-002** — The client may persist scan setup in browser local storage (`scan-config-v2`), including a local rule object (`staleDays`, duplicate floors, etc.). The scan-create API shall **not** apply those client rule fields; processing uses server-side policies.  
**Status:** Implemented (client stores; server `validate_scan_config` ignores `rules`).

**FR-SCN-003** — If an equivalent **active** scan already exists for the same connection, modules, clock, depth, and range policy, the system shall reuse it instead of inserting a duplicate plan, and shall still enqueue the provider worker.  
**Status:** Implemented. Active statuses: `CREATED`, `AUTH_VALIDATING`, `DISCOVERING`, `PLANNED`, `EXTRACTING`, `PROCESSING`, `PAUSED_RETRYABLE`.

Create API: `POST /api/scans`.

Zoho create persists `scan_jobs` + `scan_module_runs` then enqueues `ORCHESTRATE_SCAN`.  
Salesforce create sets `crm_provider = salesforce`, builds Salesforce field plans from describe, syncs owner directory, then enqueues `ORCHESTRATE_SALESFORCE_SCAN`.

Cost estimate in Setup is **indicative** (Zoho Bulk Read credit envelope: 50 submit + 1 download per module). It is not a live CRM quote. Salesforce has no separate credit estimator.

### 8.2 Scan state machine

Persisted on `scan_jobs.status`.

| State | Purpose | Typical entry | Exit |
|---|---|---|---|
| `CREATED` | Plan stored; worker not yet through discover | Insert on create | Zoho: discover; Salesforce: worker start |
| `AUTH_VALIDATING` | Zoho token/org check at the start of discover | Discover sets this **before** calling Zoho | Success → `DISCOVERING`; failure → `PAUSED_RETRYABLE` |
| `DISCOVERING` | Zoho field allowlist + user directory sync | After token obtained | Success → `PLANNED` |
| `PLANNED` | Field plans stored; bulk jobs can be prepared | Discover complete | Extract |
| `EXTRACTING` | Provider extract in progress | Bulk submit | Download / process |
| `PROCESSING` | DQ batches running | After download | `COMPLETED` or pause/fail |
| `PAUSED_RETRYABLE` | Recoverable; discover/advance may retry | Token, discover, or worker recoverable failure | Resume |
| `COMPLETED` | All selected modules processed | Last module complete | Terminal success |
| `FAILED_TERMINAL` | Unrecoverable | Provider abort/fail, persist failure | Terminal; Home shows Failed |

**Zoho orchestrate next-action (deterministic, no extra state write by the chooser):**

| Scan / bulk condition | Next action |
|---|---|
| `COMPLETED` | `COMPLETE` |
| `FAILED_TERMINAL` | `BLOCKED` → review failure |
| `CREATED`, `DISCOVERING`, `PAUSED_RETRYABLE` | `DISCOVER` |
| No bulk jobs | `PREPARE_BULK` |
| Bulk `PLANNED` | `SUBMIT_BULK` |
| Bulk `SUBMITTED` or `PROCESSING` without file | `CHECK_BULK_STATUS` |
| `READY_TO_DOWNLOAD` / `DOWNLOAD_RETRYABLE` | `DOWNLOAD_RESULT` |
| `DOWNLOADED` | `PREPARE_BATCHES` (or wait if worker already queued) |
| `PROCESSING_PLANNED` / `PROCESSING` with file | `PROCESS_BATCHES` (or wait) |
| Task `OUTCOME_UNKNOWN` | `BLOCKED` → review worker job |
| All bulk `PROCESSED` | `WAIT_FOR_COMPLETION` |

Salesforce uses a single `ORCHESTRATE_SALESFORCE_SCAN` task that submits **one** Bulk API 2.0 Query job per tick (never resubmitting an existing `provider_job_id`), polls, downloads CSV, then continues into batch prepare/process on the same worker.

Module rows have their own `status` (`PLANNED`, `PROCESSING`, `COMPLETED`, etc.). Bulk jobs use provider-mapped statuses (see §10–11).

**FR-SCN-004** — While a scan is not `COMPLETED` or `FAILED_TERMINAL`, the UI shall show the running screen and poll `GET /api/scans/{id}/status` every 2 seconds. Polling shall not call `/advance`.  
**Status:** Implemented.

**FR-SCN-005** — Resume from Home shall `POST /api/scans/{id}/advance`. For Salesforce, advance shall only enqueue the Salesforce worker. For Zoho, advance shall enqueue the Zoho worker first; if enqueue fails with a known failure (not `WORKER_ENQUEUE_OUTCOME_UNKNOWN`), the HTTP function may perform one inline pipeline step as recovery.  
**Status:** Implemented.

### 8.3 Progress

Status payload includes per-module expected/downloaded/processed counts, bulk job statuses, and task statuses. The running UI lists modules from that payload.

### 8.4 History

**FR-SCN-006** — `GET /api/scans` shall list scans for the current user’s Zoho and Salesforce connections (up to 50 per connection, newest first), including provider and organization labels.  
**Status:** Implemented.

### 8.5 Deletion

**FR-SCN-007** — `DELETE /api/scans/{scanId}` with body `{ "confirmScanId": "<same id>" }` shall delete one owned scan and descendants (findings, issues, owner aggregates, analytics, tasks, batches, bulk jobs, module runs, scan row) and associated File Store objects, and shall **retain** the CRM connection. Deletion shall be rejected (409 `SCAN_DELETE_ACTIVE_TASK`) while pipeline tasks are `QUEUED`, `RUNNING`, or `OUTCOME_UNKNOWN`.  
**Status:** Implemented.

**Cancel API:** `cancel_requested` exists on `scan_jobs`. There is no dedicated user-facing cancel endpoint in the current router.

---

## 9. Worker / asynchronous processing

**FR-WRK-001** — Long-running CRM extraction and DQ shall run in provider-specific Job Functions, not in the HTTP request that created the scan.  
**Status:** Implemented.

### 9.1 Pipeline tasks

Table `pipeline_tasks`. Important types:

| task_type | Worker |
|---|---|
| `ORCHESTRATE_SCAN` | Zoho |
| `PREPARE_BATCHES` | Zoho (also continued from orchestrate) |
| `PROCESS_BATCHES` | Zoho |
| `ORCHESTRATE_SALESFORCE_SCAN` | Salesforce |

Task statuses used in behavior: `PLANNED`, `QUEUED`, `RUNNING`, `SUCCEEDED`, `PAUSED_RETRYABLE`, `OUTCOME_UNKNOWN`.

**Lease:** Workers claim a task to `RUNNING` with `lease_expires_at` (Zoho start uses a 10-minute lease window). Salesforce has explicit already-running / already-complete claim handling.

**Requeue:** Zoho orchestrate may yield and resubmit (immediate or delayed Cron). Salesforce worker requeues poll ticks; it does not resubmit an existing `provider_job_id`.

**Idempotency:** Orchestrate enqueue uses a deterministic `task_key`. Equivalent in-flight scans are reused. Batch checkpoints allow completed batches to be skipped.

**FR-WRK-002** — If Catalyst job submission returns an unknown outcome, the system shall not silently retry as success (`WORKER_ENQUEUE_OUTCOME_UNKNOWN`).  
**Status:** Implemented.

---

## 10. Zoho CRM functionality

**FR-ZO-002** — After scan create, the Zoho worker shall discover module fields, cache Zoho users into `zoho_connection_users`, prepare one Bulk Read job per module, submit, poll, download a ZIP of CSV into File Store, split into 5,000-record batches, and process DQ.  
**Status:** Implemented.

Zoho Bulk Read criteria use the scan clock field and UTC window. Credits: submit 50, download 1, plus status polls (not estimated).

Owner on records: Zoho `Owner` JSON (`id`, `name`). Directory: `zoho_connection_users` keyed by hashed `crm_user_id`.

HTTP still exposes Zoho Bulk step routes (`/discover`, `/prepare-bulk`, `/bulk-jobs/...`). The React client does not call them; they remain part of the HTTP API and Zoho `/advance` fallback.

---

## 11. Salesforce CRM functionality

**FR-SF-004** — Salesforce extraction shall use Bulk API 2.0 Query jobs built from the stored field allowlist and `CreatedDate` / `LastModifiedDate` window, poll until complete, download CSV (locator paging), store the file in File Store, then batch and process. An existing `provider_job_id` shall not be resubmitted.  
**Status:** Implemented.

Salesforce job states are mapped into `bulk_read_jobs.status` (e.g. UploadComplete/InProgress → processing; JobComplete → ready to download; Aborted/Failed → `FAILED_TERMINAL`).

**FR-SF-005** — Field allowlists come from Salesforce describe (quality-relevant fields plus identifiers and `OwnerId`). Object names remain Salesforce-native (`Account`, `Contact`, `Opportunity`, …).  
**Status:** Implemented.

**FR-SF-006** — Owner resolution shall use `OwnerId` against `salesforce_connection_owners`, matching 15- and 18-character Salesforce Ids and case-insensitive 15-character prefixes. Unresolved owners shall display as `Unknown owner`. Unassigned empty owners as `Unassigned`.  
**Status:** Implemented.

**FR-SF-007** — `GET /api/salesforce/directory` and `GET /api/salesforce/objects/{name}/describe` shall remain available HTTP APIs even if the React client does not call them.  
**Status:** Implemented.

Salesforce scan create requires a valid Organization timezone (`TimeZoneSidKey`); missing timezone fails closed (`ORGANIZATION_TIMEZONE_MISSING`). Zoho discover likewise fails closed if organization timezone metadata is unavailable (`ORGANIZATION_TIMEZONE_MISSING`).

---

## 12. Data extraction and normalization

### 12.1 Zoho path

CRM → Bulk Read job → ZIP/CSV → File Store (`BULK_EXPORT_FOLDER_ID`) → 5,000-row `processing_batches` → DQ.

Identifier field: `id`. Time fields: `Created_Time`, `Modified_Time`. Owner: `Owner`.

### 12.2 Salesforce path

CRM → SOQL from field plan → Bulk API 2.0 Query → CSV pages (locator) → File Store (`.csv`) → worker wraps non-ZIP files as a one-member ZIP for processing → batches → DQ.

Identifier: `Id` (also accepted as `id`). Time: `CreatedDate`, `LastModifiedDate`. Owner: `OwnerId`.

### 12.3 Canonical record used in DQ

Per extracted row, processing builds a field map from the **stored allowlist** (case-insensitive CSV headers). Completeness/validity run on those fields. Owner identity is resolved separately. No invented cross-CRM canonical schema is stored as a table of renamed fields.

**FR-EXT-001** — Processing batch size shall be 5,000 records (`batch-plan-v1`).  
**Status:** Implemented.

File size limits in shared constants: File Store upload 100 MB; Zoho uncompressed bulk 1 GB.

---

## 13. Data quality engine

Engine versions stored on results: quality `quality-rules-v1`; domains `phase2-domain-rules-v1`; findings `record-findings-v4` / `record-rules-v3`.

Depth controls **which missing-value findings are emitted**, not which records are extracted.

### 13.1 Completeness (missing values)

**DQ-C-001 SYSTEM_MANDATORY_VALUE_MISSING**  
Purpose: Flag empty system-mandatory fields.  
Severity: HIGH. Depths: all. Source: provider field metadata `systemMandatory`.

**DQ-C-002 UNIQUE_FIELD_VALUE_MISSING**  
Empty unique fields. Severity: HIGH. Depths: all. Metadata `unique`.

**DQ-C-003 BUSINESS_CRITICAL_VALUE_MISSING**  
Empty fields in the hardcoded business-critical set. Severity: MEDIUM. Depths: `presales`, `deep`, `full`.

Zoho module keys currently used:

| Module API name | Fields |
|---|---|
| Leads | First_Name, Last_Name, Full_Name, Company, Email, Phone, Lead_Status, Lead_Source, Industry, Country |
| Contacts | First_Name, Last_Name, Full_Name, Account_Name, Email, Phone, Mailing_Country |
| Accounts | Account_Name, Phone, Industry, Billing_Country |
| Deals | Deal_Name, Account_Name, Stage, Pipeline, Amount, Closing_Date |

Salesforce object API names (`Account`, `Contact`, `Opportunity`) **do not match** these keys, so this business-critical catalog generally does **not** apply to Salesforce unless a module is literally named `Accounts`/`Contacts`/`Deals`/`Leads`.

**DQ-C-004 OPTIONAL_VALUE_MISSING**  
Other writable non-mandatory fields. Severity: LOW. Depths: `deep`, `full` only.

**DQ-C-005 LEGACY_ANALYSIS_VALUE_MISSING**  
Allowlist fields without metadata. Severity: MEDIUM.

Read-only fields: no missing-value finding.

Example: Zoho Contacts scan at `presales` with empty `Email` → finding `BUSINESS_CRITICAL_VALUE_MISSING`, state `incomplete`.

### 13.2 Validity (format)

Applied when a non-empty value is present. Severity: HIGH. Metric group: VALIDITY.

| Rule ID | Detector | Pass | Fail issue |
|---|---|---|---|
| DQ-V-001 | Field name contains `email` | Matches `local@domain` | `INVALID_EMAIL` |
| DQ-V-002 | phone / mobile / fax | 7–15 digits | `INVALID_PHONE` |
| DQ-V-003 | website / url / `*_url` | Host with a dot | `INVALID_URL` |
| DQ-V-004 | Amount, Annual_Revenue, Employees | Parseable number | `INVALID_NUMBER` |
| DQ-V-005 | Name ends with `_time` or `_date` | Parseable datetime | `INVALID_DATETIME` |

Salesforce `CreatedDate` / `LastModifiedDate` do **not** match the `_time`/`_date` suffix rule, so they are not format-validated as datetimes by this detector. Completeness still counts empty vs populated.

### 13.3 Record states (implemented listing)

From findings: `incomplete` if missing issues only; `inaccurate` if any invalid issues. Records with no issues are `proper` (listed from the export when requested). Stored aggregate also reserves `suspicious`, `suspected_duplicate`, `confirmed_duplicate` counts; the Records API lists `incomplete`, `inaccurate`, and `proper` only. Duplicate pair classification from `domain/` is **not** the production listing engine.

### 13.4 Domain metrics (aggregates)

Measured when applicable; otherwise `applicable: false` with a reason.

**Duplication** — For configured identity fields (Zoho `Leads`/`Contacts` Email, `Accounts` Account_Name), score = `100 * (observations − duplicateOccurrences) / observations` using in-memory hashes (values not stored). Salesforce native object names typically yield “no configured identity values”.

**Plausibility** — Non-negative Amount/Annual_Revenue/Employees (Employees integer); Created/Modified not after scan `to_utc`; Created not after Modified. Score = pass rate of those checks. Salesforce time-field names `Created_Time`/`Modified_Time` are the ones counted; Salesforce `CreatedDate`/`LastModifiedDate` are not those keys.

**Freshness** — Age of `Modified_Time` vs scan `to_utc`: 0–90 days → 100 points; 91–180 → 75; 181–365 → 40; over 365 → 0. Score = average points. Frontend `staleDays: 365` is **not** the engine input.

**Integrity** — `OWNER_ASSIGNED`; `OWNER_ACTIVE` if owner id is in the connection directory; `REQUIRED_ACCOUNT_RELATIONSHIP` for Zoho `Contacts`/`Deals` `Account_Name`.

**Config, PII, automation** — Always not applicable in current processing (`applicable: false`, explicit reason strings). They are **excluded from overall score denominator** (not scored as zero).

### 13.5 Finding persistence

Up to **40** sample findings per module are stored. Issues capped per finding. Clean records are **not** persisted as findings; they are re-derived from File Store on Records-tab `proper` listing.

---

## 14. Scoring / analytics

**FR-ANL-001** — Completeness rate = populated cells / (records × fields). Validity rate = (checked − invalid) / checked.  
**Status:** Implemented.

**FR-ANL-002** — Overall and trend scores shall be a **weight-only-on-measured-domains** average:

| Domain | Weight |
|---|---|
| completeness | 20 |
| duplication | 20 |
| validity | 15 |
| plausibility | 10 |
| freshness | 10 |
| integrity | 10 |
| config | 8 |
| pii | 4 |
| automation | 3 |

`score = round( Σ (domainScore × weight) / Σ weights of domains with a numeric score )`

Unmeasured domains (null / not applicable) are omitted from the denominator.

**Owner score (Users / overview):** completeness weight 20 and validity weight 15 only, same weighted-mean pattern. Owners below `minRecordsPerUser` default **25** are treated as needing volume before coaching in overview helpers.

These implemented rates are **not** the severity-weighted per-rule means in `docs/approved-product-contract.md` (D2). That contract remains product policy; the running engine uses the formulas above.

---

## 15. Reporting

Report tabs (sidebar, completed scan): Overview, Users, Modules, Trend, Records, Fix.

Filters: modules and users (owners), plus Overview state focus. Shared `FilterBar`.

### 15.1 Overview — FR-RPT-001

Purpose: org-level health, state breakdown, domain bars, movers vs prior comparable scan, findings list.  
Source: `GET /api/scans/{id}/results` adapted in the client.  
Empty/error: empty notes when metrics missing; boot/report errors use `ErrorState`.

### 15.2 Users — FR-RPT-002

Purpose: quality by CRM **record owner**, not by application user.  
Source: `ownerAnalytics` on results; Salesforce names from `salesforce_connection_owners`.  
Limitation: `Unknown owner` when directory miss or empty table.

### 15.3 Modules — FR-RPT-003

Purpose: per-module scores and field completeness/validity tables.  
Uses stored module API names (Zoho `Accounts` vs Salesforce `Account`).

### 15.4 Trend — FR-RPT-004

Purpose: up to **12** completed scans for the same connection, scored with the same domain weights.  
API: `GET /api/scans/{id}/trend`.  
If history is thin, fewer points; no fabricated history.

### 15.5 Records — FR-RPT-005

Purpose: paginated findings and clean (`proper`) rows.  
API: `GET /api/scans/{id}/records` (page size 20). Filters: states, modules, owners, `q`.  
Zoho may enrich names via CRM record fetch; Salesforce uses export `Name` and strips CRM ids from the payload. Fallback display: `Unnamed record`.

### 15.6 Fix — FR-RPT-006 / FR-FIX-001

Purpose: **read-only remediation plan**.  
API: `GET /api/scans/{id}/fix-plan`.  
`actionType: "manual"` on every action. Maximum **30** returned actions (`omittedActionCount` reports the remainder). Copy states that the application has **not** changed any CRM value.  
Not an automated write-back.

**Ranking (implemented):**

- Invalid-format issues → priority `HIGH`.
- Missing system-mandatory or unique → `HIGH`.
- Missing business-critical → `HIGH` if coverage ≥ 50% of module records, else `MEDIUM`.
- Missing optional → `LOW`.
- Other missing: `HIGH` if the field is in the quality-candidate set and coverage ≥ 50%; `MEDIUM` if quality-candidate or coverage ≥ 25%; else `LOW`.
- Sort: HIGH/MEDIUM/LOW, then `_rank = recordCount × severityWeight × businessWeight` descending (`LOW=1, MEDIUM=2, HIGH=4, CRITICAL=8`; quality-candidate fields ×1.25 else ×0.75).
- Quality-candidate field names (Zoho-oriented, plus `Name`): `First_Name`, `Last_Name`, `Full_Name`, `Company`, `Account_Name`, `Deal_Name`, `Name`, `Email`, `Secondary_Email`, `Phone`, `Mobile`, `Website`, `Industry`, `Lead_Source`, `Lead_Status`, `Stage`, `Pipeline`, `Amount`, `Closing_Date`, `Billing_Country`, `Mailing_Country`, `Country`, `Annual_Revenue`, `Employees`, `Created_By`, `Owner`. Salesforce `OwnerId` is **not** in this set.
- `pointGain` is currently `null`.

Issue copy for missing system-mandatory/unique fields currently says **“Zoho CRM marks this field…”** even when the scan is Salesforce. That wording is implemented, not a second engine.

---

## 16. Record findings (detail)

Each finding includes module, CRM record id (internal; Salesforce id may be omitted from client payload), display name, owner key/name, issue list (field, type, severity), and state `incomplete` or `inaccurate`.

**FR-RPT-007** — Owner names shall come from the provider directory when present; otherwise `Unknown owner` or `Unassigned`.  
**Status:** Implemented.

---

## 17. Historical scans / trending

History is per application user via their connections. Opening a completed scan loads `/scans/{id}/report`. Incomplete scans open the running view. Trend compares completed aggregates only. Deleting a scan removes its history point.

---

## 18. UI / screen specifications

### 18.1 Setup — `/`

Purpose: configure and start a scan.  
Entry: default route; sidebar “New scan”.  
Fields: module checklist, depth, clock, range presets.  
Actions: Start scan → `POST /api/scans` → running route.  
Validation: client + server (FR-SCN-001). Quarter/FY fail on server.  
Requires an active connection; otherwise user is directed to Connect.

### 18.2 Connect — `/connect`

Purpose: start or switch Zoho/Salesforce OAuth; see connection notices (consent declined, refresh failure messaging from hash flags).  
Actions: consent URLs; activate existing connection.

### 18.3 Reports (Home) — `/scans`

Purpose: historical scans, resume, delete (confirm dialog), switch connection.  
Resume: `POST .../advance`. Delete: confirmed DELETE.

### 18.4 Running — `/scans/{scanId}`

Purpose: module progress until `COMPLETED` or `FAILED_TERMINAL`.  
Poll status 2s. On complete, navigate to report.

### 18.5 Report — `/scans/{scanId}/report`

Purpose: six tabs. Sidebar report items enabled only in report phase.

### 18.6 Boot / error

Boot: “Restoring your account”. Error: message + retry (reset).

---

## 19. Inputs and outputs

| Flow | Inputs | Outputs |
|---|---|---|
| Connect Zoho/SF | User consent | Connection row |
| Create scan | modules, depth, clock, range | `scanId`, status `CREATED` |
| Status | scanId | module/bulk/task progress |
| Results | scanId | module metrics, owner analytics |
| Records | scanId, filters, page | findings / proper rows |
| Fix plan | scanId, modules | ranked manual actions |
| Trend | scanId, modules | time series points |
| Delete | scanId + confirm | rows + files removed |

---

## 20. Validation rules (summary)

- JSON body required for create
- ≥1 unique accessible module API names
- Depth ∈ {quick, presales, deep, full}
- Clock ∈ {created, modified}
- Range ∈ {7d, 30d, 90d, all} at API
- Salesforce objects must exist on describe/global and include the clock field
- Salesforce timezone required
- Delete requires matching `confirmScanId`
- List filters: max 50 values, comma-separated (Catalyst query-string constraint)

---

## 21. External interfaces

### 21.1 HTTP API (control plane)

Base (browser): `/server/ai_data_analytics_function`

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/zoho/consent` | Start Zoho OAuth |
| GET | `/api/zoho/callback` | Zoho OAuth return |
| GET | `/api/zoho/connection` | Zoho connection JSON |
| POST | `/api/zoho/connections/{id}/activate` | Activate Zoho |
| GET | `/api/salesforce/consent` | Start Salesforce OAuth |
| GET | `/api/salesforce/callback` | Salesforce return |
| GET | `/api/salesforce/connection` | Salesforce connection JSON |
| POST | `/api/salesforce/connections/{id}/activate` | Activate Salesforce |
| GET | `/api/salesforce/metadata` | Org + objects |
| GET | `/api/salesforce/directory` | Owner directory sync/status |
| GET | `/api/salesforce/objects/{name}/describe` | Object describe |
| GET/POST | `/api/scans` | History / create |
| DELETE | `/api/scans/{id}` | Delete scan |
| GET | `/api/scans/{id}/status` | Progress |
| GET | `/api/scans/{id}/results` | Report payload |
| GET | `/api/scans/{id}/trend` | Trend |
| GET | `/api/scans/{id}/records` | Findings |
| GET | `/api/scans/{id}/fix-plan` | Manual plan |
| POST | `/api/scans/{id}/advance` | Resume/enqueue |
| POST | `/api/scans/{id}/discover` | Zoho discover (API; not used by React) |
| POST | `/api/scans/{id}/prepare-bulk` and `/bulk-jobs/...` | Zoho bulk steps (API; not used by React) |

### 21.2 CRM APIs

Zoho CRM REST + Bulk Read. Salesforce REST (org, describe, User/Group SOQL, token, identity) + Bulk API 2.0 Query.

### 21.3 Catalyst

Authentication, Data Store, File Store, Job Functions / Job Pools.

---

## 22. Data requirements / data dictionary (behavioral)

Catalyst Data Store tables **used by the application** (columns listed are those the code reads/writes; console schema is the physical source):

| Table | Role |
|---|---|
| `oauth_states` | OAuth CSRF/PKCE state, TTL |
| `zoho_connections` | Zoho OAuth + org + modules |
| `salesforce_connections` | Salesforce OAuth + org + instance_url |
| `zoho_connection_users` | Zoho owner directory |
| `salesforce_connection_owners` | Salesforce users/queues/groups |
| `scan_jobs` | Scan plan and status; `crm_provider` |
| `scan_module_runs` | Per-module plan, allowlist JSON, counts |
| `bulk_read_jobs` | Provider extract jobs + File Store ids |
| `processing_batches` | 5k checkpoints |
| `pipeline_tasks` | Worker tasks, lease, attempts |
| `analytics_results` | Aggregates (`summary`, `completeness`, `validity`, `temporal`, `domains`, `record_findings`, owner metrics) |
| `owner_batch_aggregates` | Per-owner batch stats |
| `record_quality_findings` | Sample findings |
| `record_quality_issues` | Finding issues |

File Store: extract ZIP/CSV under `BULK_EXPORT_FOLDER_ID`.

There is **no** migration runner in-repo; tables/columns must exist in the Catalyst console.

---

## 23. Error and exception handling

Representative codes (not exhaustive):

| Code | Typical meaning |
|---|---|
| `AUTHENTICATION_REQUIRED` | No/invalid Catalyst user |
| `ZOHO_CONNECTION_REQUIRED` / `SALESFORCE_CONNECTION_REQUIRED` | Connect CRM |
| `TOKEN_REFRESH_FAILED` / `REFRESH_TOKEN_MISSING` | Reconnect or fix OAuth env |
| `INVALID_SCAN_CONFIG` / `MODULE_NOT_ACCESSIBLE` | Setup validation |
| `ORGANIZATION_TIMEZONE_MISSING` | Salesforce org timezone |
| `SCAN_NOT_FOUND` | Unknown or not owned |
| `SCAN_DELETE_CONFIRMATION_REQUIRED` / `SCAN_DELETE_ACTIVE_TASK` | Delete guards |
| `WORKER_ENQUEUE_OUTCOME_UNKNOWN` | Inspect Job Pool |
| `SALESFORCE_WORKER_ENQUEUE_FAILED` | Salesforce worker queue |
| `FAILED_TERMINAL` (status) | Unrecoverable scan |
| `PAUSED_RETRYABLE` (status) | Resume may work |

Workers persist `controlled_error_code` on tasks. HTTP `/advance` recovery for Zoho is enqueue-first then optional inline step. Salesforce advance is enqueue-only.

---

## 24. Security

**FR-SEC-001** — CRM tokens shall be stored in Data Store connection tables and shall not be returned on connection listing APIs.  
**Status:** Implemented (listing returns org/user labels, not tokens).

**FR-SEC-002** — Findings and logs shall avoid persisting raw CRM field values in duplicate-detection hashes; hashes are process-local. Stored findings keep CRM ids and display names needed for the Records tab.  
**Status:** Implemented as designed in processing.

**FR-SEC-003** — Application auth is Catalyst; CRM auth is OAuth. Scans are scoped to the authenticated user’s connections.  
**Status:** Implemented. No RBAC.

OAuth client secrets belong in Catalyst environment configuration. They must not be committed; live env must still contain Salesforce client id/secret for refresh to work.

Read-only CRM scopes are used; the Fix plan does not call CRM update APIs.

---

## 25. Non-functional requirements (observed)

| ID | Requirement | Status |
|---|---|---|
| FR-NFR-001 | HTTP APIs are synchronous; extracts are asynchronous | Implemented |
| FR-NFR-002 | Status poll interval 2 seconds | Implemented (client) |
| FR-NFR-003 | Records page size 20 | Implemented |
| FR-NFR-004 | Independent deploy of HTTP, Zoho worker, Salesforce worker | Implemented |
| FR-NFR-005 | Shared connector/helper source packaged by `functions/_shared/sync_into_workers.py` | Implemented |

No published SLA/RPO numbers exist in the application.

---

## 26. Assumptions

- Catalyst Authentication, Data Store tables, File Store folder, and both Job Pools exist in the target project.
- The application user is allowed to authorize the CRM Connected App / Zoho client.
- Organization timezones for Salesforce are IANA names Salesforce returns (`TimeZoneSidKey`).
- One active workspace connection is the intended operator model.

---

## 27. Constraints

- Catalyst zips each function separately; functions cannot import each other at runtime.
- ZCQL and reserved words (e.g. `active`) constrain queries (`select *` used for owner directory).
- Query-string list filters are comma-separated because Catalyst may collapse repeated keys.
- No in-repo schema migration.
- Salesforce refresh-token rotation is last-write-wins (no compare-and-set).

---

## 28. Dependencies

- Zoho CRM APIs and Zoho Accounts OAuth
- Salesforce OAuth, REST, Bulk API 2.0
- Zoho Catalyst (Auth, Functions, Data Store, File Store, Job Pool)
- React (Vite) hosted as Catalyst client

---

## 29. Current limitations

1. Only Zoho CRM and Salesforce CRM.
2. No CRM write-back; Fix is advisory.
3. No application RBAC.
4. No connection delete.
5. No scan-cancel API (only `cancel_requested` column).
6. UI quarter/FY/custom ranges are not accepted by the API.
7. Client-side rule sliders (`staleDays`, duplicate floors, burst rules, `excludeBulkUsers`, `stageAware`) are **not** consumed by scan create/processing.
8. Config / PII / automation domains are not scored.
9. Duplicate **pair** confirmation is not the Records-tab state machine.
10. Salesforce business-critical, duplication, freshness, and several integrity checks still key off Zoho module/field names, so Salesforce `Account`/`Contact`/`Opportunity` often skip those domain rules while still getting completeness/validity on described fields and OwnerId resolution.
11. Owner names require a populated directory; empty `salesforce_connection_owners` yields `Unknown owner`.
12. Zoho HTTP Bulk routes exist for compatibility/fallback; React does not call them.
13. `domain/` package is test/spike contract code, not HTTP runtime.
14. Token refresh errors are mapped to generic `TOKEN_REFRESH_FAILED` without Salesforce `error` in the API body.

---

## 30. Future scope (not implemented)

- Additional CRM providers
- Automated CRM updates
- Severity-weighted D2 scoring if product elects to replace the current measured-domain average
- True duplicate-pair workflow
- Fiscal calendar windows
- Connection disconnect UI
- Scan cancel UX
- Applying Setup “rules” to the engine

---

## 31. Traceability (selected)

| Requirement | Primary implementation | Test / UI |
|---|---|---|
| FR-AUTH-002 | `App.jsx` redirect | Session restore |
| FR-CON-001 | `connections/activation.py` | Connect / switcher |
| FR-ZO-001 | `connections/routes.py` | Connect screen |
| FR-SF-001 | `salesforce/oauth.py` | Connect screen |
| FR-SF-002 | `salesforce/client.py` | `tests/test_salesforce_token_refresh.py` |
| FR-SF-003 | `salesforce/scan_create.py` | `tests/test_salesforce_scan_create.py` |
| FR-SCN-001 | `common/core.py` `validate_scan_config` | Setup |
| FR-SCN-005 | `orchestration/service.py` | Home Resume |
| FR-SCN-007 | `scans/delete.py` | Home delete |
| FR-WRK-001 | worker `main.py` files | Worker tests |
| FR-DQ-* | `pipeline/processing.py` (per worker) | Record/owner tests |
| FR-ANL-002 | `analytics/trends.py`, `analyticsAdapter.js` | Report Overview/Trend |
| FR-FIX-001 | `analytics/fixes.py` | Fix tab |
| FR-RPT-005 | `analytics/records.py` | Records tab |

---

## 32. Use cases (implemented)

**UC-01 Connect CRM** — User opens Connect, completes Zoho or Salesforce OAuth, sees organization and connected user, connection is exclusive-active.

**UC-02 Switch connection** — User activates another stored connection; new scans use it; history still lists scans from other owned connections.

**UC-03 Run scan** — User selects modules, depth, clock, 7/30/90d or all, starts scan, watches running view, opens report when `COMPLETED`.

**UC-04 Resume scan** — User opens Home and resumes a non-terminal scan; `/advance` enqueues the correct worker.

**UC-05 Review quality** — User inspects Overview/Users/Modules/Records/Trend/Fix. Fix items are manual.

**UC-06 Delete scan** — User confirms id; system refuses if workers are active.

**UC-07 Token expired** — Metadata or extract refreshes access token; on failure user must reconnect (especially Salesforce `TOKEN_REFRESH_FAILED`).

---

## 33. Appendices

### A. Glossary

See §1.5.

### B. Scan depths (effect on missing-value findings)

| Depth | System mandatory / unique | Business-critical (Zoho-named modules) | Optional fields |
|---|---|---|---|
| quick | Yes | No | No |
| presales | Yes | Yes | No |
| deep | Yes | Yes | Yes |
| full | Yes | Yes | Yes |

Extraction still includes the described allowlist; depth filters **findings**, not the extract field list.

### C. Frontend vs backend rules

| Item | Frontend | Backend |
|---|---|---|
| Depth/clock/modules/range 7d–90d/all | Used | Used |
| qtr / fy / custom | Shown | Rejected or unsupported |
| staleDays, burst, duplicate floors, excludeBulkUsers, stageAware | localStorage only | Not applied |
| Domain weights | `analyticsAdapter.js` | Same weights in `analytics/trends.py` |

### D. Related documents

- `docs/functional-specification.md` — original widget FSD (not this app)
- `docs/approved-product-contract.md` — approved product policy
- `docs/catalyst-architecture.md` — platform architecture notes

---

## 34. Detailed functional requirements

Normative statements. Status is **Implemented** unless noted.

### FR-AUTH-001 Application identity

| Field | Content |
|---|---|
| Requirement | The system shall treat Catalyst Authentication as the only application identity. |
| Description | CRM OAuth does not log a user into this application. Application login does not grant CRM API access until a connection exists. |
| Preconditions | Catalyst Authentication is configured for the project. |
| Inputs | Catalyst session cookie / current-user SDK result. |
| Processing | HTTP handlers call `get_current_user`. Inactive users are rejected. |
| Outputs | `user_id` used as owner of connections and scans. |
| Exception | Missing/invalid user → `AUTHENTICATION_REQUIRED`. |
| Postconditions | All subsequent APIs are scoped to that `user_id`. |
| Dependencies | Catalyst Authentication. |

### FR-AUTH-002 Login redirect

| Field | Content |
|---|---|
| Requirement | If an API returns HTTP 401 or 403, the client shall redirect to `{origin}/__catalyst/auth/login`. |
| Inputs | Failed same-origin fetch. |
| Processing | React `client.js` intercepts 401/403. |
| Outputs | Browser navigation to Catalyst login. |
| Alternative | Successful APIs continue the SPA. |
| Current status | Implemented. There is no in-app password form. |

### FR-CON-001 Exclusive active connection

| Field | Content |
|---|---|
| Requirement | The system shall allow multiple Zoho and Salesforce connections per application user and keep at most one active across both providers. |
| Inputs | Activate API for a connection ROWID. |
| Processing | Sets `is_active=true` and `last_selected_at` on the target; clears `is_active` on all other Zoho and Salesforce rows for the user. On failure, restores previous actives. |
| Outputs | Updated connection rows; UI key `{provider}:{connectionId}`. |
| Exception | Missing connection or auth failure. |
| Postconditions | New scans use the exclusive-active connection (FR-CON-002). |
| Current status | Implemented. Connection **delete** is not implemented. |

### FR-ZO-001 Zoho OAuth connection

| Field | Content |
|---|---|
| Requirement | The system shall connect Zoho CRM using OAuth 2.0 authorization code with `access_type=offline`. |
| Preconditions | Application user is authenticated. Zoho client id/secret and redirect URI are configured. |
| Inputs | User consent at Zoho Accounts; callback `code` + `state`. |
| Processing | `GET /api/zoho/consent` → authorize URL with `ZOHO_SCOPE` (modules, fields, users, org, layouts, workflow, search, **bulk.read**). Callback exchanges code, stores tokens and org identity on `zoho_connections`, activates exclusively. |
| Outputs | Connection listing without tokens. |
| Exception | Consent declined or token exchange failure; UI hash notices. |
| Dependencies | Zoho Accounts; Data Store `oauth_states`, `zoho_connections`. |

### FR-SF-001 Salesforce OAuth connection

| Field | Content |
|---|---|
| Requirement | The system shall connect Salesforce using authorization code + PKCE (S256), scope `api refresh_token id`, `prompt=consent`. |
| Preconditions | Live env contains Salesforce client id/secret, login URL, redirect URI. |
| Inputs | Callback `code` + stored `code_verifier`. |
| Processing | Token request requires `access_token`, `refresh_token`, `instance_url`. Identity URL supplies user/org. Persist `salesforce_connections` and exclusive-activate. |
| Outputs | Connection JSON (org, connected user; no tokens). |
| Exception | Missing refresh token or identity; user must retry consent. |
| Dependencies | Salesforce login host; `oauth_states`. |

### FR-SF-002 Salesforce token refresh

| Field | Content |
|---|---|
| Requirement | On access-token expiry (or unparsable expiry), the system shall refresh with `grant_type=refresh_token`. A new refresh token from Salesforce shall be persisted; omission shall leave the stored refresh token unchanged. Failed refresh shall not overwrite stored tokens. |
| Exception | `REFRESH_TOKEN_MISSING` or `TOKEN_REFRESH_FAILED` (502 on metadata). API body does not include Salesforce `error` JSON. |
| Current status | Implemented. Live failure requires Catalyst logs (`HTTPError` vs `KeyError`) to distinguish revoked grant vs missing client credentials. |

### FR-SF-003 Salesforce owner directory at scan create

| Field | Content |
|---|---|
| Requirement | Salesforce owner directory (Users and Group Queue/Regular) shall be cached in `salesforce_connection_owners` at scan create for the scan’s connection. Sync failure shall not block scan creation. |
| Outputs | Directory rows with `crm_user_id`, `display_name`, `owner_type`, `active`. |
| Alternative | Scan still creates; Users tab may show `Unknown owner` until directory is populated. |
| Current status | Implemented in source. Live population depends on deploying this HTTP function. |

### FR-SCN-001 Scan configuration validation

| Field | Content |
|---|---|
| Requirement | The system shall create a scan only with ≥1 accessible module/object, depth ∈ {quick, presales, deep, full}, clock ∈ {created, modified}, range ∈ {7d, 30d, 90d, all}. |
| Inputs | `POST /api/scans` JSON. |
| Processing | `validate_scan_config` ignores client `rules`. `qtr`/`fy` raise validation requiring org calendar metadata. |
| Outputs | `scanId` or `INVALID_SCAN_CONFIG` / `MODULE_NOT_ACCESSIBLE`. |
| Validation | Salesforce objects must exist and include the clock field (`CreatedDate` or `LastModifiedDate`). |
| Current status | Implemented. UI still **displays** quarter, FY, and custom range. |

### FR-SCN-003 Reuse equivalent active scan

| Field | Content |
|---|---|
| Requirement | If an equivalent active scan exists (same connection, modules, clock, depth, range policy), the system shall reuse it and still enqueue the provider worker. |
| Active statuses | `CREATED`, `AUTH_VALIDATING`, `DISCOVERING`, `PLANNED`, `EXTRACTING`, `PROCESSING`, `PAUSED_RETRYABLE`. |
| Postconditions | Client receives the existing `scanId`. |

### FR-SCN-005 Resume / advance

| Field | Content |
|---|---|
| Requirement | Resume from Home shall `POST /api/scans/{id}/advance`. Salesforce: enqueue Salesforce worker only. Zoho: enqueue Zoho worker first; if enqueue fails with a **known** failure (not `WORKER_ENQUEUE_OUTCOME_UNKNOWN`), HTTP may run one inline pipeline step. |
| Preconditions | Scan owned by the user; not terminal unless already complete. |
| Exception | `WORKER_ENQUEUE_OUTCOME_UNKNOWN` is returned; no silent success. Status polling does **not** call `/advance`. |

### FR-SCN-007 Delete scan

| Field | Content |
|---|---|
| Requirement | `DELETE /api/scans/{scanId}` with `{ "confirmScanId": "<same id>" }` shall delete the owned scan and descendants and File Store objects, and shall retain the CRM connection. |
| Exception | 409 `SCAN_DELETE_ACTIVE_TASK` while tasks are `QUEUED`, `RUNNING`, or `OUTCOME_UNKNOWN`. Confirmation mismatch → `SCAN_DELETE_CONFIRMATION_REQUIRED`. |
| Postconditions | History and trend no longer include the scan. |

### FR-WRK-001 Asynchronous extraction

| Field | Content |
|---|---|
| Requirement | Long-running CRM extraction and DQ shall run in provider-specific Job Functions. |
| Processing | HTTP persists plan + `pipeline_tasks`. Zoho pool runs `ORCHESTRATE_SCAN` (and related batch tasks). Salesforce pool runs `ORCHESTRATE_SALESFORCE_SCAN`. Workers lease tasks, extract, store files, process batches, persist analytics. |
| Exception | Enqueue unknown outcome; lease already-running/already-complete. |
| Recovery | Completed batches skipped via checkpoints. Salesforce never resubmits an existing `provider_job_id`. |

### FR-EXT-001 Batch size

| Field | Content |
|---|---|
| Requirement | Processing batch size shall be 5,000 records (`batch-plan-v1`). |
| Inputs | File Store export + field plan. |
| Exception | Fewer CSV rows than planned → processing error. Multi-page Zoho Bulk Read (`next_page_token`) is not implemented. |

### FR-ANL-002 Overall score

| Field | Content |
|---|---|
| Requirement | Overall and trend scores shall be a weight-only-on-measured-domains average using weights completeness 20, duplication 20, validity 15, plausibility 10, freshness 10, integrity 10, config 8, pii 4, automation 3. |
| Formula | `round( Σ (domainScore × weight) / Σ weights of domains with a numeric score )` |
| Owner score | Completeness 20 + validity 15 only. |
| Exception | No measured domains → score `null`. Config/PII/automation currently not measured, so they do not enter the denominator. |
| Note | This is **not** the severity-weighted D2 formula in `docs/approved-product-contract.md`. |

### FR-FIX-001 Manual fix plan

| Field | Content |
|---|---|
| Requirement | The system shall produce a ranked **manual** remediation plan and shall not write CRM records. |
| Inputs | Completed scan; optional module query filters. |
| Processing | Group persisted issues; assign priority; rank; cap at 30. |
| Outputs | `actions[]` with `actionType: "manual"`, `pointGain: null`. |
| Exception | `FIX_PLAN_READ_FAILED`; empty `measured: false` when no finding schema. |
| Current status | Implemented. Copy for mandatory/unique missing fields is Zoho-worded. |

### FR-RPT-005 Records listing

| Field | Content |
|---|---|
| Requirement | The system shall list incomplete, inaccurate, and proper records for an owned scan (page size 20). |
| Inputs | `state`, `module`, `owner`, `q`, page. |
| Processing | Findings from Data Store; `proper` rows re-evaluated from File Store export. Salesforce uses export `Name`; Zoho may enrich names via CRM GET. Salesforce record ids are not returned to the client. |
| Outputs | Paginated rows; `Unnamed record` / `Unknown owner` / `Unassigned` fallbacks. |
| Exception | Missing export → read error. Duplicate pair states are not listable. |

### FR-SEC-001 Token confidentiality

| Field | Content |
|---|---|
| Requirement | CRM tokens shall be stored in connection tables and shall not be returned on connection listing APIs. |
| Exception | Tokens exist only in Data Store and worker/HTTP memory during API calls. |

---

## 35. Screen specifications (extended)

Chrome on all authenticated pages: `AppShell` (sidebar + header). Workspace nav: **Reports**, **New scan**, **Connect to CRM**. Report nav (enabled in report phase): Overview, Users, Modules, Trend, Records, Fix.

### 35.1 Setup (`/` — route name `setup`)

| Item | Specification |
|---|---|
| Purpose | Configure and start a scan against the active connection. |
| Entry | Default URL; sidebar New scan. |
| Layout | Module checklist; depth; created/modified clock; range presets (7d, 30d, 90d, quarter, FY, all, custom); indicative cost. |
| Primary action | Start scan → `POST /api/scans` → `/scans/{id}`. |
| Validation | Client + FR-SCN-001. Quarter/FY fail on the API. |
| Empty | No modules if not connected → user sent to Connect. |
| Error | API error message on the form. |

### 35.2 Connect (`/connect`)

| Item | Specification |
|---|---|
| Purpose | Authorize or switch Zoho CRM / Salesforce CRM. |
| Actions | Start consent; activate an existing connection. |
| Success | Exclusive-active connection; user can return to Setup. |
| Error | Consent/token notices from callback hash flags. |

### 35.3 Reports / Home (`/scans`)

| Item | Specification |
|---|---|
| Purpose | Historical scans for the user’s connections. |
| Actions | Open running or report route; Resume (`/advance`); Delete with confirm-id. |
| Empty | No scans yet. |
| Error | Failed list/delete/advance surfaced on the page. |

### 35.4 Running (`/scans/{scanId}`)

| Item | Specification |
|---|---|
| Purpose | Show per-module extract/process progress. |
| API | `GET /api/scans/{id}/status` every 2s. Does not call `/advance`. |
| Success | `COMPLETED` → `/scans/{id}/report`. |
| Failure | `FAILED_TERMINAL` remains a failed running/history item. |

### 35.5 Report (`/scans/{scanId}/report`)

| Item | Specification |
|---|---|
| Purpose | Six-tab analysis of a completed scan. |
| APIs | `/results`, `/trend`, `/records`, `/fix-plan` as tabs need them. |
| Filters | Modules, users (owners), Overview state focus. |
| Unknown tab | `ComingSoonPanel` fallback (not used for the six implemented tabs). |

### 35.6 Boot / error phases

Boot: “Restoring your account” while session/history load. Error: message + retry (client reset). 401/403 → Catalyst login.

---

## 36. End-to-end workflows (implemented)

### 36.1 Zoho happy path

```
Login → Connect Zoho → exclusive-active connection
  → Setup (modules, depth, clock, range)
  → POST /api/scans (scan_jobs + scan_module_runs)
  → enqueue ORCHESTRATE_SCAN
  → AUTH_VALIDATING → DISCOVERING (fields + zoho_connection_users)
  → PLANNED → Bulk Read submit/poll/download ZIP
  → File Store → 5,000-row batches → DQ → analytics_results
  → COMPLETED → Report tabs
```

### 36.2 Salesforce happy path

```
Login → Connect Salesforce (PKCE) → exclusive-active connection
  → Setup
  → POST /api/scans (crm_provider=salesforce, describe field plans)
  → owner directory sync (non-blocking)
  → enqueue ORCHESTRATE_SALESFORCE_SCAN
  → Bulk API 2.0 Query (CreatedDate/LastModifiedDate window)
  → poll JobComplete → CSV (+ locator pages) → File Store
  → wrap CSV as ZIP if needed → batches → DQ
  → COMPLETED → Report (OwnerId resolved via salesforce_connection_owners)
```

### 36.3 Failure / recovery

```
Token refresh fail → PAUSED_RETRYABLE or TOKEN_REFRESH_FAILED → reconnect
Worker enqueue unknown → do not treat as success; inspect Job Pool
Salesforce existing provider_job_id → poll only, never resubmit
Completed processing batches → skipped on retry
FAILED_TERMINAL (Aborted/Failed bulk, persist failure) → not auto-resumed
Home Resume → /advance (Salesforce enqueue-only; Zoho enqueue-then-optional inline)
```

---

**End of document.** This FSD describes the standalone CRM Data Health Scanner as implemented on 20 September 2026. Unimplemented product-contract items are listed as limitations or future scope, not as current features.
