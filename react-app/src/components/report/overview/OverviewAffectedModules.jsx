import { orgBand } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import { Button } from "@/components/ui/button";

export default function OverviewAffectedModules({
  modules = [],
  onOpenModule,
  onOpenModules,
}) {
  if (!modules.length) {
    return (
      <p className="text-[13px] leading-relaxed text-ink-soft">
        Module-level scores are not available for this view.
      </p>
    );
  }

  return (
    <div className="min-w-0">
      <ul className="m-0 flex list-none flex-col p-0">
        {modules.map((module) => {
          const band = orgBand(module.overall);
          return (
            <li key={module.apiName}>
              <button
                type="button"
                className="flex w-full min-w-0 items-center gap-3 px-1 py-2 text-left hover:bg-surface print:pointer-events-none"
                onClick={() => onOpenModule?.(module.apiName)}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-semibold text-ink">
                    {module.label}
                  </span>
                  <span className="mt-0.5 block text-[12px] text-ink-muted">
                    {formatNumber(module.recordCount)} records
                  </span>
                </span>
                <span className="relative h-1.5 w-[min(6.5rem,22%)] overflow-hidden bg-line">
                  <span
                    className="absolute inset-y-0 left-0"
                    style={{
                      width: `${module.overall}%`,
                      background: band.color,
                    }}
                  />
                </span>
                <span
                  className="mono w-8 text-right text-[15px] font-semibold tracking-tight"
                  style={{ color: band.color }}
                >
                  {module.overall}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {onOpenModules && (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="mt-1 h-auto px-1 print:hidden"
          onClick={onOpenModules}
        >
          All modules
        </Button>
      )}
    </div>
  );
}
