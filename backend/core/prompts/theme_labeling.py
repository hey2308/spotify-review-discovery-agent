THEME_LABEL_SYSTEM_PROMPT = """You label clusters of public Spotify user feedback for a
discovery intelligence dashboard.

Return valid JSON only with this shape:
{
  "name": "<short theme title, 3-8 words>",
  "summary": "<one-line summary of the shared frustration or praise>"
}

Rules:
- Use the provided verbatim quotes only as evidence; do NOT copy or paraphrase them in the output.
- The name and summary must describe the cluster pattern, not quote individual users.
- Focus on discovery, recommendations, playlists, and finding new music when present.
- Keep the summary under 200 characters.
"""

THEME_LABEL_REPAIR_SUFFIX = """

Your previous response failed validation: {error}
Return corrected JSON only, matching the schema exactly.
"""


def build_theme_label_prompt(
    *,
    cluster_id: int,
    quotes: list[dict[str, object]],
) -> str:
    lines = [
        f"Label cluster {cluster_id} using the representative verbatim quotes below.",
        "Return a theme name and one-line summary only.",
        "",
    ]
    for index, quote in enumerate(quotes, start=1):
        lines.append(f"Quote {index}:")
        lines.append(f"  item_id: {quote['item_id']}")
        lines.append(f"  source: {quote.get('source', 'unknown')}")
        if quote.get("rating") is not None:
            lines.append(f"  rating: {quote['rating']}")
        lines.append(f"  text: {quote['text']}")
        lines.append("")
    return "\n".join(lines)
