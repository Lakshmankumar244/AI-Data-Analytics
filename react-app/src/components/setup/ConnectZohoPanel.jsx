import { Button } from "@/components/ui/button";

export default function ConnectZohoPanel({ onConnect, connecting, notice }) {
  return (
    <div className="max-w-[36rem]">
      <p className="eyebrow">Before the scan</p>
      <h1 className="mt-3 font-heading text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
        Connect the Zoho login this scan will read
      </h1>
      <p className="mt-4 max-w-[34rem] text-sm leading-relaxed text-ink-soft">
        We&apos;ll list the modules and record counts visible under that login.
        The scan itself never writes back to CRM.
      </p>

      <ol className="mt-8 flex flex-col gap-3 text-[13px] text-ink-soft sm:flex-row sm:items-baseline sm:gap-8">
        <li className="flex items-baseline gap-2">
          <span className="font-heading text-base font-semibold text-brand">01</span>
          Connect
        </li>
        <li className="flex items-baseline gap-2">
          <span className="font-heading text-base font-semibold text-ink-muted">02</span>
          Scope
        </li>
        <li className="flex items-baseline gap-2">
          <span className="font-heading text-base font-semibold text-ink-muted">03</span>
          Read
        </li>
      </ol>

      {notice && (
        <p className="mt-6 max-w-md text-[13px] text-ink-soft">{notice}</p>
      )}

      <Button
        type="button"
        size="lg"
        className="mt-8 min-w-[12rem]"
        onClick={onConnect}
        disabled={connecting}
      >
        {connecting ? "Redirecting\u2026" : "Connect Zoho CRM"}
      </Button>
    </div>
  );
}
