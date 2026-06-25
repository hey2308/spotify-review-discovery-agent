CLASSIFICATION_SYSTEM_PROMPT = """You classify public Spotify user feedback for a
discovery intelligence dashboard.

Return valid JSON only with this shape:
{
  "classifications": [
    {
      "item_id": "<uuid>",
      "sentiment_label": "positive" | "neutral" | "negative",
      "sentiment_score": <float 0.0-1.0, higher = more positive>,
      "intent": "<short listening goal phrase>",
      "behavior_signals": ["<signal>", ...],
      "segment_hint": "<user segment guess>"
    }
  ]
}

Rules:
- Classify every input item; keep item_id unchanged.
- sentiment_label must be positive, neutral, or negative.
- behavior_signals: 0-4 short snake_case tags (e.g. repeats_same_artist, skips_recommendations).
- segment_hint examples: casual_listener, power_user, new_user, long_term_subscriber,
  genre_locked, eclectic_explorer.
- intent examples: discover_new_music, comfort_listen, focus_work, workout,
  mood_match, playlist_curation.
- Base sentiment on discovery/recommendation frustration when present, not generic praise.
"""

CLASSIFICATION_REPAIR_SUFFIX = """

Your previous response failed validation: {error}
Return corrected JSON only, matching the schema exactly.
"""


def build_classification_prompt(items: list[dict[str, object]]) -> str:
    lines = [
        "Classify each feedback item below.",
        "Return one classification per item_id.",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.append(f"Item {index}:")
        lines.append(f"  item_id: {item['id']}")
        lines.append(f"  source: {item.get('source', 'unknown')}")
        if item.get("rating") is not None:
            lines.append(f"  rating: {item['rating']}")
        if item.get("title"):
            lines.append(f"  title: {item['title']}")
        lines.append(f"  text: {item['text']}")
        lines.append("")
    return "\n".join(lines)
