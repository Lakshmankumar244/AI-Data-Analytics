export default function LoadingState({ label = "Loading" }) {
  return (
    <div className="loading-state" role="status">
      <span className="eyebrow">{label}</span>
      <span className="loading-state-spinner" aria-hidden="true" />
    </div>
  );
}
