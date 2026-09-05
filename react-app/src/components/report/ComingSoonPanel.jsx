export default function ComingSoonPanel({ tabLabel }) {
  return (
    <div className="mx-auto max-w-[480px] py-16">
      <p className="eyebrow">Coming soon</p>
      <h2 className="mt-1 font-heading text-xl font-semibold tracking-tight text-ink">
        {tabLabel} isn't built yet
      </h2>
      <p className="mt-2 text-sm leading-normal text-ink-soft">
        This view is scoped for a later build phase. The Overview tab covers what's
        available right now.
      </p>
    </div>
  );
}
