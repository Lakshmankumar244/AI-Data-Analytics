export default function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state card">
      <p className="eyebrow" style={{ color: "var(--risk)" }}>
        Something went wrong
      </p>
      <p style={{ marginTop: "var(--sp-2)", color: "var(--ink-soft)" }}>
        {message || "The scan could not finish. Nothing has been changed in your CRM."}
      </p>
      {onRetry && (
        <button className="btn btn-secondary" style={{ marginTop: "var(--sp-4)" }} onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
