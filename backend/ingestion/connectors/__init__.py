from ingestion.connectors.app_store import AppStoreConnector
from ingestion.connectors.community import CommunityConnector
from ingestion.connectors.play_store import PlayStoreConnector
from ingestion.connectors.reddit import RedditConnector
from ingestion.connectors.social import SocialConnector

ALL_SOURCES = (
    "app_store",
    "play_store",
    "reddit",
    "community",
    "social",
)

# Active sources for default ingestion (Reddit disabled until API keys are configured).
DEFAULT_SOURCES = (
    "app_store",
    "play_store",
    "community",
    "social",
)

__all__ = [
    "ALL_SOURCES",
    "DEFAULT_SOURCES",
    "AppStoreConnector",
    "CommunityConnector",
    "PlayStoreConnector",
    "RedditConnector",
    "SocialConnector",
]
