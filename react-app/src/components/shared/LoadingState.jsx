export default function LoadingState({ label = "Loading" }) {
  return (
    <div className="loading-state" role="status">
      <span className="loading-state-dot" aria-hidden="true" />
      <span className="eyebrow">{label}</span>
    </div>
  );
}
