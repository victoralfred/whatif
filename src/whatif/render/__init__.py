"""`whatif.render` — Markdown / CI-status rendering layer.

Phase 7 of the v0.1 implementation plan. Three output formats are
produced from the same `ReportV01`:

  - **CI status** (`render_ci_status`) — ≤80 chars; the one-line
    PR-check summary. Phase 7.3, this delivery.
  - **Summary section** (Phase 7.2) — ≤30 lines; the compact
    Markdown block surfaced in PR comments / Slack.
  - **Full report** (Phase 7.1) — the five-section Markdown
    document with anchored jump links and methodology disclosure.

Each format is a pure function `(ReportV01) -> str`; rendering does
not raise for typed `ReportV01` inputs. Walkthrough-match tests
(Phase 7 gate) verify the rendered output against the committed
`docs/walkthroughs/*.md` fixtures.
"""

from whatif.render.ci_status import render_ci_status
from whatif.render.summary import render_summary

__all__ = ["render_ci_status", "render_summary"]
