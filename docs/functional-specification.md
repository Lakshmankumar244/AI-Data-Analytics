# Functional Specification — Zoho Data Health Scanner (v2)

**Document type:** Reverse-engineered functional specification. No implementation code.
**Sources examined:**
1. `AI_Data_Health_development.zip` → a built Zoho CRM widget (`app/widget.html` +
   minified React bundle `assets/widget-DzJ0ge9W.js`, 267 KB). This is a **client-only
   demo build**: it embeds a full synthetic-data generator and falls back to a mocked
   backend whenever `window.ZOHO` (the Zoho Embedded App SDK) is not present. Every
   business rule, threshold, and state transition described below was read directly out
   of this bundle's logic — it is not inferred from the deck alone.
2. `Data_Health_Scanner.pptx` — 31-slide internal build-approval deck describing the
   product, its intended production architecture (Catalyst backend, live Zoho org
   scanning), commercial model, and rollout plan.

Where the two sources agree, this spec states the behavior as fact. Where the widget
bundle is silent (because it's a client-only demo and the real extraction/backend logic
doesn't exist in this artifact) but the deck specifies intended production behavior,
that is called out explicitly as **(deck-only, not present in code)**.

**Status note (superseding revision):** every open question this document originally
raised in §11 has since been resolved, and several factual claims below were corrected
against direct re-verification of the widget bundle. `docs/decisions-log.md` is now the
authoritative source for every design decision — where this document and that one ever
disagree, the decisions log wins. This revision folds those corrections in directly
rather than leaving them as a separate errata list.

---

## 1. Purpose

A tool that connects (read-only) to a Zoho org, extracts records from selected modules
within a date range, classifies every record into one of six data-quality states,
scores the org across nine weighted domains, and presents the result through three
analytical lenses — which **module** is failing, which **user** is causing it, and
whether things are getting **better or worse over time**. Output includes a ranked,
effort/gain-scored remediation plan.

The product is explicitly positioned as a sales and delivery tool for a consulting
practice (free diagnostic → paid audit → paid remediation → monthly monitoring
retainer), not just a technical utility — several functional requirements below (e.g.
coaching bands instead of rankings, cost-before-run, PDF built for a non-technical
reader) exist to serve that commercial motion, not the algorithm.

---

## 2. Actors

| Actor | Description |
|---|---|
| Consultant / operator | Runs scans, sets scope, reads the command centre, exports reports, presents to the client. The only user role the interface is built for. |
| Client org (Zoho CRM, and per the deck also Desk/Books/Creator/People/Analytics) | The system being scanned. Never writes anything back in the scope covered by this spec — read-only. |
| End client stakeholders (sales director, CFO, CRM admin) | Consumers of the exported PDF / walkthrough, not direct users of the tool. |

---

## 3. Application lifecycle (state machine, confirmed in code)

The app is a single reducer-driven state machine with these phases:

```
boot → setup → running → report ⇄ (setTab/setFilter within report)
                  ↓                        ↓
                error                    reset → setup
```

- **boot**: SDK detection. If `window.ZOHO` and the Embedded App SDK are present, the
  app initializes against the live Zoho org (`ZOHO.embeddedApp.init`) and sets
  `dataSource` accordingly. **Correction:** the live branch is not initialization-only —
  it performs real calls (`CRM.META.getModules`, `CRM.META.getFields`,
  `CRM.API.getAllRecords`, `CRM.API.getAllUsers`, `CRM.UI.Record.open`) against the
  connected org. This widget has a genuine, if limited, live extraction path; it is not
  purely a mock demo. If the SDK is absent (e.g. run outside CRM, `npm run dev`), the
  app **falls back to a built-in mock client automatically** (`dataSource: "mock"`) —
  this remains a deliberate, documented fallback, not an error path.
- **setup**: module/scope selection screen (see §4.1).
- **running**: extraction in progress, per-module progress tracked.
- **report**: a completed scan is loaded (`scan` + `cube` objects in state); the six
  command-centre tabs become navigable.
- **error**: terminal error state with a message, reachable from any phase.
- **reset**: clears `scan`/`cube`/`progress`/`completed` and returns to setup without
  losing the last-used scan configuration.

Scan configuration (module selection, clock, date range, depth, rule thresholds) is
persisted to `localStorage` under key `scan-config-v2` and reloaded on boot — a
returning operator resumes their last scope rather than starting blank.

---

## 4. Screen-by-screen specification

### 4.1 Setup screen (`phase: setup`)

Fields, confirmed from state shape and default config object:

| Field | Type | Default | Notes |
|---|---|---|---|
| Client org | selector | — | Org label shown; in mock mode fixed to a synthetic "Zoho CRM" org |
| Modules in scope | multi-select checklist | `["Leads","Contacts","Accounts","Deals","Vendors"]` | Each entry shows a record count next to it |
| Scan depth | single-select, 4 options | `presales` | See table below |
| Clock | toggle | `created` | `created` \| `modified` — mutually exclusive, never blended (enforced by design, called out explicitly in the deck as "mixing them produces a number nobody can interpret") |
| Date range | quick-range buttons + custom | `90d` (last 90 days) | Quick ranges observed: 7 days, 30 days, 90 days, this quarter, this FY, all history, custom |
| Rule thresholds | advanced/expandable panel | see §6.3 | **Designed to be** editable per-scan: stale-days, min records per user, burst size/window, repeated-value threshold, duplicate suspected/confirmed floors, exclude-bulk-users toggle, stage-aware toggle — the reducer action for this exists but no UI panel is currently wired to it (see §6.3 correction) |

**Scan depth options** (id, records/module cap, purpose — verbatim from code):

| id | Cap per module | Purpose (as stated in the tool) |
|---|---|---|
| `quick` | 1,000 | "Smoke test of a new org or a re-scan after a fix. Cheapest run." |
| `presales` | 5,000 | "What we run in the room. Produces the user view, which is the part that lands." (default) |
| `deep` | 20,000 | "Enough volume for the plausibility pack to find bursts reliably." |
| `full` | 0 (uncapped) | "Full depth inside the date range, capped by Zoho's 100,000 offset ceiling." |

Before committing, the screen surfaces records in range, API credits that will be
consumed against budget, and estimated runtime — confirmed as a UI requirement by both
sources. **Correction:** in the widget, this estimate is computed from the depth
option's record cap alone, not a real records-in-range query — it will overstate the
estimate for any module with fewer records than the cap. Production needs a genuine
calculation (the Phase 1 Catalyst frontend build already implements this correctly in
`CostEstimate.jsx` / `estimateScan()`, ahead of the backend that will eventually back
it with real numbers). A read-only-scopes disclosure is shown before consent.

A saved scope can be turned into a recurring schedule with one action **(deck-only, not
present in code — no scheduling UI exists in the widget bundle)**.

### 4.2 Running screen (`phase: running`)

- Per-module progress entries keyed by module name (`progress[module] = {...}`), each
  module's extraction reported as it completes (`moduleComplete` action, accumulating
  into `completed[]`).
