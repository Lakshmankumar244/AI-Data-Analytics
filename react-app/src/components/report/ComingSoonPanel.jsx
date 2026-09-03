import "./ComingSoonPanel.css";

export default function ComingSoonPanel({ tabLabel }) {
  return (
    <div className="coming-soon-panel">
      <p className="eyebrow">Coming soon</p>
      <h2>{tabLabel} isn't built yet</h2>
      <p className="coming-soon-body">
        This view is scoped for a later build phase. The Overview tab covers what's
        available right now.
      </p>
    </div>
  );
}
