# Design: Issue #108 — typed `ToolSpan`, cardinal-#5 boundary, and `ToolCache` wiring

**Status:** draft for review
**Issue:** [#108](https://github.com/victoralfred/whatifd/issues/108) — "Phase-J follow-up: extend cardinal-#5 boundary enforcement to `RawTrace.tool_spans`"
**Cascade entries:** "`RawTrace.tool_spans` — same cardinal-#5 risk as `metadata`, deferred coordinated change" (open, tracking #108); "Phoenix `tool_spans` projection (partial; content-stripped) — F-2.2 fix" (resolved, upgrade-on-#108)
**Target:** v0.3 (coordinated runner-contract bump)

---

## 1. Summary

Introduce a typed `whatifd.contract.ToolSpan`, adopt it in `RawTrace.tool_spans`,
`ReplayOutput.tool_spans`, and `TraceOutput.tool_spans`, and apply per-field
cardinal-#5 enforcement (tool input/output wrapped as `Sensitive[str]`;
structural attributes validated via the existing `PII_ATTRIBUTE_KEYS` pattern).

This closes #108's literal scope — but the work is worth doing now because a
**second, larger payoff is coupled to the same type change**, validated by the
2026-05-30 live Langfuse integration test: typed, content-bearing tool spans
are what let whatifd thread the **original tool results** to both the runner
(via a populated `ToolCache`) and the scorer (via `ScoreCase.original_output.
tool_spans`). Today both are blocked because `tool_spans` is a loose
`list[dict[str, Any]]` whose content is *stripped* at the adapter boundary as a
cardinal-#5 stopgap.

So #108 is the linchpin between "whatifd reads traces" and "a config-driven
`whatifd fork` can actually replay and score against what the tools returned."

---

## 2. Two coupled problems

### Problem A — the cardinal-#5 gap (the issue's framing)

`RawTrace.tool_spans` carries tracer-emitted tool I/O, which routinely contains
user content, but it is typed `list[dict[str, Any]]` (`adapters/protocols.py:118`)
and is **not** covered by the `RawTrace.metadata` model_validator that enforces
`Sensitive[str]` at PII keys (`adapters/protocols.py:150-208`). The graph walk
*would* catch a `Sensitive[T]` reachable inside a span dict
(`serialization/graph_walk.py:120`), which is exactly why the Phoenix adapter's
F-2.2 fix **strips** content keys (`input.value`, `output.value`) and PII keys
rather than wrapping them (`packages/whatifd-phoenix/.../source.py:_project_tool_span`).
Stripping is a structural stopgap: it respects cardinal #5 by discarding the
data instead of protecting it.

### Problem B — the empty `ToolCache` / reference-threading gap (the live-test discovery)

`ToolCache` (`contract/__init__.py:88-146`) is a stub: `cache: dict[str, Any]`
defaults empty, and nothing populates it from a trace's tool spans. The CLI
delta closure constructs it empty — `tool_cache = ToolCache()`
(`cli_pipeline.build_delta_fn`) — and builds the original output with no tool
spans — `original_output=TraceOutput(text=original_response)`. Consequences,
both hit during the live fxtrade run:

- **Runners can't replay against original tool outputs.** The `use-original`
  policy is the whole point of cached-tool replay (cardinal #10's causal-claim
  scope: "associated *under cached-tool replay*"), but `tool_cache.lookup(...)`
  always returns `None` because the cache is empty.
- **Scorers can't see the reference.** A faithfulness scorer needs the tool
  results as ground truth. `ScoreCase` carries `original_output: TraceOutput`,
  which *has* a `tool_spans` field — but it's empty (content stripped upstream
  AND not threaded by `build_delta_fn`). The live harness worked around this by
  having the scorer **re-fetch** the tool results from Langfuse by `trace_id`
  (`evaluator/inspect_scorer.py` in the operator harness) — a workaround that
  only exists because the contract drops the data.

