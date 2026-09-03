export const MOCK_GAUGE_META = {
  duplicates: 58,
  modules: 3,
};

export const MOCK_STAT_CARDS = [
  { id: "clean", label: "Clean records", value: 3200, score: 92 },
  { id: "attention", label: "Need attention", value: 670, score: 60 },
  { id: "fabricated", label: "Looks fabricated", value: 72, score: 30 },
  { id: "critical", label: "Users needing help", value: 8, score: 20 },
];

export const MOCK_STATE_BREAKDOWN = {
  proper: 3200,
  incomplete: 480,
  inaccurate: 190,
  suspicious: 72,
  suspected_duplicate: 46,
  confirmed_duplicate: 12,
};

export const MOCK_CREATED_IN_PERIOD = [
  { label: "03", score: 68 },
  { label: "04", score: 76 },
  { label: "05", score: 58 },
  { label: "06", score: 88 },
  { label: "07", score: 72 },
  { label: "08", score: 93 },
  { label: "09", score: 81 },
];

export const MOCK_MOVERS = [
  { type: "domain", label: "Completeness", delta: 6 },
  { type: "module", label: "Deals", delta: -4 },
  { type: "domain", label: "Plausibility", delta: 3 },
];

export const MOCK_KEY_FINDINGS = [
  { severity: "critical", text: "Inactive owners still hold customer records." },
  { severity: "high", text: "Required contact details are missing in active leads." },
  { severity: "medium", text: "Several records have not been updated recently." },
];
