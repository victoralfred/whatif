"""`whatifd.statistical` — Phase E statistical layer.

Houses the real bootstrap implementation and (in later sub-phases)
Holm correction + observed-MDE power warnings. v0.1 / v0.2 baseline
ships an empirical-percentile shortcut in `whatifd.pipeline`; this
module's `paired_percentile_bootstrap` is the doctrinally-correct
replacement.

Phase E.1 (this module's first delivery): bootstrap algorithm +
property tests. The pipeline-side disclosure flip and the
walkthrough-fixture regeneration are deferred to Phase E.2 — that
PR's focus IS the regeneration churn, kept separate so the
algorithm review and the documentation churn are independently
reviewable.

## Wire-boundary pattern (read this before calling)

`BootstrapResult` carries plain Python `float` values for `median`,
`ci_lower`, and `ci_upper`. The wire-canonical view of those
quantities is `DecimalString` (cardinal #4 determinism — only the
wire shape is byte-stable across platforms; in-memory floats are
not). Callers wiring this into `whatifd.types.cohort.CohortResult`
or `whatifd.report.models_v01.ReportV01` MUST format the float to
`DecimalString` at the boundary, e.g.:

```python
from whatifd.statistical import paired_percentile_bootstrap, to_decimal_string

result = paired_percentile_bootstrap(deltas, seed=42)
median = to_decimal_string(result.median)
ci_lower = to_decimal_string(result.ci_lower)
ci_upper = to_decimal_string(result.ci_upper)
```

`to_decimal_string` defaults to 3-decimal precision (the convergent
display precision for v0.1/v0.2 cohort medians); callers needing
different precision pass it explicitly. Phase E.2 wires this into
`_cohort_result_from_bucket` directly.
"""

from whatifd.statistical.bootstrap import (
    BootstrapResult,
    paired_percentile_bootstrap,
)
from whatifd.statistical.wire_boundary import to_decimal_string

__all__ = [
    "BootstrapResult",
    "paired_percentile_bootstrap",
    "to_decimal_string",
]