### Why they are one change

Both are blocked by the same root cause: `tool_spans` content cannot be carried
safely, so it is stripped. Make it a typed `ToolSpan` with `Sensitive[str]`
content (Problem A) and the content can be carried safely — at which point
wiring it into `ToolCache` and `TraceOutput.tool_spans` (Problem B) becomes a
small, additive follow-on. Shipping A without B leaves the live-test blocker
open; shipping B without A re-opens the cardinal-#5 hole. They go together.

---

## 3. Current state (grounded)

| Surface | Today | Cite |
|---|---|---|
| `RawTrace.tool_spans` | `list[dict[str, Any]]`, no enforcement | `adapters/protocols.py:118` |
| `ReplayOutput.tool_spans` | `list[dict[str, Any]]` (public runner contract) | `contract/__init__.py:164` |
| `TraceOutput.tool_spans` | `list[dict[str, Any]]`, not populated by `build_delta_fn` | `contract/__init__.py:189` |
| `ToolCache` | stub: empty `cache` dict, `lookup()` always `None` | `contract/__init__.py:88-146` |
| `Runner.__call__` | `(TraceInput, ReplayConfig, ToolCache) -> ReplayOutput`; no `trace_id`, no spans | `contract/__init__.py:219-233` |
| cardinal-#5 chain | (a) `Sensitive[T]` type, (b) graph-walk reject, (c) encoder reject, + metadata boundary validator | `types/sensitive.py`; `serialization/graph_walk.py:120`; `serialization/encoder.py:106-119`; `adapters/protocols.py:150-208` |
| Phoenix adapter | populates `tool_spans` **content-stripped** (F-2.2 stopgap) | `whatifd-phoenix/.../source.py:_project_tool_span` |
| Langfuse adapter | does **not** populate (Langfuse models tool calls as `generations`, not nested spans) | `whatifd-langfuse/.../source.py:209` |
| Stub adapter | empty `tool_spans` | `src/whatifd/adapters/stub.py` |

There is **no** `ToolSpanInput`/`ToolSpan` type today, despite #108's wording —
the contract is loose dicts by design, for parity between the adapter side and
the runner side.

---

## 4. Proposed design

### 4.1 The typed `ToolSpan` model (`whatifd.contract.ToolSpan`)

```python
class ToolSpan(BaseModel):
    model_config = ConfigDict(extra="allow")  # forward-compat with tracer attrs

    name: str                              # tool name — structural, not sensitive
    kind: str = "tool"                     # span kind (tool | retrieval | generation | ...)
    tool_call_id: str | None = None        # for deterministic ToolCache keying
    input: Sensitive[str] | None = None    # canonical-JSON of tool args, wrapped
    output: Sensitive[str] | None = None   # canonical-JSON of tool result, wrapped
    attributes: dict[str, Any] = Field(default_factory=dict)  # structural; PII-validated

    # mirrors RawTrace.metadata: reject unwrapped values at PII_ATTRIBUTE_KEYS
    @model_validator(mode="after")
    def _enforce_pii_attribute_wrapping(self) -> "ToolSpan": ...
```

- `input`/`output` are `Sensitive[str]` because tool I/O is user content. They
  are canonicalized to a string via `serialization.canonical.canonical_json_bytes`
  before wrapping (cardinal #4 determinism — same span always projects the same
  string), exactly as `whatifd_langfuse._stringify` already does for trace I/O.
- `attributes` carries structural/tooling state (latency, status, tool version)
  and reuses the `PII_ATTRIBUTE_KEYS` validator so a tracer that smuggles
  `user.id` into a span attribute is caught at construction (Problem A, the part
  the flat-registry already handles).
- `name`/`kind`/`tool_call_id` are structural identifiers, not wrapped.

### 4.2 Per-field cardinal-#5 enforcement (mirrors the #87 three-layer chain)

