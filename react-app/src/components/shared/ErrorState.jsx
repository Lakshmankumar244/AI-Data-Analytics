import { Button } from "@/components/ui/button";

export default function ErrorState({ message, onRetry }) {
  return (
    <div className="flex min-w-0 flex-col items-start gap-2" role="alert">
      <p className="eyebrow text-risk">Something went wrong</p>
      <p className="font-heading text-base font-semibold tracking-tight text-ink">
        The workspace could not continue
      </p>
      <p className="text-sm leading-normal text-ink-soft">
        {message || "The scan could not finish. Nothing has been changed in your CRM."}
      </p>
      {onRetry && (
        <Button type="button" variant="outline" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
