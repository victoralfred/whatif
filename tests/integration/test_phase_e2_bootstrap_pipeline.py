"""Phase E.2 integration tests.

Pins the load-bearing invariants of the pipeline switch:

1. `_cohort_result_from_bucket` returns CI bounds equal to what
   `paired_percentile_bootstrap(deltas, resamples=BOOTSTRAP_RESAMPLES,
   ci_level=BOOTSTRAP_CI_LEVEL, seed=BOOTSTRAP_SEED)` produces
   directly — i.e., the pipeline really uses the bootstrap with
   the disclosed parameters, not a shadow shortcut and not the
   bootstrap-with-some-other-parameters.

2. The seed/resamples/ci_level declared in `cli.py`'s
   MethodologyDisclosure all live in `whatifd.statistical` and are
   imported at module level by both the pipeline and the CLI.
   Cardinal #10: the disclosure must echo what the pipeline
   actually ran; structural coupling prevents silent drift.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from whatifd.pipeline import _cohort_result_from_bucket, _CohortBuckets
from whatifd.statistical import (
    BOOTSTRAP_CI_LEVEL,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    paired_percentile_bootstrap,
    to_decimal_string,
)
from whatifd.types.policy import DecisionPolicy, TrustFloor


class TestPipelineCallsBootstrap:
    """The pipeline's per-cohort CI fields are the bootstrap's
    output, not the empirical-quantile shortcut."""

    def test_cohort_result_ci_matches_direct_bootstrap_call(self) -> None:
        # A delta sequence large enough to clear the floor's
        # min_scored_per_required_cohort threshold and produce a
        # non-degenerate bootstrap distribution.
        deltas = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]
        bucket = _CohortBuckets(name="failure", selected=10, deltas=tuple(deltas))
        floor = TrustFloor()
        policy = DecisionPolicy()

        # Direct bootstrap call with the SAME parameters the
        # disclosure echoes. The pipeline MUST agree with this
        # output for the disclosure to match the design (cardinal
        # #10). All three parameters are pinned so a future refactor
        # that changes one without updating the disclosure fails
        # this test.
        expected = paired_percentile_bootstrap(
            deltas,
            resamples=BOOTSTRAP_RESAMPLES,
            ci_level=BOOTSTRAP_CI_LEVEL,
            seed=BOOTSTRAP_SEED,
        )

        result = _cohort_result_from_bucket(bucket, policy=policy, floor=floor)

        # The pipeline crossed the wire boundary via to_decimal_string,
        # so the assertions are on the formatted string surface.
        assert result.ci_computable is True
        assert result.ci_unavailable_reason is None
        assert result.median_delta == to_decimal_string(expected.median)
        assert result.ci_lower == to_decimal_string(expected.ci_lower)
        assert result.ci_upper == to_decimal_string(expected.ci_upper)


class TestSampleTooSmallBranch:
    """The bootstrap switch must not silently drop the
    sample-too-small guard. When `scored < floor.min_scored_per_
    required_cohort`, `_cohort_result_from_bucket` MUST emit
    ci_computable=False + ci_unavailable_reason="sample_too_small"
    and skip the bootstrap call entirely (cardinal #1: structural
    failure-as-data, not a degenerate bootstrap call on
    insufficient data).
    """

    def test_below_floor_emits_unavailable_reason(self) -> None:
        # TrustFloor.min_scored_per_required_cohort defaults to 5;
        # 3 deltas is structurally below that floor.
        bucket = _CohortBuckets(name="failure", selected=3, deltas=(0.1, 0.2, 0.3))
        result = _cohort_result_from_bucket(bucket, policy=DecisionPolicy(), floor=TrustFloor())
        assert result.ci_computable is False
        assert result.ci_unavailable_reason == "sample_too_small"
        assert result.median_delta is None
        assert result.ci_lower is None
        assert result.ci_upper is None

    def test_at_floor_emits_bootstrap_ci(self) -> None:
        # At exactly min_scored_per_required_cohort, the bootstrap
        # path activates. Pins the boundary so a future off-by-one
        # in the floor check surfaces.
        floor = TrustFloor()
        n = floor.min_scored_per_required_cohort
        deltas = tuple(0.1 * (i + 1) for i in range(n))
        bucket = _CohortBuckets(name="failure", selected=n, deltas=deltas)
        result = _cohort_result_from_bucket(bucket, policy=DecisionPolicy(), floor=floor)
        assert result.ci_computable is True
        assert result.ci_unavailable_reason is None
        assert result.median_delta is not None


class TestDeterminismOfPipelineOutput:
    """Cardinal #4: per-cohort CI bounds are byte-stable across
    re-runs given the same input. The PR description claims this;
    this test enforces it structurally rather than by convention.
    """

    def test_same_input_produces_byte_identical_cohort_result(self) -> None:
        deltas = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5)
        bucket_a = _CohortBuckets(name="failure", selected=10, deltas=deltas)
        bucket_b = _CohortBuckets(name="failure", selected=10, deltas=deltas)
        a = _cohort_result_from_bucket(bucket_a, policy=DecisionPolicy(), floor=TrustFloor())
        b = _cohort_result_from_bucket(bucket_b, policy=DecisionPolicy(), floor=TrustFloor())
        # Frozen dataclass equality covers every field (median,
        # ci_lower, ci_upper, ci_computable, etc.).
        assert a == b


class TestDisclosureSeedCoupling:
    """Cardinal #10 structural coupling: every bootstrap parameter
    the disclosure declares lives in `whatifd.statistical` and is
    imported at module level by both `whatifd.pipeline` and
    `whatifd.cli`. Single source of truth — future changes update
    both sites at once; a future divergence (e.g., a contributor
    reverting `cli.py` to duplicated literals) fails this test.
    """

    @staticmethod
    def _cli_source() -> str:
        # Locate `whatifd.cli` via `inspect.getsourcefile` so the
        # test is independent of pytest's current working directory.
        # `Path("src/whatifd/cli.py")`-relative pathing would fail
        # under any invocation that didn't `cd` to the repo root.
        import whatifd.cli

        path = inspect.getsourcefile(whatifd.cli)
        assert path is not None, "could not resolve whatifd.cli source path"
        return Path(path).read_text(encoding="utf-8")

    def test_cli_namespace_binds_bootstrap_constants_to_statistical_objects(self) -> None:
        # Runtime check (stronger than a source-text grep): the
        # actual symbols bound in `whatifd.cli`'s namespace under
        # the names `BOOTSTRAP_SEED` / `BOOTSTRAP_RESAMPLES` /
        # `BOOTSTRAP_CI_LEVEL_DECIMAL` ARE the objects from
        # `whatifd.statistical`. A contributor who imports under
        # an alias (`BOOTSTRAP_SEED as BS`) would pass any
        # source-text grep but fail this — the alias binding
        # `cli.BS = whatifd.statistical.BOOTSTRAP_SEED` would not
        # populate `cli.BOOTSTRAP_SEED`.
        import whatifd.cli
        import whatifd.statistical

        assert getattr(whatifd.cli, "BOOTSTRAP_SEED", None) is whatifd.statistical.BOOTSTRAP_SEED
        assert (
            getattr(whatifd.cli, "BOOTSTRAP_RESAMPLES", None)
            is whatifd.statistical.BOOTSTRAP_RESAMPLES
        )
        assert (
            getattr(whatifd.cli, "BOOTSTRAP_CI_LEVEL_DECIMAL", None)
            is whatifd.statistical.BOOTSTRAP_CI_LEVEL_DECIMAL
        )

    def test_cli_imports_bootstrap_constants_from_statistical(self) -> None:
        # Source-text complement to the namespace check above. The
        # two together catch both alias-import bypasses (namespace
        # check) and runtime stub-replacement bypasses (source
        # check). Cardinal #10 belt-and-suspenders.
        cli_source = self._cli_source()
        assert "from whatifd.statistical import" in cli_source and all(
            name in cli_source
            for name in (
                "BOOTSTRAP_CI_LEVEL_DECIMAL",
                "BOOTSTRAP_RESAMPLES",
                "BOOTSTRAP_SEED",
            )
        ), (
            "cli.py must import BOOTSTRAP_SEED, BOOTSTRAP_RESAMPLES, and "
            "BOOTSTRAP_CI_LEVEL_DECIMAL from whatifd.statistical so all three "
            "bootstrap parameters in MethodologyDisclosure are structurally "
            "coupled to the pipeline's actual bootstrap call. Cardinal #10."
        )

    def test_cli_does_not_duplicate_bootstrap_literals(self) -> None:
        cli_source = self._cli_source()
        # The integer literal 4_872_109 should appear exactly once
        # across the codebase (in whatifd.statistical) — not in
        # cli.py as a duplicated mirror.
        assert "4_872_109" not in cli_source, (
            "cli.py contains the literal seed value as a duplicated integer. "
            "Use the BOOTSTRAP_SEED import so the seed is structurally "
            "coupled, not manually mirrored."
        )

    def test_pipeline_constants_are_pinned(self) -> None:
        # Version-pin: if ANY of these constants change, callers
        # reading prior reports need to know the bootstrap output
        # shifted. Changing the literals here requires updating
        # CHANGELOG with a methodology-disclosure note so
        # downstream consumers learn about the rebase.
        assert BOOTSTRAP_SEED == 4_872_109
        assert BOOTSTRAP_RESAMPLES == 2000
        assert BOOTSTRAP_CI_LEVEL == 0.95


class TestDocsExampleStructuralCoupling:
    """The programmatic example in `docs/getting-started.md` shows
    a `MethodologyDisclosure` construction. Cardinal #10: the docs
    must echo the same constants the pipeline uses, not duplicate
    literals. A future seed/resamples change would otherwise leave
    the docs telling readers a stale story.
    """

    @staticmethod
    def _docs_source() -> str:
        # Locate the file relative to the test module's location so
        # the test is independent of pytest's cwd.
        repo_root = Path(__file__).resolve().parents[2]
        docs_path = repo_root / "docs" / "getting-started.md"
        return docs_path.read_text(encoding="utf-8")

    def test_docs_example_imports_bootstrap_constants(self) -> None:
        docs_source = self._docs_source()
        assert "from whatifd.statistical import" in docs_source and all(
            name in docs_source
            for name in (
                "BOOTSTRAP_CI_LEVEL_DECIMAL",
                "BOOTSTRAP_RESAMPLES",
                "BOOTSTRAP_SEED",
            )
        ), (
            "docs/getting-started.md programmatic example must import the "
            "bootstrap constants from whatifd.statistical so the example "
            "echoes the same values the pipeline uses. Cardinal #10."
        )

    def test_docs_example_does_not_duplicate_bootstrap_literals(self) -> None:
        docs_source = self._docs_source()
        # The integer literals 4_872_109 and 2000 (used as
        # standalone values, not in unrelated contexts) should be
        # absent from the example. Check 4_872_109 only — `2000` is
        # too generic to forbid wholesale, so we rely on the
        # imports-present test plus the import-of-the-name to keep
        # `resamples=BOOTSTRAP_RESAMPLES` honest.
        assert "4_872_109" not in docs_source, (
            "docs/getting-started.md contains the literal seed value as a "
            "duplicated integer. Use `seed=BOOTSTRAP_SEED` instead — Cardinal "
            "#10's structural coupling requires the docs to echo the same "
            "constant the pipeline imports."
        )


class TestNoBootstrapLiteralLeakage:
    """The no-duplicated-literals rule applies to ALL files in the
    repo, not just `cli.py` and `docs/getting-started.md`. Scan
    every text file under `src/`, `tests/`, and `docs/` for the
    seed literal `4_872_109`; the only legal occurrence is in
    `whatifd.statistical.__init__` (the source-of-truth). Catches
    session-log prose, cascade-catalog entries, etc., where a
    duplicated literal would silently drift if the constant ever
    changes.
    """

    def test_seed_literal_appears_only_in_statistical_module(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        statistical_init = (repo_root / "src" / "whatifd" / "statistical" / "__init__.py").resolve()
        # Files where the literal is legal:
        # (a) the source-of-truth definition;
        # (b) THIS TEST FILE — the version-pin
        #     `assert BOOTSTRAP_SEED == 4_872_109` and the
        #     `"4_872_109" not in <source>` assertions are
        #     load-bearing: deleting them would defeat the
        #     no-duplicated-literals discipline they enforce.
        legal = {statistical_init, Path(__file__).resolve()}
        # Search every text-ish file under src/, tests/, docs/. Skip
        # binary and cache directories.
        offenders: list[str] = []
        for root_name in ("src", "tests", "docs"):
            for path in (repo_root / root_name).rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix not in (".py", ".md", ".rst", ".txt", ".yaml", ".yml", ".toml"):
                    continue
                if "__pycache__" in path.parts:
                    continue
                if path.resolve() in legal:
                    continue
                # Read defensively — some test fixtures may carry
                # non-utf8 bytes; treat decode errors as "no leak."
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if "4_872_109" in text:
                    offenders.append(str(path.relative_to(repo_root)))
        assert not offenders, (
            "Seed literal 4_872_109 found outside whatifd/statistical/__init__.py:\n  "
            + "\n  ".join(offenders)
            + "\nThe constant has exactly one source of truth; mentions in prose "
            "(session logs, cascade catalog, etc.) must reference BOOTSTRAP_SEED "
            "by name, not the bare integer. Cardinal #10's no-duplicated-literals "
            "rule applies repo-wide."
        )
