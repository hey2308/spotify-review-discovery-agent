from core.discovery_filter import text_mentions_discovery


def test_text_mentions_discovery_matches_keywords() -> None:
    assert text_mentions_discovery("Discover Weekly is stale")
    assert text_mentions_discovery("Bad recommendations lately")
    assert text_mentions_discovery("The Spotify algorithm pushes the same artists")
    assert not text_mentions_discovery("The app crashes on launch")
    assert not text_mentions_discovery("Great radio app for listening at work")
