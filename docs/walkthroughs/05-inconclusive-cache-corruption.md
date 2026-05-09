# whatifd verdict: Inconclusive

**Reason:** could not acquire scorer cache lock at `.whatifd/cache/scorer/.lock`.
A previous run may have terminated abnormally, leaving the lock file orphaned.

[Suggested next steps ↓](#fix) · [Manifest →](manifest.json)

---

## Suggested next steps

The cache lock file shows:
- PID: 12345 (recorded)
- Hostname: ci-runner-7
- Started: 2026-04-30T14:22:00Z (4 days ago)

To recover:

1. **If you know the previous run is no longer running:**
   `whatifd cache rebuild --force`
   This will rebuild the cache from scratch (slower next run, but safe).

2. **If you want to clear just the lock without rebuilding:**
   `whatifd cache unlock`
   Use only if you're certain no other whatifd process is using this cache.

3. **If you suspect file corruption:**
   `whatifd cache verify`
   Reads all entries, reports any with checksum mismatches, optionally repairs.

This run produced no verdict. Rerun after recovery.

## Methodology

- **Unit of analysis:** paired trace delta (would have been; never executed)
- **Primary metric:** faithfulness · **Cohorts:** failure, baseline (selected; not scored)
- **Primary endpoints:** failure improvement, baseline non-regression (NOT evaluated)
- **Bootstrap:** *unavailable* — `unavailable_reason: "cache locked, scoring stage did not run"`
- **Cluster handling:** *unavailable* — same reason
- **Multiplicity:** N/A (no endpoints evaluated)
- **Judge:** claude-haiku-4-5 (configured; not invoked)
- **Scorer cache:** lock acquisition failed; see "Suggested next steps" above
- **Reliability/validity/calibration/bias:** not measured
- **Causal scope:** N/A (no claim made)
- **Why Inconclusive:** run-scope failure prevented scoring. The verdict cannot exist without scored evidence above the floor.