- Live API call statistics tracked in state: `apiStats = { dispatched, retried, failed }`
  — meaning the extractor is expected to retry failed calls and the UI surfaces retry/
  failure counts live, not just a spinner.
- Reversible: the operator can cancel back to setup (implied by `reset` action being
  available independent of phase).

### 4.3 Report screen (`phase: report`) — six tabs

Confirmed tab set (from `setTab` action and CSS classes): **Overview, Modules, Users,
Trend, Records, Fix**. A shared top filter bar drives every tab (`filterModules`,
`filterUsers`, `attribution`, `grain` are top-level, tab-independent state — changing
them re-derives whichever tab is active without a re-scan).

#### 4.3.1 Overview tab
- Overall health score (0–100) rendered as a ring/gauge (`ring-centre`, `ring-track`
  CSS classes), with prior-period value shown alongside.
- Org verdict band from score (see §6.6).
- Record-state breakdown as a stacked/segmented bar across the six states.
- Domain score bars, one per domain (nine total), each showing the domain's 0–100 score
  weighted by its fixed weight.
- "Biggest movers" list: modules and users with the largest score delta vs. the prior
  comparable period, sorted, top 5 shown (`movers: k.slice(0,5)` confirmed in code).
- A callout when a user's movement crosses ±3 points ("Better than the cohort before" /
  "Worse than the cohort before" / "Holding").
- Counts requiring a minimum record threshold before scoring: any slice below
  `minRecordsPerUser` (default 25) is excluded from mover calculations and shown as
  "Fewer than 25 records in this period" rather than a misleading number.

#### 4.3.2 Modules tab
- Module × domain matrix. Rows = modules in scope, columns = the nine domains, plus an
  overall column.
- Each cell rendered into one of six visual bands via a **percentile-style banding
  function**, confirmed in code:
  - `null` → "na" (domain not applicable to this module — rendered as blank, not zero)
  - ≥97 → excellent
  - ≥90 → good
  - ≥80 → ok
  - ≥70 → fair
  - ≥55 → warn
  - else → bad
