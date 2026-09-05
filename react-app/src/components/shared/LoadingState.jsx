export default function LoadingState({ label = "Loading" }) {
  return (
    <div
      className="flex w-full min-h-[max(40vh,calc(100dvh-var(--app-header-height)))] min-w-0 flex-1 flex-col items-center justify-center gap-3 px-5 py-5 text-center"
      role="status"
    >
      <span className="eyebrow">{label}</span>
      <span
        className="size-[22px] animate-spin rounded-full border-2 border-line border-t-brand motion-reduce:animate-none"
        aria-hidden="true"
      />
    </div>
  );
}
