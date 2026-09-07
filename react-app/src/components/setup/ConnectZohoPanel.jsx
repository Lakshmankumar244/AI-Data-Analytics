import { Button } from "@/components/ui/button";

export default function ConnectZohoPanel({ onConnect, connecting, notice }) {
  return (
    <div className="max-w-[36rem]">
      <h1 className="font-heading text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
        Connect Zoho CRM
      </h1>
      <p className="mt-3 max-w-[34rem] text-sm leading-relaxed text-ink-soft">
        The scan will read modules visible under this login.
      </p>

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
