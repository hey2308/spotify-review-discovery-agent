import re

BOT_POST_PATTERN = re.compile(
    r"(?:"
    r"#NowPlaying"
    r"|Automagic show playlist"
    r"|Song on #Spotify"
    r"|show playlist on Spotify"
    r")",
    re.IGNORECASE,
)


def is_bot_post(text: str) -> bool:
    return bool(BOT_POST_PATTERN.search(text))


def sql_bot_exclusion_clauses(column):
    """SQLAlchemy expressions that exclude automated social playlist-bot posts."""
    from sqlalchemy import not_, or_

    return not_(
        or_(
            column.ilike("%#NowPlaying%"),
            column.ilike("%Automagic show playlist%"),
            column.ilike("%Song on #Spotify%"),
            column.ilike("%show playlist on Spotify%"),
        )
    )
