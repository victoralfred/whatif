#!/usr/bin/env python3
"""Claude-based PR reviewer for the whatif project.

Reads a GitHub PR's JSON metadata and diff, sends them to Claude for review
against the project's cardinal rules and quality criteria, and emits a
structured verdict.

Exit codes match whatif's verdict semantics:
- 0 = Ship (PR passes all checks)
- 1 = Don't Ship (PR has blocking issues)
- 2 = Inconclusive (setup/network/credentials/parsing failure, or genuinely
                    ambiguous review that needs human judgment)

Outputs:
- stdout: human-readable summary (for CI logs)
- --output-json <path>: optional structured JSON for downstream tooling

Usage:
    python tools/pr_checker.py --pr-json pr.json --diff-file pr.diff

In a GitHub Actions workflow:
    gh pr view "$PR_NUMBER" --json title,body,author,baseRefName,headRefName,files > pr.json
    gh pr diff "$PR_NUMBER" > pr.diff
    python tools/pr_checker.py --pr-json pr.json --diff-file pr.diff \\
        --output-json verdict.json

Requires:
- ANTHROPIC_API_KEY in environment (CLAUDE_API_KEY honored as legacy fallback)
- anthropic >= 0.40 (already in pyproject.toml [project.optional-dependencies.anthropic])
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

try:
    from anthropic import Anthropic, APIConnectionError, APIError, RateLimitError
    from anthropic.types import Message
except ImportError:
    print(
        "ERROR: anthropic package not installed. Install with:\n"
        "  pip install 'whatif[anthropic]'\n"
        "or directly: pip install 'anthropic>=0.40'",
        file=sys.stderr,
    )
    sys.exit(2)


VerdictState = Literal["ship", "dont_ship", "inconclusive"]

# Haiku is fast and cheap; sufficient for first-pass PR review against
# rule-based criteria. Override via --model or ANTHROPIC_MODEL for deeper review.
DEFAULT_MODEL = "claude-haiku-4-5"

# Hard limits to bound context usage and API cost on giant PRs.
# A 150K-char diff is ~37.5K tokens; well under Claude's 200K context window
# even with the system prompt + user prompt overhead.
# Earlier limit of 50K truncated foundational PRs (e.g. PR #13 was 156K chars,
# saw ~32%) and forced inconclusive verdicts due to insufficient context.
# If still exceeded, we tell the model to return state=inconclusive rather
# than guess.
MAX_DIFF_CHARS = 150_000
MAX_BODY_CHARS = 5_000
# 4000 tokens is plenty for a thorough review with multiple blocking issues
# and cardinal-rule citations. Earlier limit of 1500 truncated Sonnet responses
# mid-string and broke JSON parsing.
MAX_OUTPUT_TOKENS = 4_000


@dataclass
class ReviewVerdict:
    """Structured verdict from a PR review pass.

    Mirrors whatif's three-state verdict semantics deliberately so the
    PR-checker output composes with downstream tooling that already knows
    these states.
    """

    state: VerdictState
    summary: str
    blocking_issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    cardinal_rule_citations: list[str] = field(default_factory=list)
    review_method: str = "claude"
    model: str = DEFAULT_MODEL

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "summary": self.summary,
            "blocking_issues": self.blocking_issues,
            "suggestions": self.suggestions,
            "cardinal_rule_citations": self.cardinal_rule_citations,
            "review_method": self.review_method,
            "model": self.model,
        }


SYSTEM_PROMPT = """Ultrathink You are reviewing a pull request for the `whatif` project — an open-source CLI experiment runner for LLM behavior changes that emits PR-ready verdict reports.

