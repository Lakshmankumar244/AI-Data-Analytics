import "./ConnectZohoPanel.css";

export default function ConnectZohoPanel({ onConnect, connecting, notice }) {
  return (
    <div>
      <p className="eyebrow">Accessible to your account</p>
      <div className="connect-panel">
        <div className="connect-panel-icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
            <path d="M9 6L4 12l5 6M15 6l5 6-5 6" />
          </svg>
        </div>
        <p className="connect-panel-title">Connect your Zoho CRM</p>
        <p className="connect-panel-body">
          We&apos;ll show the modules and record counts visible under your Zoho
          login once you connect.
        </p>
        {notice && <p className="connect-panel-notice">{notice}</p>}
        <button
          type="button"
          className="btn btn-primary connect-panel-btn"
          onClick={onConnect}
          disabled={connecting}
        >
          {connecting ? "Redirecting\u2026" : "+ Create Zoho CRM connection"}
        </button>
      </div>
    </div>
  );
}
