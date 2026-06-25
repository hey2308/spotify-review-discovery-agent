UNMET_NEEDS_SYSTEM_PROMPT = """You extract ranked unmet user needs about Spotify music discovery.

Return valid JSON only with this shape:
{
  "needs": [
    {
      "description": "<short need statement>",
      "supporting_ids": ["<item_id>", ...],
      "urgency_score": <0.0-1.0>
    }
  ]
}

Rules:
- Extract 4-8 distinct unmet needs from the evidence quotes.
- supporting_ids must be copied exactly from provided item_id values.
- urgency_score reflects emotional intensity and repetition in the evidence.
- description must be a user-need statement, not a product feature name alone.
- Do not invent quotes or IDs.
"""

UNMET_NEEDS_REPAIR_SUFFIX = """

Your previous response failed validation: {error}
Return corrected JSON only. supporting_ids must be chosen from the provided item_id list.
"""


def build_unmet_needs_prompt(quotes: list[dict[str, object]]) -> str:
    lines = [
        "Extract ranked unmet needs from the evidence quotes below.",
        "Return needs with description, supporting_ids, and urgency_score.",
        "",
    ]
    allowed_ids = [str(quote["item_id"]) for quote in quotes]
    lines.append(f"Allowed supporting_ids: {', '.join(allowed_ids)}")
    lines.append("")
    for index, quote in enumerate(quotes, start=1):
        lines.append(f"Quote {index}:")
        lines.append(f"  item_id: {quote['item_id']}")
        lines.append(f"  source: {quote.get('source', 'unknown')}")
        if quote.get("sentiment_label"):
            lines.append(f"  sentiment: {quote['sentiment_label']}")
        lines.append(f"  text: {quote['text']}")
        lines.append("")
    return "\n".join(lines)