The project follows a TRUST-FIRST doctrine. Your review must check the PR against these CARDINAL RULES (any violation makes the verdict Don't Ship):

1. **Failure-as-data** — every expected failure is structured data, not silent crashes or generic catch-alls. No bare `except:`, no swallowed exceptions, no print-and-continue.
2. **Trust floor cannot be bypassed** — floor failures produce Inconclusive regardless of policy. Floor enforcement is type-level via the `FloorPassedProof` witness token, not by convention.
3. **Disclosure necessary but not sufficient** — severe failures must affect the verdict, not just appear in a footnote.
4. **Determinism opt-in per field** — new schema fields default to non-deterministic; deterministic budget is explicit via `x-deterministic: true` annotations.
5. **Sensitive data wrapped, never raw** — user content goes through `Sensitive[T]` at the adapter boundary, unwrapped only via `.unwrap(reason=...)` which audit-logs.
6. **Public schema hand-written** — `ReportV01` is hand-written; internal types refactor freely. No `dict[str, Any]` crossing module boundaries except at adapter ingress.
7. **Two-affirmation for dangerous capabilities** — forensic profile and similar require both a config block AND a CLI flag.
8. **Inconclusive must be actionable** — every blocking finding has a registered fix-suggestion template.
9. **Orchestration not compute** — reject Ray, ProcessPool for replay, NumPy throughout, MKL/SIMD, BF16/INT8, Numba, ONNX, shared-memory IPC. The workload is I/O-bound; CPU is never the bottleneck.
10. **Statistical claims must match the design** — paired trace deltas as the unit of analysis, predeclared cohort-level endpoints, descriptive (not inferential) per-trace evidence, methodology disclosure required in every report. Scorer caching addresses reproducibility — NOT reliability, validity, calibration, or absence of bias.

Beyond cardinal rules, also check:
- Tests added or updated for behavioral changes (new code without tests is a blocking issue unless explicitly justified)
- No secrets, credentials, API keys, or sensitive data in the diff
- Cascade catalog updated if the PR has architectural follow-on consequences (look for `references/cascade-catalog.md` changes)
- `CHANGELOG.md` updated for user-facing changes
- Imports follow project discipline: Pydantic at boundaries, `@dataclass(frozen=True, slots=True)` for internal types
- `json.dumps` not used outside `whatif/serialization/` (banned-import lint)

Respond ONLY with valid JSON in this exact shape (no markdown fences, no prose around it):

{
  "state": "ship" | "dont_ship" | "inconclusive",
  "summary": "<one paragraph plain-English assessment>",
  "blocking_issues": ["<issue 1>", "<issue 2>"],
  "suggestions": ["<non-blocking suggestion>"],
  "cardinal_rule_citations": ["#N: <how this PR relates to cardinal rule #N>"]
}

State semantics:
- **ship** — no blocking issues; PR aligns with doctrine; tests appropriate to the change.
- **dont_ship** — at least one cardinal rule violation, OR missing tests for behavioral change, OR sensitive data leaked, OR the change weakens a structural guarantee.
- **inconclusive** — diff too large to evaluate fairly, refactor with unclear scope, ambiguous case where you cannot recommend ship without human judgment.

Be specific but TERSE. Each `blocking_issues` entry, `suggestions` entry, and `cardinal_rule_citations` entry should be one sentence — no multi-paragraph explanations, no essays, no quoted code blocks. Cite line ranges or file paths inline. The reviewer reading this report has 3 minutes; respect their time. Cap `blocking_issues` and `suggestions` at 5 items each. Do NOT default to ship; when in doubt, prefer inconclusive."""


def build_user_prompt(title: str, body: str, diff: str, files: list[str]) -> str:
    """Build the user message with PR context, applying truncation limits."""
    truncated_body = body[:MAX_BODY_CHARS]
    body_was_truncated = len(body) > MAX_BODY_CHARS
    if body_was_truncated:
        truncated_body += "\n\n[... PR body truncated ...]"

    truncated_diff = diff[:MAX_DIFF_CHARS]
    diff_was_truncated = len(diff) > MAX_DIFF_CHARS

    parts = [
        f"# PR Title\n{title}",
        f"\n# PR Body\n{truncated_body or '(empty)'}",
        f"\n# Changed files ({len(files)})",
        "\n".join(f"- {f}" for f in files[:50]),
    ]
    if len(files) > 50:
        parts.append(f"\n[... {len(files) - 50} more files not listed ...]")

    parts.append(f"\n# Diff\n```diff\n{truncated_diff}\n```")
    if diff_was_truncated:
        parts.append(
            f"\n[The diff was truncated at {MAX_DIFF_CHARS} chars; "
            f"original was {len(diff)} chars. "
            f"If you cannot fairly assess the PR from this much context, "
            f"return state=inconclusive citing diff_too_large.]"
        )

    return "\n".join(parts)


def parse_response(text: str, model: str) -> ReviewVerdict:
    """Parse Claude's JSON response into a ReviewVerdict.

    Strips markdown fences if present (Claude sometimes adds them despite
    the instruction). Raises if the response is not valid JSON in the
    expected shape; the caller maps that to inconclusive.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```") and lines[-1].startswith("```"):
            cleaned = "\n".join(lines[1:-1])

    data = json.loads(cleaned)

    state = data.get("state")
    if state not in ("ship", "dont_ship", "inconclusive"):
        raise ValueError(f"Invalid state in response: {state!r}")

    return ReviewVerdict(
        state=state,
        summary=str(data.get("summary", "")),
        blocking_issues=list(data.get("blocking_issues", [])),
        suggestions=list(data.get("suggestions", [])),
        cardinal_rule_citations=list(data.get("cardinal_rule_citations", [])),
        review_method="claude",
        model=model,
    )


def review_with_claude(
    title: str,
    body: str,
    diff: str,
    files: list[str],
    api_key: str,
    model: str,
) -> ReviewVerdict:
    """Run the actual Claude review.

    Returns a ReviewVerdict on success. Raises APIError /
    APIConnectionError / RateLimitError on transport-level failures
    and json.JSONDecodeError / ValueError on parse failures; the
    caller maps these to inconclusive verdicts.
    """
    client = Anthropic(api_key=api_key)
    user_prompt = build_user_prompt(title, body, diff, files)

    message: Message = client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text += block.text

    if not response_text:
        raise ValueError("Claude returned an empty response")

    return parse_response(response_text, model)


def render_summary(verdict: ReviewVerdict) -> str:
    """Render verdict as human-readable text for CI logs."""
    glyph = {"ship": "✅", "dont_ship": "❌", "inconclusive": "⚠️"}[verdict.state]
    label = {
        "ship": "Ship",
        "dont_ship": "Don't Ship",
        "inconclusive": "Inconclusive",
    }[verdict.state]

    lines = [
        f"{glyph} whatif PR review: {label}",
        f"Method: {verdict.review_method} · Model: {verdict.model}",
        "",
        f"Summary: {verdict.summary}",
    ]

    if verdict.blocking_issues:
        lines.append("\nBlocking issues:")
        for issue in verdict.blocking_issues:
            lines.append(f"  - {issue}")

    if verdict.cardinal_rule_citations:
        lines.append("\nCardinal rule citations:")
        for cite in verdict.cardinal_rule_citations:
            lines.append(f"  - {cite}")

    if verdict.suggestions:
        lines.append("\nSuggestions (non-blocking):")
        for sugg in verdict.suggestions:
            lines.append(f"  - {sugg}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Claude-based PR reviewer for whatif",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pr-json",
        required=True,
        type=Path,
        help="Path to PR metadata JSON (output of `gh pr view --json title,body,files,...`)",
    )
    parser.add_argument(
        "--diff-file",
        required=True,
        type=Path,
        help="Path to PR diff (output of `gh pr diff <PR>`)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional: write structured verdict JSON to this path",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
        help=f"Anthropic model ID (default: {DEFAULT_MODEL}; override via --model or ANTHROPIC_MODEL env)",
    )
    args = parser.parse_args()

    # Read PR metadata.
    try:
        pr = json.loads(args.pr_json.read_text())
    except FileNotFoundError:
        print(f"ERROR: --pr-json file not found: {args.pr_json}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"ERROR: --pr-json is not valid JSON: {e}", file=sys.stderr)
        return 2

    title: str = pr.get("title", "") or ""
    body: str = pr.get("body") or ""
    files_raw = pr.get("files", []) or []
    files = [f.get("path", str(f)) if isinstance(f, dict) else str(f) for f in files_raw]

    # Read diff.
    try:
        diff = args.diff_file.read_text()
    except FileNotFoundError:
        print(f"ERROR: --diff-file not found: {args.diff_file}", file=sys.stderr)
        return 2

    # Local rule checks before burning an API call.
    if "WIP" in title.upper() or "[WIP]" in body.upper():
        verdict = ReviewVerdict(
            state="dont_ship",
            summary="PR marked WIP; skipping automated review until ready.",
            blocking_issues=["PR is marked WIP; remove the WIP marker when ready for review."],
            review_method="local-rule",
            model=args.model,
        )
    elif not diff.strip():
        verdict = ReviewVerdict(
            state="inconclusive",
            summary="PR diff is empty.",
            blocking_issues=["No diff to review. Verify the PR has actual changes."],
            review_method="local-rule",
            model=args.model,
        )
    else:
        # Standard env name is ANTHROPIC_API_KEY; CLAUDE_API_KEY honored as legacy fallback.
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        if not api_key:
            verdict = ReviewVerdict(
                state="inconclusive",
                summary="ANTHROPIC_API_KEY not set; cannot run automated review.",
                blocking_issues=[
                    "Set ANTHROPIC_API_KEY in the environment to enable Claude-based PR review.",
                    "In GitHub Actions, add the key as a repo secret and reference it via "
                    "`env: ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` on the job.",
                ],
                review_method="local-rule",
                model=args.model,
            )
        else:
            try:
                verdict = review_with_claude(title, body, diff, files, api_key, args.model)
            except (APIError, APIConnectionError, RateLimitError) as e:
                verdict = ReviewVerdict(
                    state="inconclusive",
                    summary=f"Claude API error: {type(e).__name__}: {e}",
                    blocking_issues=[
                        f"Anthropic API call failed: {type(e).__name__}.",
                        "Retry the workflow run; if the failure persists, check the Anthropic status page.",
                    ],
                    review_method="claude-failed",
                    model=args.model,
                )
            except (json.JSONDecodeError, ValueError) as e:
                verdict = ReviewVerdict(
                    state="inconclusive",
                    summary=f"Could not parse Claude response: {e}",
                    blocking_issues=[
                        "Claude returned a response that could not be parsed as the expected JSON shape.",
                        "Inspect the Action logs for the raw response and consider adjusting the prompt.",
                    ],
                    review_method="claude-parse-failed",
                    model=args.model,
                )

    print(render_summary(verdict))

    if args.output_json:
        args.output_json.write_text(json.dumps(verdict.to_dict(), indent=2, sort_keys=True))

    return {"ship": 0, "dont_ship": 1, "inconclusive": 2}[verdict.state]


if __name__ == "__main__":
    sys.exit(main())
