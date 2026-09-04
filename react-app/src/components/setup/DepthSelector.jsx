import Dropdown from "../shared/Dropdown";

const DEPTHS = [
  { id: "quick", label: "Quick", cap: "1,000 / module", note: "Smoke test after a fix. Cheapest run." },
  { id: "presales", label: "Presales", cap: "5,000 / module", note: "Enough to produce a real picture." },
  { id: "deep", label: "Deep", cap: "20,000 / module", note: "Enough volume for plausibility checks." },
  { id: "full", label: "Full", cap: "Uncapped", note: "Everything in range." },
];

const DEPTH_OPTIONS = DEPTHS.map((depth) => ({
  id: depth.id,
  label: `${depth.label} \u00b7 ${depth.cap}`,
}));

export default function DepthSelector({ value, onChange }) {
  return (
    <Dropdown
      label="Scan depth"
      variant="field"
      value={value}
      options={DEPTH_OPTIONS}
      onChange={onChange}
    />
  );
}
