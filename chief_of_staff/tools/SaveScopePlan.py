from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime, timezone
from pathlib import Path
import re

# Plans are written here, at the repository root, so the founder keeps a durable
# record of every scoping decision.
PLANS_DIR = Path(__file__).resolve().parents[2] / "plans"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "project"


class SaveScopePlan(BaseTool):
    """
    Persist a beta scope plan for a single project to a Markdown file under the
    repository's `plans/` directory. Use this after triaging a project into
    must-have / cut-for-now / out-of-scope buckets so the founder has a durable,
    shareable record of the decision. Returns the file path and the rendered plan.
    """

    project_name: str = Field(
        ..., description="Name of the project this scope plan is for, e.g. 'Asymmetry'."
    )
    beta_definition: str = Field(
        ...,
        description="One sentence describing the smallest beta that is still valuable: 'Beta = ...'.",
    )
    must_have: list[str] = Field(
        ...,
        description="The few beta-blocking items. Keep short (ideally <= 5).",
    )
    cut_for_now: list[str] = Field(
        default_factory=list,
        description="Real but post-beta items, explicitly parked (not deleted).",
    )
    out_of_scope: list[str] = Field(
        default_factory=list,
        description="Items that do not belong in this product at all.",
    )
    next_actions: list[str] = Field(
        ...,
        description="The next concrete actions to take, ordered. Maximum of 3.",
    )
    notes: str = Field(
        default="", description="Optional extra context or risk flags."
    )

    def run(self) -> str:
        # Step 1: Enforce the 'max 3 next actions' discipline at the tool level.
        actions = self.next_actions[:3]

        # Step 2: Render the plan as Markdown.
        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {i}" for i in items) if items else "- (none)"

        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        md = (
            f"# Beta Scope Plan: {self.project_name}\n\n"
            f"_Generated {generated}_\n\n"
            f"**Beta definition:** {self.beta_definition}\n\n"
            f"## Must-have for beta\n{bullets(self.must_have)}\n\n"
            f"## Cut for now (post-beta)\n{bullets(self.cut_for_now)}\n\n"
            f"## Out of scope\n{bullets(self.out_of_scope)}\n\n"
            f"## Next 3 actions\n"
            + ("\n".join(f"{n}. {a}" for n, a in enumerate(actions, 1)) if actions else "(none)")
        )
        if self.notes.strip():
            md += f"\n\n## Notes\n{self.notes.strip()}\n"

        # Step 3: Write to plans/<slug>.md.
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = PLANS_DIR / f"{_slugify(self.project_name)}.md"
        out_path.write_text(md, encoding="utf-8")

        return f"Saved scope plan to {out_path}\n\n{md}"


if __name__ == "__main__":
    tool = SaveScopePlan(
        project_name="Asymmetry",
        beta_definition="Beta = testers can send and receive one encrypted payload end to end.",
        must_have=[
            "Working send/receive of a single encrypted payload",
            "Pre-beta disclosure gate",
            "Basic error message when a packet drops",
        ],
        cut_for_now=["Group threads", "Mobile app", "Custom themes"],
        out_of_scope=["Built-in crypto wallet", "Financial advice features"],
        next_actions=[
            "Confirm single-payload round trip works on the live site",
            "Write a 5-step tester onboarding note",
            "Recruit 5 beta testers",
        ],
        notes="Zero-knowledge core is safety-critical; keep beta scope minimal and do not touch payload crypto casually.",
    )
    print(tool.run())
