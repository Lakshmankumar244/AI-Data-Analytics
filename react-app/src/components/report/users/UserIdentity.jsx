function initials(name) {
  const parts = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export default function UserIdentity({ name, modules = [] }) {
  const unassigned = name === "Unassigned" || name === "Unknown owner";

  return (
    <div className={`user-identity${unassigned ? " user-identity-unassigned" : ""}`}>
      <span className="user-identity-avatar" aria-hidden="true">
        {initials(name)}
      </span>
      <div className="user-identity-text">
        <strong className="user-identity-name">{name}</strong>
        <p className="user-identity-meta">
          {modules.length ? modules.join(", ") : "No modules in this view"}
        </p>
        <p className="user-identity-team">Team not in this scan</p>
      </div>
    </div>
  );
}
