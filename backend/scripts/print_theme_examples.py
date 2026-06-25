import json
import sqlite3
from textwrap import shorten

RUN_ID = "669ca52cc5eb4c6f852a9a278f2679cc"
DB = r"c:/Projects/Grad_Project/data/spotify_discovery.db"

KEYWORDS = {
    "Algorithmic Music Discovery Issues": [
        "algorithm",
        "discover",
        "recommend",
        "taste profile",
        "personalized",
        "music discovery",
    ],
    "Discover Weekly stopped surprising me": [
        "discover weekly",
        "stale",
        "old taste",
        "years ago",
        "gotten worse",
        "release radar",
    ],
    "Can't explore a new genre confidently": [
        "genre",
        "explore",
        "mood",
        "jazz",
        "emotional",
        "niche",
        "underground",
    ],
    "Shuffle Play Frustration": [
        "shuffle",
        "smart shuffle",
        "autoplay",
        "radio",
        "repeat",
        "same songs",
    ],
    "Algorithm locks me into a bubble": [
        "bubble",
        "filter bubble",
        "same artist",
        "on repeat",
        "knows me too well",
        "flooded",
    ],
}


def main() -> None:
    conn = sqlite3.connect(DB)
    themes = conn.execute(
        """
        SELECT id, name, summary, mention_volume, sentiment_score, source_breakdown
        FROM themes
        WHERE pipeline_run_id = ?
        ORDER BY mention_volume DESC
        """,
        (RUN_ID,),
    ).fetchall()

    for theme_id, name, summary, volume, sentiment, source_breakdown in themes:
        print("=" * 72)
        print(name)
        print(f"Items: {volume} | Avg sentiment: {sentiment:.2f}")
        print(f"Summary: {summary}")
        print(f"Sources: {source_breakdown}")

        keywords = KEYWORDS.get(name, [])
        rows = conn.execute(
            """
            SELECT fi.text, fi.source, fi.rating, a.sentiment_label
            FROM feedback_themes ft
            JOIN feedback_items fi ON fi.id = ft.feedback_item_id
            LEFT JOIN analyses a ON a.feedback_item_id = fi.id
            WHERE ft.theme_id = ?
            """,
            (theme_id,),
        ).fetchall()

        scored: list[tuple[int, str, str, int | None, str | None]] = []
        for text, source, rating, label in rows:
            hits = sum(1 for keyword in keywords if keyword.lower() in text.lower())
            scored.append((hits, text, source, rating, label))
        scored.sort(key=lambda item: (-item[0], -len(item[1])))

        shown = 0
        for hits, text, source, rating, label in scored:
            if shown >= 4:
                break
            if len(text.split()) < 8 and hits == 0 and shown < 2:
                continue
            snippet = shorten(text.replace("\n", " "), width=280, placeholder="...")
            rating_label = f"stars={rating}" if rating is not None else "no rating"
            print(f"  - [{source}] {rating_label} ({label or 'n/a'})")
            print(f'    "{snippet}"')
            shown += 1
        print()


if __name__ == "__main__":
    main()
