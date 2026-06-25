SEGMENT_ROLLUP_SYSTEM_PROMPT = """You summarize Spotify user segments for a discovery intelligence dashboard.

Return valid JSON only with this shape:
{
  "segments": [
    {
      "segment_key": "<snake_case key from input>",
      "label": "<human-readable segment name>",
      "top_frustration": "<one sentence>",
      "top_unmet_need": "<one sentence>",
      "top_behavior": "<one sentence>"
    }
  ]
}

Rules:
- Use ONLY the provided segment statistics and sample quotes as evidence.
- Each segment must have all three rollup fields filled in.
- Keep each field under 160 characters.
- Focus on discovery and recommendation challenges when present.
"""

SEGMENT_ROLLUP_REPAIR_SUFFIX = """

Your previous response failed validation: {error}
Return corrected JSON only, matching the schema exactly.
"""


def build_segment_rollup_prompt(segments: list[dict[str, object]]) -> str:
    lines = [
        "Summarize each user segment with top frustration, unmet need, and behavior.",
        "",
    ]
    for segment in segments:
        lines.append(f"Segment key: {segment['segment_key']}")
        lines.append(f"  label_hint: {segment.get('label_hint', '')}")
        lines.append(f"  item_count: {segment.get('item_count', 0)}")
        lines.append(f"  top_intents: {segment.get('top_intents', [])}")
        lines.append(f"  top_behaviors: {segment.get('top_behaviors', [])}")
        lines.append(f"  mean_sentiment: {segment.get('mean_sentiment')}")
        for index, quote in enumerate(segment.get("sample_quotes", []), start=1):
            lines.append(f"  sample_{index}: {quote}")
        lines.append("")
    return "\n".join(lines)