- Stage-aware toggle: when on, rule evaluation is gated by each record's current stage;
  when off, all stage-scoped rules apply uniformly (the deck states turning this off
  drops every module's score by roughly 15 points and destroys client trust in the
  number — a strong signal this must default **on**, confirmed as default `true` in
  code's `stageAware: true`).
- A "worst cell" callout auto-identifies the single lowest-scoring module×domain
  combination with its record/cluster count.
- Export to `module-matrix.csv` (filename confirmed in code).

#### 4.3.3 Users tab
- Table columns confirmed: user, team, records created (in the selected attribution),
  score, record-state mix, trend (sparkline, prior vs current), band, suggested action.
- **Attribution selector**, three modes: `created` (default — "that is where the defect
  enters"), `modified`, `owner`.
- Controls: module filter, team filter, minimum-records input (default 25), "exclude
  bulk users" toggle (**default ON**).
- Bulk/system user detection is pattern-based against the user's name/identifier,
  matching (case-insensitive substring): `import`, `integration`, `migration`,
  `system`, `api`, `data load`, `bulk`. Matched users are excluded from individual
  scoring by default and shown separately.
- Users below `minRecordsPerUser` show **"Insufficient data"** and band
  **"Insufficient data"** rather than a computed score — never a misleading number for
  a low-volume user.
- Coaching bands (not ranks) — see §6.6.
- Export to `user-accountability.csv`.

#### 4.3.4 Trend tab
- Grain selector: default `month`; other grains implied by the deck (`day`/`week`/
  `quarter`) though only `month` is exercised in the bundled mock data.
- Clock toggle reused from setup (`created`/`modified`), rendered as two distinct lines
  ("line created", "line modified" CSS classes) — never combined into one series.
- Cohort decay table: a cohort (records created in a given period) is re-scored at
  creation, after 1 month, after 3 months, and "today", with a verdict label
  (`Decaying fast` / `Decaying` / `Holding` style, per the deck's example) — this
  separates an entry-quality problem from a maintenance problem.
- Event overlays capability (go-live dates, new-joiner cohorts, campaign imports,
  releases plotted on the trend line) — **(deck-only, no overlay data structures found
  in the widget bundle's state shape)**.

#### 4.3.5 Records tab (record state explorer)
- Every state count is clickable and opens a filtered record list for that state
  (`focusState` in top-level app state — clicking a state count sets this and filters
  the Records tab).
- Table columns: record identifier, module, **why it was flagged** (a specific,
  human-readable reason string, never a generic "flagged" — see §6 for exact reason
  text per rule), created-by, created date, suggested fix.
- Field values are never displayed or exported — only record identifiers, module,
  state, and the flagged reason. This is a hard constraint, not a display choice (see
  §9 Data retention).
- Export to `remediation-plan.csv` and a "send to fix list" action linking records into
  the Fix tab.

#### 4.3.6 Fix tab (remediation / action centre)
- Actions grouped into three waves (mechanical / assisted / process — confirmed via
  `wave-block`, `wave-head`, `wave-title`, `wave-totals` CSS structures and the
  `mechanical` string constant).
- Each action row: action name, module scope, record count affected, effort estimate,
  projected score gain, and a run control.
- A running "projected score after selected actions" total updates as actions are
  selected (`projection-from`, `projection-to`, `projection-arrow`, `projection-bar`
  elements confirmed).
- **Fix action identifiers (fixKey), each tied to a specific rule — resolved policy
  shown, with the widget's actual (incorrect) behavior flagged separately:**

  | fixKey | Bound to rule | Action |
  |---|---|---|
  | `normalise-phone` | `validity.phone` | Normalize phone numbers to a consistent dialable format |
  | `fix-email` | `validity.email` | Correct malformed email addresses |
  | `fix-identifier` | `validity.indiaIdentifiers` | Correct/flag invalid GST/PAN/IFSC/pincode |
  | `merge-duplicates` | `duplication.fuzzy`, **`confirmed_duplicate` state only** | Merge confirmed duplicate clusters |
  | `review-duplicates` | `duplication.fuzzy`, **`suspected_duplicate` state** | Route to human review — not an automatic merge |
  | `close-overdue` | `freshness.overdue` | Close or re-date overdue open deals |
  | `archive-stale` | `freshness.stale` | Bulk close/archive records untouched beyond threshold |
  | `reassign-owner` | `integrity.inactiveOwner` / `integrity.noOwner` | Reassign records with no owner or an inactive owner |
  | `relink-orphans` | `integrity.orphan` | Relink orphan child records to an unambiguous parent |
  | `backfill-required` | `completeness.*` | Backfill required/report-critical fields |
  | `audit-suspicious` | `plausibility.*` | Route to manual audit — explicitly **not** a scripted fix |

  **Correction:** an earlier revision of this document asserted the
  suspected/confirmed-duplicate split above was already how the widget behaves. It
  is not. The widget hardcodes `fixKey: "merge-duplicates"` on the single
  `duplication.fuzzy` rule definition, covering both `suspected_duplicate` and
  `confirmed_duplicate` states identically — meaning an unconfirmed suspected
  duplicate currently routes to the same "merge" action as a confirmed one. The
  string `"review-duplicates"` does exist in the bundle but is never bound to
  anything. This directly contradicts the product's own stated non-negotiable
  (unconfirmed findings must never route to an automated write) and is a resolved
  code-fix item, not a policy question — production must bind these separately as
  shown in the table above.
- Every mechanical action requires "preview" before it writes, and every write is
  snapshotted for rollback **(deck-only — no preview/snapshot/rollback data structures
  exist in the widget bundle since it never performs writes; this is entirely a
  production-backend responsibility)**.
- "Generate SOW" export action present in the deck's UI mock **(deck-only)**.

---

## 5. Data model (entities, reconstructed)

These are the object shapes the client operates on — a production backend must produce
equivalent structures, whatever its storage engine.

**Module extract record** (per record, pre-classification):
```
{ id, module, createdBy, modifiedBy, owner, createdTime, modifiedTime, stage,
  <module-specific fields as needed by rules: email, phone, GSTIN, PAN, industry,
  source, amount, closeDate, closeReason, accountId (lookup), ...> }
```

**Record signature** (derived, used only for duplicate matching — confirms the
system does NOT retain raw fields beyond this signature after classification):
```
{ strongId, email, phone, name, company }
```

**Record state result** (the only long-lived per-record artifact):
```
{ recordId, module, state, failedRuleIds[], reasonText, confidence? }
```
where `state ∈ {proper, incomplete, inaccurate, suspicious, suspected_duplicate,
confirmed_duplicate}`.

**User score entry**:
```
{ userId, name, team, records, score, band, sufficient (bool), bulk (bool),
  stateCounts, trend (sparkline series) }
```

**Scan object**: holds scope (modules, clock, range, depth, rule config), full record
state results, computed cube.

**Cube** (the pre-aggregated result — the component the deck calls the thing that
"makes version two possible"): pre-computed scores sliceable by module, user, and time
dimension without re-touching raw records.

**Duplicate cluster**: `{ clusterId, module, recordIds[], matchType (suspected|
confirmed), confidence, matchedFields[] }`.

---

## 6. Business rules, thresholds, and formulas (as implemented)

### 6.1 The six record states

| State | Meaning | How assigned |
|---|---|---|
| Proper | Passes every rule in scope for its module and stage | No rule failures at all |
| Incomplete | Structurally valid, missing information | `completeness.*` or `freshness.stale` failure |
| Inaccurate | A value is present and wrong | `validity.*`, `freshness.overdue`, or `integrity.*` failure |
| Suspicious | Passes format checks, fails plausibility | Any `plausibility.*` rule failure |
| Suspected duplicate | Fuzzy match confidence 0.70–0.90 | `duplication.fuzzy`, confidence in range |
| Confirmed duplicate | Exact strong-identifier match, or >0.90 with two strong fields agreeing | `duplication.fuzzy`, confidence above floor |

A record is assigned exactly one state, by an **explicit, confirmed precedence map**
(not an inference — `Zt = ["proper","incomplete","inaccurate","suspicious",
"suspected_duplicate","confirmed_duplicate"]` with a matching numeric ranking, highest
wins): `confirmed_duplicate > suspected_duplicate > suspicious > inaccurate >
incomplete > proper`. This matches the state ontology's apparent severity ordering, as
originally guessed in an earlier revision of this document — that guess is now
confirmed as fact, not inference.

### 6.2 Rule catalogue (as implemented in the widget's mock engine)

**Correction: 22 rule identifiers** were found (16 per-record rules + 6 set-level
rules — an earlier revision of this document miscounted this as 24), each with a fixed
`domain`, target `state`, `severity`, and human-readable `description`. These represent
**rule families** (each capable of firing with a specific, per-record reason string),
not the full ~70-rule production catalogue the deck describes — the widget's mock
engine is a representative subset sufficient to drive every UI screen. ~48 additional
rules are needed to reach the deck's target and must be authored fresh (see §11).

| Rule id | Title | Domain | → State | Severity | Description (verbatim) |
|---|---|---|---|---|---|
| `completeness.mandatory` | Mandatory field empty | completeness | incomplete | critical | A field the layout marks mandatory is empty, because imports and API writes bypass layout validation. |
| `completeness.reportCritical` | Report critical field empty | completeness | incomplete | high | A field every downstream report segments on is empty. Zoho does not mark these mandatory, so nothing catches them. |
| `completeness.stageRequired` | Stage required field empty | completeness | incomplete | high | A field expected once the record reaches a given stage. A Lead at New is not judged by the bar set for a Lead at Qualified. |
| `completeness.closeReason` | Closed deal with no reason | completeness | incomplete | high | A closed deal without a reason removes every win/loss insight the client paid for. |
| `validity.email` | Malformed email | validity | inaccurate | high | Email that cannot receive mail. Campaigns bounce and sender reputation degrades. |
| `validity.phone` | Unusable phone number | validity | inaccurate | high | Phone with no country code, a doubled prefix, or too few digits to dial. |
| `validity.indiaIdentifiers` | GST, PAN, IFSC or pincode invalid | validity | inaccurate | critical | Statutory identifiers validated by checksum, not just by shape. A GSTIN that fails checksum gets an invoice rejected. |
| `validity.picklist` | Picklist value off the list | validity | inaccurate | high | A picklist holding a value that is not a defined option. Breaks reports and workflow criteria silently. |
| `validity.website` | Malformed website | validity | inaccurate | low | A website field that is not a resolvable URL. |
| `validity.crossField` | Contradictory field combination | validity | inaccurate | high | Values that contradict each other: won with no amount, negative revenue, modified before created, closed with a future date. |
| `duplication.fuzzy` | Duplicate records | duplication | suspected/confirmed_duplicate | critical | Blocking key generation then weighted fuzzy scoring. Above 0.90 with two strong fields agreeing is confirmed; 0.70 to 0.90 needs a person. |
| `freshness.overdue` | Open deal past its close date | freshness | inaccurate | critical | Open deals with close dates in the past. The forecast number the board sees is fiction. |
| `freshness.stale` | Stale record | freshness | incomplete | medium | Untouched beyond the agreed threshold. Nobody owns ageing records, so they rot quietly. |
| `integrity.noOwner` | No owner | integrity | inaccurate | critical | Invisible to assignment rules, queues and every per-rep report. |
| `integrity.inactiveOwner` | Owned by an inactive user | integrity | inaccurate | high | Still assigned to a deactivated user. Nobody is working these and they distort per-rep reporting. |
| `integrity.orphan` | Orphan child record | integrity | inaccurate | high | Contacts without an account, deals without an account. These belong to no single module and break rollups. |
| `plausibility.dummy` | Test or dummy value | plausibility | suspicious | high | Format valid, entirely fictional. Names like asdf, test, aaa. No native report surfaces these. |
| `plausibility.burst` | Entry velocity burst | plausibility | suspicious | critical | A run of records created by one user inside a few minutes. Format valid throughout, so no native report surfaces them. |
| `plausibility.repeatedValue` | One contact value across many records | plausibility | suspicious | high | The same mobile or email repeated across records that should each be a distinct person. |
| `plausibility.impossible` | Impossible sequence | plausibility | suspicious | critical | A deal created and marked won in the same minute, or closed before it was created. |
| `plausibility.roundAmounts` | Repeated round amounts | plausibility | suspicious | medium | The same round figure repeated across a territory, which is what invented numbers look like. |
| `plausibility.offHours` | Off-hours bulk edit | plausibility | suspicious | low | Thousands of records touched by one user in the small hours, the signature of an unreviewed script run. |

Additional validity sub-checks confirmed by regex constants in code (not separately
titled, folded into `validity.email` / `validity.website`):
- Email pattern: `^[^\s@,;]+@[^\s@.,;]+(\.[^\s@.,;]+)+$`, plus a max length of 254
  characters.
- Website/URL pattern: `^(https?://)?([\w-]+\.)+[a-z]{2,}(/\S*)?$` (case-insensitive).
- Phone normalization for matching strips all non-digits and, for duplicate-matching
  purposes, keeps the **last 10 digits** as the comparable key.
- Company-name normalization for duplicate matching: lowercases, strips punctuation/
  whitespace, and strips common legal suffixes (`pvt`, `private`, `ltd`, `limited`,
  `inc`, `incorporated`, `llc`, `corp`, `corporation`, `co`, `gmbh`).

**Correction — `plausibility.repeatedValue` has a real bug, resolved as a code fix.**
The phone-matching grouping key only checks that a record's signature object exists,
not that its `phone` field is actually non-empty — every record with a blank phone
collapses into the same shared, non-empty grouping key (`${module}::`), so five or
more records that simply have no phone number on file will incorrectly trip this rule
as if they shared one real phone number. The parallel email-matching code already
guards this correctly (`l?.email ?` before building its key). Production must fix the
phone path to match — this was never an intended behavior, just an asymmetry the two
otherwise-identical code paths shouldn't have had.

### 6.3 Configurable rule engine parameters (confirmed defaults)

```
staleDays: 365
minRecordsPerUser: 25
burstSize: 15
burstWindowMinutes: 5
repeatedValueThreshold: 5
duplicateSuspectedFloor: 0.70
duplicateConfirmedFloor: 0.90
excludeBulkUsers: true
bulkUserPatterns: ["import","integration","migration","system","api","data load","bulk"]
maxExamplesPerRule: 200
stageAware: true
```

Interpretation:
- **staleDays (365):** a record untouched for 365+ days trips `freshness.stale`.
- **minRecordsPerUser (25):** the volume floor below which a user is shown
  "Insufficient data" rather than a score, in the Users tab and in mover calculations.
- **burstSize / burstWindowMinutes (15 / 5):** `plausibility.burst` fires when one user
  creates ≥15 records within any rolling 5-minute window.
- **repeatedValueThreshold (5):** `plausibility.repeatedValue` fires when the same
  phone/email value appears on ≥5 distinct records.
- **duplicateSuspectedFloor / duplicateConfirmedFloor (0.70 / 0.90):** the fuzzy
  confidence bands described in §6.7.
- **maxExamplesPerRule (200):** intended as a cap on how many example records are
  retained/shown per rule. **Correction:** this value is defined but never actually
  consumed anywhere in the widget — the real per-rule example cap is a hardcoded,
  inconsistently-applied `3`. Production should either wire this config value up for
  real or remove it so it stops implying a control that doesn't exist.
- **stageAware:** governs whether `completeness.stageRequired` and similar rules gate
  on the record's current stage value.

These are designed to be operator-editable per scan (the `setRules` reducer action
exists specifically to merge a partial patch into `scanConfig.rules`), matching the
deck's "stored per client and tunable" requirement. **Correction:** `setRules` is wired
into the reducer and context, but has **zero call sites anywhere in the render tree** —
no UI control currently invokes it. The threshold panel this implies was designed but
never built. Production needs to build the control panel; the design intent itself
(tunable, not hardcoded) is not in question.

### 6.4 Domain weights and measurability (confirmed, exact — with resolution)

| Domain | Weight | Feeds state | Measurable in this widget | Notes |
|---|---|---|---|---|
| Completeness | 20 | incomplete | Yes | |
| Duplication | 20 | suspected/confirmed_duplicate | Yes | |
| Validity | 15 | inaccurate | Yes | |
| Plausibility | 10 | suspicious | Yes | |
| Freshness | 10 | incomplete, inaccurate | Yes | |
| Referential integrity | 10 | inaccurate | Yes | |
| Configuration hygiene | 8 | org-level only | Widget: crude proxy only | See resolution below |
| PII and access | 4 | org-level only | **No** | Code-level `unavailableReason`: *"Needs profile, permission and field-masking APIs that the widget SDK does not expose. Requires the Catalyst backend."* |
| Automation health | 3 | org-level only | **No** | Code-level `unavailableReason`: needs workflow/function/scheduler APIs the widget SDK does not expose; requires the Catalyst backend. |

The widget declares that 2 of the 9 domains (7 of 100 weighted points) are structurally
impossible to compute from a Zoho CRM embedded widget's permission surface. These
require a server-side integration user with elevated (still read-only, but broader —
profile/permission/workflow/function-log) scopes. PII and Automation Health scoring
must run from the Catalyst backend collector, not from anything equivalent to this
widget.

**Configuration Hygiene — resolved, not actually unmeasurable.** The widget's own
implementation of this domain is a crude "% of fields with any value" proxy — not the
deck's real definition (unused modules, dead workflows, layout sprawl), and it leaks
the same org-global value into every module's slice regardless of that module's actual
configuration. Unlike PII/Automation, this domain **can** be properly computed:
Zoho's Workflow Rules API (with `last_execution` timestamps and a `deprecated` flag —
direct dead-workflow detection), a Workflow Rule Usage Report, and a Layouts Metadata
API (reports whether a field/section is actually used) together provide everything
needed, given the right scopes (`ZohoCRM.settings.workflow_rules.READ`,
`ZohoCRM.settings.layouts.READ`). Production should build the real thing, not port the
widget's proxy.

**Resolved policy for handling PII/Automation's non-applicability in the overall
score:** renormalize the overall score to measurable/applicable domains only, but
**disclose it in the UI** — e.g. "92 of 100 possible points measured — PII and
Automation Health need broader access." Silent renormalization (what the widget does)
was rejected as a trust risk; withholding the score entirely was rejected as too
restrictive for early product stages.

### 6.5 Scoring formula — resolved

**Resolved formula (simple ratio, no severity weighting):**
```
domain_score = 100 × (1 − offending_records / eligible_records)
overall_score = Σ (weight_i / 100 × domain_score_i)  for i in the applicable, measured domains
```
computed per domain, per slice (org / module / user / date-range — one formula at every
level, only the eligible-record set changes; this also resolves an earlier open
question — user-level scoring uses this exact formula too, not a separate
percent-of-proper-records metric. Percent-proper is retained only as a secondary
display statistic, never as the score itself).

**Correction — this differs from what the widget actually implements.** The widget
computes a *severity-weighted mean* of per-rule pass rates (`{critical:3, high:2.5,
medium:2, low:1.5, info:1}`), not the simple ratio above, and renormalizes the overall
score silently rather than disclosing it. Both of these were open product decisions;
both are now resolved in favor of the simpler, disclosed approach shown above — the
widget's severity-weighted, silently-renormalized version should **not** be carried
into production.

A domain with zero eligible records for a given slice is **excluded from that slice's
rollup**, not scored as zero (explicit "not applicable is not zero" rule, confirmed by
the `null → "na"` matrix-cell rendering) — this part of the widget's behavior is
correct and carries forward unchanged.

### 6.6 Score verdict bands

**Org-level band** (function `Zh` in code):
| Score | Band |
|---|---|
| ≥ 85 | Strong ("Healthy") |
| 70–84 | Stable |
| 55–69 | Attention ("Needs attention") |
| < 55 | Risk ("At risk") |

Note: this differs from the deck's slide-15 example, which labels a score of 53 as
"At risk" — consistent with the < 55 → risk band above, confirming the two sources
agree at that data point.

**Secondary 3-tier band** (function `Xh`, used elsewhere in the UI, exact
usage/location not fully traced — flag for confirmation, likely a compact/summary
badge):
| Score | Band |
|---|---|
| ≥ 80 | good |
| 60–79 | warn |
| < 60 | bad |

**User coaching band** (function `Ng`, confirmed):
| Score | Band | Suggested action (confirmed copy) |
|---|---|---|
| ≥ 70 | Exemplary | "Use as model" |
| 50–69 | Solid | "No action" |
| 30–49 | Needs coaching | "Coach on the weakest domain" |
| < 30 | Needs intervention | "Review with team lead" |
| (below minRecordsPerUser) | Insufficient data | "Below threshold" |

**Matrix cell band** (module × domain grid, function `Iu`, confirmed):
| Score | Band |
|---|---|
| null (not applicable) | na |
| ≥ 97 | excellent |
| 90–96 | good |
| 80–89 | ok |
| 70–79 | fair |
| 55–69 | warn |
| < 55 | bad |

These are four *distinct* banding functions used in different parts of the UI — a
production spec should preserve this distinction rather than collapsing them into one
"score band" concept; they were clearly tuned independently for their specific visual
context (a compact org gauge tolerates a coarser 4-band scale; a dense matrix of ~63
cells needs a finer 6-band scale to stay visually informative).

### 6.7 Duplicate detection algorithm (confirmed, precise)

1. **Scope**: **resolved policy — module-scoped only for v1.** The widget's actual
   blocking keys are all `${module}|...`-prefixed, meaning it never matches across
   modules despite what the deck's module list might imply. This is now the confirmed
   production policy too: cross-module matching (e.g. Leads vs. Contacts) is explicitly
   deferred, not a widget limitation to fix. Requires at least 2 eligible records in a
   module to run at all.
2. **Signature extraction** per record: `{ strongId (uppercased), email (lowercased),
   phone (normalized to last-10-digits), name, company (normalized: lowercased,
   punctuation/whitespace stripped, legal-entity suffixes stripped) }`.
3. **Blocking**: records are bucketed by exact match on `module|id|<strongId>`,
   `module|em|<email>`, and `module|ph|<phone>` (phone only blocks when the normalized
   value is ≥10 digits), plus an undocumented name-prefix key
   `module|nm|<first-8-chars-of-name-hash>` not mentioned anywhere else in either
   source. **Correction — block-size handling:** the widget silently skips any block
   larger than 40 records (comparisons inside that block never happen, with no
   indication to the user). Resolved policy: oversized blocks must be processed or
   explicitly flagged in the output — never silently dropped.
4. **Weighted fuzzy scoring** within each block, field weights:
   `strongId: 0.50, email: 0.25, phone: 0.20, name: 0.18, company: 0.07`.
   For exact-comparable fields (strongId/email/phone) the weight contributes fully on
   an exact match. For name/company, weight is scaled by a string-similarity score
   (0–1) before being added to the numerator. Final confidence =
   `matched_weighted_sum / considered_weighted_sum` (i.e. only fields present on both
   records count toward the denominator — a record missing a company name isn't
   penalized for it, but also can't earn credit for a company match).
5. **Classification — resolved, the 0.90 floor is now absolute.** Confidence in
   **[0.70, 0.90)** → Suspected duplicate. Confidence **≥ 0.90 AND at least two strong
   fields (from strongId/email/phone) agree exactly** → Confirmed duplicate.
   **Correction:** the widget's actual confirmation logic includes two shortcut paths
   that bypass the 0.90 floor entirely — exact strongId match confirms unconditionally
   (kept, see below), but so does exact-email-plus-exact-phone, and exact-email-plus
   very-high name similarity, **regardless of the overall confidence score**. These
   shortcuts are removed in the resolved policy: the 0.90 floor is absolute with no
   bypass. The one exception that remains legitimate is an **exact match on a strong
   statutory identifier** (GSTIN/PAN/etc.) — that is independent corroboration strong
   enough to stand on its own, not a floor bypass, and continues to auto-confirm.

### 6.8 Plausibility detection (confirmed rule set, §6.2) — set-level, not per-record

Unlike every other domain, plausibility rules require the **whole extract for a
module in memory simultaneously** (burst detection needs every record's creator +
timestamp; repeated-value detection needs every record's phone/email compared against
every other) — this is the specific reason, stated explicitly in the deck and borne
out by the rule shapes in code, that the rule engine cannot run as a per-record Zoho
Deluge function and must run as a batch process over a full extract.

---

## 7. Non-functional / architectural requirements

Confirmed from code:
- **Zoho Embedded App SDK dependency**: `ZOHO.embeddedApp.init` must be called before
  any live-org functionality is available; script loaded from
  `https://live.zwidgets.com/js-sdk/1.2/ZohoEmbededAppSDK.min.js`.
- **Light-mode only**: `<meta name="color-scheme" content="only light">` — the widget
  explicitly opts out of following the host page/OS dark-mode preference because it
  sits inside a light Zoho page.
- **Client-side persistence**: scan configuration only (`scan-config-v2` in
  localStorage). No record data or scores are persisted client-side beyond the active
  session's in-memory `scan`/`cube` state.
- **Localization scaffold present but minimal**: `translations/en.json` contains only
  5 keys (`widget.title`, `widget.subtitle`, `action.run`, `action.cancel`,
  `action.newScan`) — the vast majority of UI copy is hardcoded English in the bundle,
  not routed through the translation layer. A production i18n requirement would need
  to externalize substantially more strings than currently exist.
- **API call resilience**: dispatched/retried/failed counters are tracked live during
  extraction, implying retry-with-backoff behavior is an expected part of the
  extractor, not optional.

Confirmed from deck (architecture intent for the real backend, not present in this
artifact):
- Entire pipeline runs inside Catalyst, India data centre; no client record leaves
  region.
- OAuth self-client, read-only scopes only, per-org token isolation, API credit
  budgeter, rate-limit guard.
- Bulk Read API / COQL pager with watermark-based resume for extraction.
- Field values discarded after evaluation; only record identifiers, states, and
  dimension keys persist — **this widget's own data-retention behavior (record
  signatures discarded after duplicate matching, no raw field export anywhere in the
  UI) is directly consistent with this stated backend constraint**, i.e. the client
  was built to the same discipline the backend is supposed to enforce.
- Hard per-run API credit ceiling; full scans default to running outside business
  hours.

---

## 8. Commercial/process rules that constrain functional behavior

These are not algorithmic rules but they shape required UI behavior and must be
treated as functional requirements, not optional copy:

1. **User lens must never present as a ranking.** Coaching bands only; movement
   (trend) must be visually weighted at least as heavily as absolute position. This is
   enforced in this spec by the Users tab requiring sparkline/trend display and by the
   band vocabulary explicitly avoiding numeric rank language ("Exemplary/Solid/Needs
   coaching/Needs intervention", never "#1/#2/#3").
2. **A false "suspicious" flag is treated as the single most damaging failure mode.**
   Functional consequence: every plausibility/suspicious finding must carry a stated,
   specific reason (never generic), a minimum burst/threshold size before firing
   (`burstSize: 15`, `repeatedValueThreshold: 5` — these floors exist specifically to
   suppress low-confidence noise), and must route to a human-review fix action
   (`audit-suspicious`), never an automated write.
3. **Cost must be shown before a scan runs**, and **projected score gain must be shown
   before a remediation action runs** — both are "no surprise" requirements that apply
   equally to read (scan) and write (fix) operations.
4. **Nothing sold as a scan output may include field values outside the client's own
   region/system** — record identifiers and states only in every export path
   (`module-matrix.csv`, `user-accountability.csv`, `remediation-plan.csv`, "send to
   fix list").

---

## 9. Data retention — resolved boundary

**Correction:** an earlier revision of this document asserted the widget only ever
retains `{recordId, module, state, failedRuleIds, reasonText, confidence?}`. That's
incomplete — the actual downstream "fact" object also carries a record `label`
(display name) alongside `createdById` and similar attribution fields, which are
exported in the CSV paths, not just used internally. This is more than "identifiers and
states only" as originally claimed.

**Resolved retention boundary** (the open question this raised — is a display label a
permissible "dimension key" or a forbidden "field value"? — is now settled):

**Permitted to persist:** record IDs, module, state, failed rule IDs, stage, timestamps,
and display names needed for the product to function (a record or user has to be
nameable for the report to be usable) — these are dimension keys.

**Not permitted:** actual field values embedded in reason-string content. Reason
strings must be **templated**, never echoing a real value — "GSTIN failed checksum,"
never the GSTIN itself. Duplicate-matching signatures (the normalized phone/email/name/
company keys used for blocking and scoring) must be **cleared once that scan step
completes** — they're a legitimate, necessary intermediate, not a value that should
outlive the classification step.

This should be treated as a hard constraint on the production data model (§5's "Module
extract record" shape must not outlive the classification step for any given scan, and
the "fact"/record-state shape must not exceed the permitted list above).

---

## 10. Explicit gaps between this artifact and a production system

For traceability, everything below is asserted by the deck but has **no corresponding
implementation** in the widget bundle examined — a production build must design these
from the deck's requirements alone, since there is no reference code:

- Live OAuth self-client connect/token-vault flow (widget only has SDK-detection plus
  real read calls against the connected org — see §3's correction; it still has no real
  OAuth grant/token-vault flow of its own, that part of the finding stands).
- Bulk Read/COQL extraction with watermark resume (the widget's live path, now
  confirmed real per §3, uses simple client-side `getAllRecords` paging with JS-side
  date filtering — appropriate for a browser widget bound by the Embedded App SDK, but
  not a substitute for the production Catalyst-side Bulk Read/COQL extractor this
  describes; the two were never meant to be the same thing).
- PII/Access domain scoring (explicitly declared unmeasurable by the widget itself —
  needs backend-only APIs, see §6.4). Automation Health, same. Configuration Hygiene is
  **no longer in this list** — resolved as buildable, see §6.4.
- Action-centre write operations: preview, snapshot-before-write, one-click rollback.
- PDF report generation (SmartBrowz-equivalent).
- Scheduling, alert floors, and the monitoring/retainer delivery mode.
- Cross-object modules beyond Leads/Contacts/Accounts/Deals/Vendors (Desk tickets,
  Books invoices, Creator apps are referenced in UI copy/mock data but not exercised by
  any rule in the traced rule catalogue — the module set actually driving rule logic
  is `Leads, Contacts, Accounts, Deals, Vendors` plus duplication scope limited to
  `Leads, Contacts, Accounts, Vendors`).
- Multi-CRM source support (out of scope for this artifact entirely; Zoho-only
  throughout).
- Org Audit mode (admin-gated, org-wide scanning) — deferred by product decision, not a
  widget limitation; see `docs/decisions-log.md` Section B5. Only Personal Check mode
  (scoped to whatever the connecting person's own Zoho profile can see) is in scope for
  the current build.

---

## 11. Open questions — all resolved

Every open question this document originally raised here has been resolved through a
structured adjudication process (D1–D17) plus follow-up product decisions and API
research. Nothing below remains open. Resolutions are recorded in
`docs/decisions-log.md`, which is now the authoritative source, and have been folded
into the relevant sections above (state precedence → §6.1, scoring formula → §6.5,
duplicate policy → §6.7, retention boundary → §9, rule count → §6.2). The original
three open questions, for traceability:

1. **State-assignment precedence** — resolved. Explicit, confirmed in code (§6.1), not
   inferred as originally thought.
2. **Secondary band function (`Xh`)** — its exact UI usage remains untraced, but this
   was a minor documentation gap, not a blocking decision; not pursued further since it
   doesn't affect the production build.
3. **Full ~70-rule catalogue** — resolved as a known, scoped task (§6.2's correction):
   22 rule families exist as a template; ~48 more need to be authored fresh, following
   the same shape (`id, title, domain, state, severity, description, fixKey`).
