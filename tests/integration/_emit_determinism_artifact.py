"""Emit the canonical deterministic-subset JSON for the cross-platform
CI matrix.

Phase J — Determinism widening: the cross-platform CI job runs this
script on Ubuntu and macOS, uploads the resulting JSON as a per-OS
artifact, and a finalizer job downloads both and asserts byte-equality.

The script picks the canonical clean-Ship walkthrough fixture, runs
the projection, and writes the canonical bytes to
`./determinism-subset.json` in the current working directory. The
fixture is deterministic by construction (fixed seeds, fixed timestamps,
fixed adapter identifiers) so any byte difference between the two
runs surfaces a real cross-platform bug — float formatting drift,
dict-ordering quirk, etc.

Not a pytest test: pytest's discovery would surface this as an
empty-collection error in the cross-platform job. The CI matrix
runs `python` directly. The byte-equality assertion lives in the
workflow's finalizer step (a `diff -q`), not here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    # Late imports (inside main) keep the module-level import block
    # ruff-clean. The sys.path manipulation must happen before
    # importing test fixtures, which lints E402 if done at module
    # top; doing it in main isolates the path-hack to function scope.
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "tests"))

    from integration._fixtures import scenario_clean_ship
    from whatifd.pipeline import run_pipeline
    from whatifd.serialization import canonical_json_bytes, encode_report_v01
    from whatifd.serialization.determinism import extract_deterministic_subset
    from whatifd.types.policy import DecisionPolicy, TrustFloor

    fx = scenario_clean_ship()
    report = run_pipeline(
        fx.trace_source,
        delta_fn=fx.delta_fn,
        floor=TrustFloor(),
        policy=DecisionPolicy(),
        runtime=fx.runtime,
        methodology=fx.methodology,
        cache_summary=fx.cache_summary,
    )
    report_dict = json.loads(encode_report_v01(report))
    subset = extract_deterministic_subset(report_dict)
    out_path = Path("determinism-subset.json")
    out_path.write_bytes(canonical_json_bytes(subset))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