1. **Type-level (a):** `input`/`output: Sensitive[str]` — mypy strict makes a
   raw `str` at those fields a compile error. The `attributes` validator raises
   `PIIAttributeTypeError` at construction (reuse `format_pii_violation`).
2. **Graph-walk (b):** already descends into `list[dict]` via the Mapping branch
   (`graph_walk.py`), so a typed `ToolSpan` with `Sensitive` fields is walked
   for free — but because the content is now *intended* to be `Sensitive[str]`,
   the report projection must **unwrap-or-omit** tool-span content on the wire
   path (the report does not surface raw tool I/O; see §6).
3. **Encoder (c):** unchanged — the last-line reject still applies.

This flips F-2.2's stopgap: Phoenix `_project_tool_span` upgrades from
**strip-content** to **wrap-content-as-`Sensitive[str]`** (cascade entry's
documented upgrade trigger).

### 4.3 Adopt `ToolSpan` across the contract (coordinated bump)

- `RawTrace.tool_spans: list[ToolSpan]` (`adapters/protocols.py`)
- `ReplayOutput.tool_spans: list[ToolSpan]` (`contract/__init__.py` — **public
  runner contract**, see §6 compat)
- `TraceOutput.tool_spans: list[ToolSpan]`

Pydantic coerces a plain dict matching `ToolSpan` fields, and `extra="allow"`
keeps unknown tracer attributes — softening the break for runners that emit
dicts (§6).

### 4.4 `ToolCache` wiring (Problem B)

- Add `whatifd.replay.build_tool_cache(tool_spans: list[ToolSpan]) -> ToolCache`
  that keys each span's `output` by `(name, input)` via `ToolCache._key`.
- In `cli_pipeline.build_delta_fn` and the programmatic `run_pipeline` path,
  replace `tool_cache = ToolCache()` with `build_tool_cache(rt.tool_spans)` so
  the `use-original` policy actually returns cached outputs.
- `ToolCache.lookup` stays as-is; it finally has entries to return.

### 4.5 Thread the reference to the scorer (Problem B)

- In `build_delta_fn`, build `original_output=TraceOutput(text=original_response,
  tool_spans=rt.tool_spans)` (currently `tool_spans` is dropped). The scorer can
  then read `case.original_output.tool_spans` as the ground-truth reference —
  no re-fetch. The operator harness's `score_fn` re-fetch workaround becomes
  unnecessary.

---

## 5. Adapter migration

| Adapter | Change |
|---|---|
| **Phoenix** | `_project_tool_span` upgrades strip → wrap: canonical-JSON the `input.value`/`output.value`, wrap as `Sensitive[str]`, route PII attrs through the validator. Update the 6 `TestToolSpansProjection` tests. |
| **Langfuse** | Project `generations`/observations into `ToolSpan`s (Langfuse has no nested spans, but the `[TOOL]`/`[GENERATION]` observations carry tool I/O — confirmed in the live data). New projection + tests. |
| **Stub** | Add an optional `tool_spans` field to `StubTraceSpec` so fixtures can exercise the wrap path; default stays empty. |

---

## 6. Cardinal-rule + compatibility analysis

- **#5 (Sensitive wrapped):** the core win — content becomes `Sensitive[str]`
  end to end; stripping is retired. The report path must **unwrap-with-reason or
  omit** tool-span content during projection so the wire artifact never carries
  raw I/O (decision: omit by default; surface only under `forensic` profile,
  mirroring judge-rationale handling).
- **#6 (public schema hand-written):** `ReplayOutput` is the **public runner
  contract**. Changing `tool_spans` from `list[dict]` to `list[ToolSpan]` is a
  deliberate, hand-written contract change → **minor bump (v0.3)**, documented
  in `runner-contract.md` and CHANGELOG. `extra="allow"` + dict coercion means
  most existing runners keep working (a returned dict with `name`/`output`
  coerces); runners that emit free-form span dicts with non-conforming shapes
  get a validation error — called out as a breaking note.
