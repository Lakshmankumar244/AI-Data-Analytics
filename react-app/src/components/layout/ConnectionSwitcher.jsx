import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Plus } from "lucide-react";
import { useAppDispatch, useAppState, useActions } from "../../state/AppContext";
import * as api from "../../data/client";
import {
  activeConnectionLabels,
  connectionKey,
  connectionSummary,
  listSwitchableConnections,
  parseConnectionKey,
  providerLabel,
} from "../../data/activeConnection";
import { cn } from "@/lib/utils";
import { Toast } from "@/components/ui/toast";

export function ConnectionSwitcher() {
  const { connection, salesforceConnection, activeConnection } = useAppState();
  const dispatch = useAppDispatch();
  const { showConnect } = useActions();
  const [open, setOpen] = useState(false);
  const [switchingKey, setSwitchingKey] = useState(null);
  const [toast, setToast] = useState(null);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const optionRefs = useRef(new Map());
  const menuId = useId();
  const labels = activeConnectionLabels(activeConnection);
  const options = listSwitchableConnections(
    connection,
    salesforceConnection,
    activeConnection?.connectionKey
  );
  const busy = Boolean(switchingKey);

  useEffect(() => {
    if (!open) return undefined;
    function handleOutside(event) {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    function handleKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", handleOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const selectedKey = activeConnection?.connectionKey;
    const firstKey = options[0]?.connectionKey;
    const selected =
      optionRefs.current.get(selectedKey) || optionRefs.current.get(firstKey);
    selected?.focus();
    return undefined;
  }, [open]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(timer);
  }, [toast]);

  if (!labels && options.length === 0) return null;

  function focusOption(index) {
    const option = options[index];
    if (!option) return;
    optionRefs.current.get(option.connectionKey)?.focus();
  }

  function handleMenuKeyDown(event) {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key) || options.length === 0) return;
    event.preventDefault();
    const currentIndex = options.findIndex(
      (option) => optionRefs.current.get(option.connectionKey) === document.activeElement
    );
    if (event.key === "Home") {
      focusOption(0);
      return;
    }
    if (event.key === "End") {
      focusOption(options.length - 1);
      return;
    }
    const delta = event.key === "ArrowDown" ? 1 : -1;
    const nextIndex =
      currentIndex < 0
        ? event.key === "ArrowDown"
          ? 0
          : options.length - 1
        : (currentIndex + delta + options.length) % options.length;
    focusOption(nextIndex);
  }

  async function selectConnection(option) {
    if (!option || option.connectionKey === activeConnection?.connectionKey) {
      setOpen(false);
      triggerRef.current?.focus();
      return;
    }
    const parsed = parseConnectionKey(option.connectionKey);
    if (!parsed) return;
    setSwitchingKey(option.connectionKey);
    try {
      const selected = await api.activateCrmConnection(
        parsed.provider,
        parsed.connectionId
      );
      const selectedId = String(selected?.connectionId || "").trim();
      if (!selectedId) {
        throw new Error("The connection could not be selected");
      }
      const otherProvider =
        parsed.provider === "zoho"
          ? await api.getSalesforceConnection().catch(() => null)
          : await api.getConnection().catch(() => null);
      dispatch({
        type: "connectionLoaded",
        connection: parsed.provider === "zoho" ? selected : otherProvider,
        salesforceConnection:
          parsed.provider === "salesforce" ? selected : otherProvider,
        activeConnectionKey: connectionKey(parsed.provider, selectedId),
      });
      setOpen(false);
      triggerRef.current?.focus();
    } catch (error) {
      setToast({
        message:
          error instanceof Error
            ? error.message
            : "The connection could not be selected",
      });
    } finally {
      setSwitchingKey(null);
    }
  }

  function handleConnectAnother() {
    setOpen(false);
    showConnect();
  }

  return (
    <div className="relative min-w-0" ref={rootRef}>
      <button
        ref={triggerRef}
        type="button"
        className={cn(
          "flex max-w-[min(280px,46vw)] min-w-0 items-center gap-1 rounded-[var(--radius-md)] border-0 bg-transparent px-1.5 py-0.5 text-right",
          "hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
          open && "bg-surface-sunken"
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label="Switch connection"
        disabled={busy}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className="flex min-w-0 flex-col items-end gap-0.5">
          {labels?.organization && (
            <span className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-medium text-ink">
              {labels.organization}
            </span>
          )}
          {labels?.account && (
            <span className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-ink-muted">
              {labels.account}
            </span>
          )}
        </span>
        <ChevronDown
          className={cn(
            "size-3.5 shrink-0 text-ink-muted transition-transform",
            open && "rotate-180"
          )}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          className="absolute top-[calc(100%+8px)] right-0 z-40 w-[min(18.5rem,calc(100vw-2rem))] rounded-md border border-line bg-surface p-2 shadow-[var(--shadow-float)]"
          onKeyDown={handleMenuKeyDown}
        >
          <p className="px-2.5 py-1.5 text-[11px] font-medium tracking-wide text-ink-muted uppercase">
            Switch connection
          </p>
          <div
            id={menuId}
            role="listbox"
            aria-label="Switch connection"
            aria-busy={busy || undefined}
            className="flex flex-col gap-0.5"
          >
            {options.map((option) => {
              const selected =
                option.connectionKey === activeConnection?.connectionKey;
              const pending = switchingKey === option.connectionKey;
              return (
                <button
                  key={option.connectionKey}
                  ref={(node) => {
                    if (node) optionRefs.current.set(option.connectionKey, node);
                    else optionRefs.current.delete(option.connectionKey);
                  }}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  disabled={busy}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-[var(--radius-md)] border-0 bg-transparent px-2.5 py-2 text-left hover:bg-surface-sunken focus-visible:bg-surface-sunken focus-visible:outline-none",
                    selected && "bg-brand-soft",
                    busy && "opacity-70"
                  )}
                  onClick={() => selectConnection(option)}
                >
                  <span className="grid size-4 shrink-0 place-items-center pt-0.5 text-brand-strong">
                    {selected ? (
                      <Check className="size-3.5" strokeWidth={2.25} aria-hidden="true" />
                    ) : null}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-semibold text-ink">
                      {providerLabel(option.provider)}
                      {pending ? "…" : ""}
                    </span>
                    <span className="mt-0.5 block overflow-hidden text-ellipsis whitespace-nowrap text-[12px] text-ink-muted">
                      {connectionSummary(option) || "Connected account"}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
          <div className="my-2 border-t border-line" />
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-[var(--radius-md)] border-0 bg-transparent px-2.5 py-2 text-left text-[13px] font-medium text-ink hover:bg-surface-sunken focus-visible:bg-surface-sunken focus-visible:outline-none"
            onClick={handleConnectAnother}
          >
            <Plus className="size-3.5 shrink-0 text-ink-muted" aria-hidden="true" />
            Connect another CRM
          </button>
        </div>
      )}
      <Toast open={Boolean(toast)}>{toast?.message}</Toast>
    </div>
  );
}

export default ConnectionSwitcher;
