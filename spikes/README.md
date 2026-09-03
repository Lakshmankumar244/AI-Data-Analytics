# Non-production technical verification spikes

These spikes implement no product behavior. They use synthetic data and temporary
storage to test mechanisms classified **IMPLEMENT AFTER TECHNICAL VERIFICATION** in
`docs/implementation-authorization-matrix.md`.

Run:

```powershell
python spikes/run_synthetic_verifications.py
```

The local runner verifies deterministic D5 chunk coverage, D13-style checkpoint
idempotency, D7 payload leakage checks, explicit-read OAuth scope enforcement,
timezone/DST conversion, and deterministic D2 arithmetic. Its SQLite schema is
temporary synthetic test infrastructure—not a proposed Catalyst schema.

The runner does not contact Zoho or Catalyst. D14-EVIDENCE, CRM administrator proof,
OAuth granted-scope introspection, real Bulk Read/COQL behavior, Catalyst transaction
semantics, module close/audit fields, and ephemeral-runtime guarantees require a
configured sandbox and remain unverified.