- **Wire schema (`ReportV01`):** unaffected — tool spans are not a top-level
  report field, so **no `v0.2.json` → `v0.3.json` schema change** is forced by
  this work (only the runner contract moves). Confirm during implementation.
- **#4 (determinism):** input/output canonicalization is deterministic
  (`canonical_json_bytes`); no `x-deterministic` annotation needed (internal,
  not wire).
- **#1 (failure-as-data):** a malformed span (missing required field) surfaces
  as a typed `PIIAttributeTypeError`/`ValidationError` at construction, not a
  downstream crash.
- **#10:** populating `ToolCache` makes the "associated under cached-tool
  replay" claim *actually true* — today it is asserted but the cache is empty.

---

## 7. Test plan

- `tests/adapters/conformance.py::TraceSourceConformance::test_emitted_traces_wrap_tool_span_user_content` — every adapter's emitted `RawTrace` has tool-span content wrapped (issue's named test).
- `ToolSpan` unit tests: PII-attribute validator, canonical input/output, `Sensitive` repr-redaction.
- `build_tool_cache` tests: round-trip a span → `lookup(name, args)` returns the wrapped output; miss returns `None`.
- `build_delta_fn` integration: `ToolCache` is populated; `TraceOutput.tool_spans` is threaded into `ScoreCase`.
- Report projection: tool-span content is omitted/unwrapped on the wire (graph walk + encoder stay green; a forensic-profile test surfaces it).
- Phoenix/Langfuse adapter projection tests (strip→wrap; generations→spans).

---

## 8. Phasing

Ship as two PRs sharing the `ToolSpan` type, both v0.3:

- **108a — typed `ToolSpan` + cardinal-#5 enforcement** (closes the issue's
  literal scope): introduce `ToolSpan`, adopt in the three contract surfaces,
  per-field enforcement, Phoenix strip→wrap, conformance test. After 108a,
  content is *carried safely* but not yet *used*.
- **108b — `ToolCache` wiring + reference threading** (the live-test payoff):
  `build_tool_cache`, populate in the delta closures, thread
  `RawTrace.tool_spans → TraceOutput.tool_spans`, Langfuse generation→span
  projection, runner/scorer reference access. After 108b, a config-driven
  `whatifd fork` can replay against original tool outputs and score against the
  reference without a re-fetch workaround.

108b also reduces the pressure on the sibling **"cohort_classifier configurable"**
v0.3 item: with the reference available in-contract, a config-loadable scorer no
longer needs Langfuse credentials to re-fetch.

---

## 9. Open decisions (for the owner)

1. **Report surfacing of tool-span content:** omit on the wire by default and
   surface only under `forensic` profile (recommended, mirrors judge rationale),
   or never surface? Affects the projection + a renderer decision.
2. **Bump size:** does the runner-contract change (`ReplayOutput.tool_spans`
   shape) make v0.3 a clean minor, or do we want a deprecation window where
   `list[dict]` is still accepted and coerced for one release?
3. **Langfuse span source:** project from `observations` of type `[TOOL]`
   (cleanest, matches the live data) vs `[GENERATION]` `tool_results` — confirm
   which the adapter standardizes on.
4. **108a/108b split vs single PR:** the split keeps each PR reviewable; a single
   PR lands the full payoff faster but is large. Recommend the split.

---

## 10. Cascade-catalog updates (to land with the code)

- Update "`RawTrace.tool_spans` — same cardinal-#5 risk…" → resolution path
  amended to reference this doc + the A/B split; status moves to in-progress on
  108a merge, resolved on 108b.
- Update the resolved Phoenix F-2.2 entry: its documented upgrade trigger
  (#108) has fired; note strip→wrap shipped in 108a.
- Cross-reference the "cohort_classifier configurable" entry: 108b removes the
  re-fetch workaround that motivated part of it.
