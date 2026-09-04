export default function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state" role="alert">
      <p className="eyebrow" style={{ color: "var(--risk)" }}>
        Something went wrong
      </p>
      <p className="error-state-title">The workspace could not continue</p>
      <p className="text-body">
        {message || "The scan could not finish. Nothing has been changed in your CRM."}
      </p>
      {onRetry && (
        <button type="button" className="btn btn-secondary" style={{ marginTop: "var(--sp-3)" }} onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
