# UI Reference — `docs/UI/*.webp`

Screenshots of the actual, running Phase 1 frontend (`react-app/`) — Personal Check
mode, built against mock data per `frontend-build-plan.md`. These are ground truth for
what the frontend currently looks like and does, not a mockup or a description of
intent — treat them as authoritative over any prose description of a screen elsewhere
in this repo's docs if the two ever seem to disagree.

**When building or wiring the backend, check these before finalizing any response
shape a screen consumes.** The frontend's data layer (`react-app/src/data/client.js`,
currently backed by `mockClient.js`) already defines the exact contract each screen
expects — these images are the visual result of that contract, useful for confirming a
field actually renders where you'd expect, not just that the JSON shape matches on
paper.

Current coverage: Setup and Running screens (the only two built in Phase 1). Anything
not pictured here (Overview, Modules, Users, Trend, Records, Fix) doesn't exist yet —
don't infer their design from absence.
