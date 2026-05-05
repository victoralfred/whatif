"""Floor evaluator and `FloorPassedProof` witness token (cardinal rule #2).

The trust floor is structural — it cannot be bypassed by configuration.
This module implements the type-level enforcement: `Ship` requires a
`FloorPassedProof`, and the only function that can produce one is
`evaluate_floor()`. Any code path that constructs a Ship is forced to
go through floor evaluation.

## The closure-capture pattern (CASCADE-010, v0.1 resolution)

The original deliberation considered three approaches to enforcing
"only `evaluate_floor` can produce valid proofs":

1. **Underscore-token convention** — `_FLOOR_INTERNAL_TOKEN = object()`
   at module level; constructor compares against it. Bypassable by
   `from whatif.decision.floor import _FLOOR_INTERNAL_TOKEN` (single-
   underscore is private by convention only). Rejected: convention,
   not structural.

2. **Closure-capture** (this implementation) — the token lives in the
   closure of `_build_floor_machinery()`. After that function returns,
   the local `_floor_token` is unreachable through any module-level
   name. The class `FloorPassedProof` and the function `evaluate_floor`
   both close over the token; they're returned to module scope, but
   the token itself is not. Adversarial code that imports this module
   thoroughly cannot find a name that resolves to the token.

3. **Verify-on-construction** — `Ship.__post_init__` re-runs floor logic
   to verify the proof matches its cohort results. Closes cross-run
   proof reuse but adds runtime cost. Deferred to v1.0; CASCADE-205.

This module ships option 2. CASCADE-010 is resolved-for-v0.1 by this
file. The v1.0 hardening (cohort-hash binding) is a separate cascade.

## Known v0.1 limit

Closure-capture is bypassable by Python introspection:
`FloorPassedProof.__init__.__closure__[N].cell_contents` extracts the
captured token. Any contributor running that as production code is
visibly doing something adversarial — code review catches it. The
property test "no DecisionPolicy configuration produces Ship when
evaluate_floor returns FloorFailureSet" (Phase 2 gate) covers
configuration-coverage gaps. Together: structural enforcement against
accidental bypass; visible enforcement against deliberate bypass;
property test against policy-coverage gaps.

## Layering and mypy reconciliation

`FloorPassedProof` lives here, not in `whatif/types/verdict.py`,
because closure-capture requires the class and its producer to be in
the same module. `Ship` (in `types/verdict.py`) imports `FloorPassedProof`
under `TYPE_CHECKING` so the runtime types/ layer carries no
dependency on decision/.

mypy can't analyze classes built inside closures as named types. To
satisfy strict typing, this module declares `FloorPassedProof` and
`FloorFailureSet` as `TYPE_CHECKING`-only stubs at module top — mypy
sees those stubs as the public type. At runtime, the same names are
rebound to the closure-built classes (with `# type: ignore[no-redef]`
on the rebind). Static analysis and runtime see consistent surface;
the closure-capture protection is preserved at runtime.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from whatif.types.cohort import FloorFailure


if TYPE_CHECKING:
    # Type stubs for static analysis. The runtime classes are built inside
    # `_build_floor_machinery()` with closure-captured validation; these
    # stubs declare the public surface so mypy can resolve `FloorPassedProof`
    # as a type in `Ship.proof`.

    class FloorPassedProof:
        """Witness token; runtime impl is closure-captured below."""

        floor_version: str
        evaluated_at: str

        def __init__(
            self,
            *,
            _token: object,
            floor_version: str,
            evaluated_at: str,
        ) -> None: ...

        def __repr__(self) -> str: ...
        def __eq__(self, other: object) -> bool: ...
        def __hash__(self) -> int: ...

    @dataclass(frozen=True, slots=True)
    class FloorFailureSet:
        """Failure-branch return; runtime impl is closure-captured below."""

        failures: list[FloorFailure] = field(default_factory=list)

        def __iter__(self) -> Iterator[FloorFailure]: ...
        def __len__(self) -> int: ...
        def __bool__(self) -> bool: ...


def _build_floor_machinery() -> tuple[type, type, Callable[[], object]]:
    """Module-init factory.

    Binds `_floor_token` in this function's closure. Returns the runtime
    `FloorPassedProof` class, `FloorFailureSet` class, and `evaluate_floor`
    function. The token is unreachable from any module-level name — only
    the closures of `FloorPassedProof.__init__` and `evaluate_floor` see it.
    """
    _floor_token = object()

    class FloorPassedProof:
        __slots__ = ("evaluated_at", "floor_version")

        floor_version: str
        evaluated_at: str

        def __init__(
            self,
            *,
            _token: object,
            floor_version: str,
            evaluated_at: str,
        ) -> None:
            if _token is not _floor_token:
                raise TypeError(
                    "FloorPassedProof cannot be constructed externally. "
                    "Obtain a proof via evaluate_floor()."
                )
            object.__setattr__(self, "floor_version", floor_version)
            object.__setattr__(self, "evaluated_at", evaluated_at)

        def __setattr__(self, name: str, value: object) -> None:
            raise AttributeError(f"FloorPassedProof is immutable; cannot set {name!r}")

        def __repr__(self) -> str:
            return (
                f"FloorPassedProof(floor_version={self.floor_version!r}, "
                f"evaluated_at={self.evaluated_at!r})"
            )

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, FloorPassedProof):
                return NotImplemented
            return (
                self.floor_version == other.floor_version
                and self.evaluated_at == other.evaluated_at
            )

        def __hash__(self) -> int:
            return hash((self.floor_version, self.evaluated_at))

    @dataclass(frozen=True, slots=True)
    class FloorFailureSet:
        failures: list[FloorFailure] = field(default_factory=list)

        def __iter__(self) -> Iterator[FloorFailure]:
            return iter(self.failures)

        def __len__(self) -> int:
            return len(self.failures)

        def __bool__(self) -> bool:
            return bool(self.failures)

    def evaluate_floor() -> FloorPassedProof | FloorFailureSet:
        """Phase 1.4 stub.

        Phase 2.1 replaces this signature with
        `evaluate_floor(result: ExperimentResult, floor: TrustFloor)`
        and implements real per-cohort rule evaluation. For Phase 1.4
        testing, this stub always returns a `FloorPassedProof`. Tests
        that need to exercise the failure branch can construct a
        `FloorFailureSet` directly (it has no closure-bound construction
        guard).
        """
        return FloorPassedProof(
            _token=_floor_token,
            floor_version="v1",
            # Loud marker so a manifest carrying this string in production
            # is obviously bug evidence, not a real evaluation timestamp.
            # Phase 2.1 replaces this with an ISO 8601 timestamp from the
            # injected clock.
            evaluated_at="<<PHASE_1_4_STUB_REPLACE_IN_PHASE_2_1>>",
        )

    return FloorPassedProof, FloorFailureSet, evaluate_floor


# Bind the closure-captured machinery to module-level names. The token
# itself is NOT bound at module level — it lives only in the closure of
# FloorPassedProof.__init__ and evaluate_floor.
#
# mypy already saw the TYPE_CHECKING stubs at the top of this file; the
# runtime rebind is the actual class. We accept the [misc, assignment]
# ignore as the cost of structural enforcement — closure-capture is
# stronger than module-level convention; the cost is mypy ergonomics.
FloorPassedProof, FloorFailureSet, evaluate_floor = _build_floor_machinery()  # type: ignore[misc, assignment]
