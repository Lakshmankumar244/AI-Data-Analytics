import Dropdown from "../shared/Dropdown";

const CLOCK_OPTIONS = [
  { id: "created", label: "Created time" },
  { id: "modified", label: "Modified time" },
];

export default function ClockToggle({ value, onChange }) {
  return (
    <Dropdown
      label="Clock"
      variant="field"
      value={value}
      options={CLOCK_OPTIONS}
      onChange={onChange}
    />
  );
}
