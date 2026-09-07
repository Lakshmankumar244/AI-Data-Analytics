// Every score-to-band mapping in the product, in one place, matching the
// exact thresholds confirmed in the functional spec / decisions log.
// Components ask for a band, they never hardcode a threshold themselves.

// Org-level verdict band (4-tier)
export const ORG_BANDS = [
  { min: 85, id: "strong", label: "Strong", color: "var(--strong)", soft: "var(--strong-soft)" },
  { min: 70, id: "stable", label: "Stable", color: "var(--stable)", soft: "var(--stable-soft)" },
  { min: 55, id: "attention", label: "Needs attention", color: "var(--attention)", soft: "var(--attention-soft)" },
  { min: 0, id: "risk", label: "At risk", color: "var(--risk)", soft: "var(--risk-soft)" },
];

export function orgBand(score) {
  return ORG_BANDS.find((b) => score >= b.min) ?? ORG_BANDS[ORG_BANDS.length - 1];
}

// User coaching band (Users report). Driven by the user quality percentage
// once the minimum-record floor is met — not the org/module verdict.
export const USER_BANDS = [
  {
    min: 70,
    id: "exemplary",
    label: "Exemplary",
    action: "Use as model",
    color: "var(--strong)",
    soft: "var(--strong-soft)",
  },
  {
    min: 50,
    id: "solid",
    label: "Solid",
    action: "No action",
    color: "var(--stable)",
    soft: "var(--stable-soft)",
  },
  {
    min: 30,
    id: "coaching",
    label: "Needs coaching",
    action: "Coach on the weakest domain",
    color: "var(--attention)",
    soft: "var(--attention-soft)",
  },
  {
    min: 0,
    id: "intervention",
    label: "Intervention",
    action: "Review with team lead",
    color: "var(--risk)",
    soft: "var(--risk-soft)",
  },
];

export const INSUFFICIENT_BAND = {
  id: "insufficient",
  label: "Insufficient data",
  action: "Below threshold",
  color: "var(--muted)",
  soft: "var(--surface-sunken)",
};

export function userBand(score, insufficient = false) {
  if (insufficient || score === null || score === undefined) {
    return INSUFFICIENT_BAND;
  }
  return USER_BANDS.find((b) => score >= b.min) ?? USER_BANDS[USER_BANDS.length - 1];
}

// Matrix cell band (6-tier, used on the Modules screen - Phase 3)
export const MATRIX_BANDS = [
  { min: 97, id: "excellent", label: "Excellent", color: "var(--matrix-excellent)", soft: "var(--matrix-excellent-soft)" },
  { min: 90, id: "good", label: "Good", color: "var(--matrix-good)", soft: "var(--matrix-good-soft)" },
  { min: 80, id: "ok", label: "OK", color: "var(--matrix-ok)", soft: "var(--matrix-ok-soft)" },
  { min: 70, id: "fair", label: "Fair", color: "var(--matrix-fair)", soft: "var(--matrix-fair-soft)" },
  { min: 55, id: "warn", label: "Needs attention", color: "var(--matrix-warn)", soft: "var(--matrix-warn-soft)" },
  { min: 0, id: "bad", label: "Poor", color: "var(--matrix-bad)", soft: "var(--matrix-bad-soft)" },
];

export function matrixBand(score) {
  if (score === null || score === undefined) {
    return { id: "na", label: "N/A", color: "var(--muted)", soft: "var(--surface-sunken)" };
  }
  return MATRIX_BANDS.find((b) => score >= b.min) ?? MATRIX_BANDS[MATRIX_BANDS.length - 1];
}

// Six record states - order matters (this IS the precedence order, D3)
export const RECORD_STATES = [
  { id: "proper", label: "Proper", color: "var(--state-proper)", soft: "var(--state-proper-soft)" },
  { id: "incomplete", label: "Incomplete", color: "var(--state-incomplete)", soft: "var(--state-incomplete-soft)" },
  { id: "inaccurate", label: "Inaccurate", color: "var(--state-inaccurate)", soft: "var(--state-inaccurate-soft)" },
  { id: "suspicious", label: "Suspicious", color: "var(--state-suspicious)", soft: "var(--state-suspicious-soft)" },
  { id: "suspected_duplicate", label: "Suspected duplicate", color: "var(--state-suspected-duplicate)", soft: "var(--state-suspected-duplicate-soft)" },
  { id: "confirmed_duplicate", label: "Confirmed duplicate", color: "var(--state-confirmed-duplicate)", soft: "var(--state-confirmed-duplicate-soft)" },
];

export function stateMeta(id) {
  return RECORD_STATES.find((s) => s.id === id);
}

export const DOMAIN_LABELS = {
  completeness: "Completeness",
  duplication: "Duplication",
  validity: "Validity",
  plausibility: "Plausibility",
  freshness: "Freshness",
  integrity: "Referential integrity",
  config: "Config hygiene",
  pii: "PII and access",
  automation: "Automation health",
};
