from agency_swarm.tools import BaseTool
from pydantic import Field
from pathlib import Path
import re

# Knowledge base lives at the repository root in `knowledge/` as Markdown files.
# This is provider-agnostic (plain file reads), so it works with any model —
# unlike Agency Swarm's built-in files_folder, which relies on OpenAI-hosted
# vector stores / file_search and requires a valid OpenAI key.
KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "how", "what", "why", "can",
    "i", "you", "we", "to", "of", "and", "or", "in", "on", "for", "my", "it",
    "with", "about", "this", "that", "be", "will", "if", "so", "as", "at",
}


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS and len(w) > 1}


class SearchKnowledgeBase(BaseTool):
    """
    Search the Asymmetry knowledge base (Markdown files under `knowledge/`) for
    sections relevant to a tester's question. Returns the best-matching sections
    with their source file and heading, or a clear "no matching entries" message
    when the knowledge base does not cover the question. Always search here before
    answering a product-specific question; if nothing relevant is found, do not
    invent an answer.
    """

    query: str = Field(..., description="The tester's question or the topic to look up.")
    max_sections: int = Field(
        default=3, description="Maximum number of matching sections to return."
    )

    def run(self) -> str:
        if not KNOWLEDGE_DIR.exists():
            return "No matching entries: the knowledge base is empty."

        query_terms = _tokenize(self.query)
        if not query_terms:
            return "No matching entries: the query had no searchable terms."

        # Step 1: Split every Markdown file into (heading, body) sections.
        scored: list[tuple[int, str, str, str]] = []  # (score, file, heading, body)
        for md in sorted(KNOWLEDGE_DIR.rglob("*.md")):
            text = md.read_text(encoding="utf-8", errors="ignore")
            # Split on headings (##, ###, #) keeping the heading with its body.
            parts = re.split(r"(?m)^(#{1,6}\s+.*)$", text)
            # re.split with a capturing group yields: [pre, head1, body1, head2, body2, ...]
            i = 1
            while i < len(parts):
                heading = parts[i].lstrip("#").strip()
                body = parts[i + 1].strip() if i + 1 < len(parts) else ""
                i += 2
                if not body and not heading:
                    continue
                # Ignore blockquote/meta lines (starting with '>') so founder-facing
                # notes in the docs don't produce misleading matches.
                body_for_scoring = "\n".join(
                    line for line in body.splitlines() if not line.lstrip().startswith(">")
                )
                section_terms = _tokenize(heading + " " + body_for_scoring)
                score = len(query_terms & section_terms)
                if score > 0:
                    scored.append((score, md.name, heading, body))

        if not scored:
            return (
                "No matching entries found in the knowledge base for this question. "
                "Do not invent an answer; log it with LogBetaFeedback (category 'question')."
            )

        # Step 2: Return the top sections, best score first.
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, fname, heading, body in scored[: self.max_sections]:
            out.append(f"### {heading}  (source: {fname}, relevance: {score})\n{body}")
        return "\n\n---\n\n".join(out)


if __name__ == "__main__":
    for q in ["Can the company read my data?", "How do I add a contact?"]:
        print(f"\n===== QUERY: {q} =====")
        print(SearchKnowledgeBase(query=q).run())
