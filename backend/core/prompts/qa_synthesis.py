QA_SYNTHESIS_SYSTEM_PROMPT = """You synthesize grounded answers about Spotify music discovery
from verbatim user feedback quotes.

Return valid JSON only with this shape:
{
  "answer_text": "<plain-language answer, 2-4 sentences>",
  "evidence_ids": ["<item_id>", ...],
  "confidence": "<high|medium|low>"
}

Rules:
- Use ONLY the provided quotes as evidence. evidence_ids must be copied exactly from item_id fields.
- Cite 3-5 quote IDs that best support the answer. Never invent IDs or quote text.
- answer_text must summarize patterns across the evidence, not quote users verbatim.
- confidence=high when evidence is consistent and specific; low when evidence is thin or mixed.
- Focus on music discovery, recommendations, playlists, and finding new music.
"""

QA_SYNTHESIS_REPAIR_SUFFIX = """

Your previous response failed validation: {error}
Return corrected JSON only. evidence_ids must be chosen from the provided item_id list.
"""


def build_qa_synthesis_prompt(
    *,
    question_id: str,
    question_text: str,
    quotes: list[dict[str, object]],
) -> str:
    lines = [
        f"Question {question_id}: {question_text}",
        "",
        "Synthesize a grounded answer using only the evidence quotes below.",
        "Return answer_text, evidence_ids (from item_id values), and confidence.",
        "",
    ]
    allowed_ids = [str(quote["item_id"]) for quote in quotes]
    lines.append(f"Allowed evidence_ids: {', '.join(allowed_ids)}")
    lines.append("")
    for index, quote in enumerate(quotes, start=1):
        lines.append(f"Quote {index}:")
        lines.append(f"  item_id: {quote['item_id']}")
        lines.append(f"  source: {quote.get('source', 'unknown')}")
        if quote.get("rating") is not None:
            lines.append(f"  rating: {quote['rating']}")
        if quote.get("sentiment_label"):
            lines.append(f"  sentiment: {quote['sentiment_label']}")
        if quote.get("intent"):
            lines.append(f"  intent: {quote['intent']}")
        lines.append(f"  text: {quote['text']}")
        lines.append("")
    return "\n".join(lines)
