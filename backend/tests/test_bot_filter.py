from core.bot_filter import is_bot_post, sql_bot_exclusion_clauses
from db.models import FeedbackItem


def test_is_bot_post_detects_nowplaying_spotify_bots():
    text = (
        "#NowPlaying on #BBC6Music's #CraigCharles Gurriers: Nobody's Coming To Save You "
        "#6music #Gurriers Automagic show playlist on Spotify Song on #Spotify:"
    )
    assert is_bot_post(text)


def test_is_bot_post_allows_real_reviews():
    assert not is_bot_post("Discover Weekly feels stale and never surprises me anymore.")
    assert not is_bot_post("I wish Spotify would reset my recommendations.")


def test_sql_bot_exclusion_clauses_builds_expression():
    clause = sql_bot_exclusion_clauses(FeedbackItem.text)
    assert clause is not None
