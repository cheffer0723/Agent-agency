from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime, timezone
from pathlib import Path
import json

# Feedback is appended here, at the repository root, so the founder has one
# durable place to review everything testers report during the beta.
FEEDBACK_DIR = Path(__file__).resolve().parents[2] / "feedback"
FEEDBACK_LOG = FEEDBACK_DIR / "beta-feedback.jsonl"

VALID_CATEGORIES = {"bug", "question", "feature", "praise", "other"}
VALID_SEVERITIES = {"", "low", "medium", "high", "critical"}


class LogBetaFeedback(BaseTool):
    """
    Record a beta tester's bug report, unanswered question, feature idea, or
    other feedback to a durable append-only log the team can review. Use this
    whenever a tester reports a problem, whenever you cannot confidently answer
    a product-specific question, or when a tester shares a suggestion.
    """

    category: str = Field(
        ...,
        description="One of: bug, question, feature, praise, other.",
    )
    summary: str = Field(
        ..., description="A short one-line summary of the feedback."
    )
    details: str = Field(
        default="",
        description="Fuller details: what happened, steps to reproduce, or the tester's exact question.",
    )
    severity: str = Field(
        default="",
        description="For bugs only: low, medium, high, or critical. Leave empty otherwise.",
    )
    tester_contact: str = Field(
        default="",
        description="Optional tester-provided contact (email/handle) if they want a follow-up.",
    )

    def run(self) -> str:
        # Step 1: Normalize and validate the category/severity without failing hard.
        category = self.category.strip().lower()
        if category not in VALID_CATEGORIES:
            category = "other"
        severity = self.severity.strip().lower()
        if severity not in VALID_SEVERITIES:
            severity = ""

        # Step 2: Build a structured record.
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "severity": severity,
            "summary": self.summary.strip(),
            "details": self.details.strip(),
            "tester_contact": self.tester_contact.strip(),
        }

        # Step 3: Append to the JSONL log (one record per line).
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        label = f"{category}" + (f"/{severity}" if severity else "")
        return f"Logged {label} feedback to {FEEDBACK_LOG}: {record['summary']}"


if __name__ == "__main__":
    tool = LogBetaFeedback(
        category="bug",
        summary="Payload failed to deliver after ~30s",
        details="Sent an encrypted payload; recipient never received it. No error shown.",
        severity="high",
        tester_contact="tester@example.com",
    )
    print(tool.run())
