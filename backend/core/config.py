from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from core.db_url import normalize_database_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(alias="DATABASE_URL")

    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model_small: str = Field(default="llama-3.1-8b-instant", alias="GROQ_MODEL_SMALL")
    groq_model_large: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL_LARGE")

    embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        alias="EMBEDDING_MODEL",
    )
    chroma_persist_dir: str = Field(default="./chroma_data", alias="CHROMA_PERSIST_DIR")
    chroma_collection: str = Field(default="feedback_embeddings", alias="CHROMA_COLLECTION")
    embedding_batch_size: int = Field(default=64, alias="EMBEDDING_BATCH_SIZE")
    embedding_max_text_chars: int = Field(default=2000, alias="EMBEDDING_MAX_TEXT_CHARS")

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173"], alias="CORS_ORIGINS"
    )

    reddit_client_id: str | None = Field(default=None, alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = Field(default=None, alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(
        default="spotify-discovery-agent/0.1", alias="REDDIT_USER_AGENT"
    )
    community_feed_url: str = Field(
        default="https://community.spotify.com/rss/message?board.id=iOS_iPhone_iPad",
        alias="COMMUNITY_FEED_URL",
    )
    ingest_throttle_seconds: float = Field(default=0.5, alias="INGEST_THROTTLE_SECONDS")
    ingest_min_words: int = Field(default=6, alias="INGEST_MIN_WORDS")
    ingest_english_only: bool = Field(default=True, alias="INGEST_ENGLISH_ONLY")
    play_store_max_reviews: int = Field(default=3000, alias="PLAY_STORE_MAX_REVIEWS")
    play_store_page_size: int = Field(default=200, alias="PLAY_STORE_PAGE_SIZE")
    bluesky_search_queries: Annotated[list[str], NoDecode] = Field(
        default=[
            "spotify discovery",
            "spotify recommendations",
            "spotify algorithm",
            "spotify discover weekly",
            "spotify playlist",
            "spotify shuffle",
            "spotify radio",
            "spotify repeat",
            "spotify stale",
            "spotify wrapped",
            "spotify release radar",
            "spotify daily mix",
            "spotify autoplay",
            "spotify home feed",
            "spotify bad recommendations",
            "spotify find new music",
            "spotify music discovery",
        ],
        alias="BLUESKY_SEARCH_QUERIES",
    )
    mastodon_instances: Annotated[list[str], NoDecode] = Field(
        default=[
            "https://mastodon.social",
            "https://mastodon.online",
            "https://fosstodon.org",
            "https://mas.to",
            "https://hachyderm.io",
            "https://techhub.social",
        ],
        alias="MASTODON_INSTANCES",
    )
    mastodon_tags: Annotated[list[str], NoDecode] = Field(
        default=["spotifydiscovery", "discoverweekly", "spotify"],
        alias="MASTODON_TAGS",
    )
    social_max_items: int = Field(default=3000, alias="SOCIAL_MAX_ITEMS")
    bluesky_page_size: int = Field(default=100, alias="BLUESKY_PAGE_SIZE")
    mastodon_page_size: int = Field(default=40, alias="MASTODON_PAGE_SIZE")
    bluesky_slice_days: int = Field(default=14, alias="BLUESKY_SLICE_DAYS")
    mastodon_max_pages: int = Field(default=50, alias="MASTODON_MAX_PAGES")
    classification_batch_size: int = Field(default=16, alias="CLASSIFICATION_BATCH_SIZE")
    classification_max_text_chars: int = Field(default=400, alias="CLASSIFICATION_MAX_TEXT_CHARS")
    groq_small_rpm: int = Field(default=25, alias="GROQ_SMALL_RPM")
    groq_large_rpm: int = Field(default=25, alias="GROQ_LARGE_RPM")
    groq_max_retries: int = Field(default=2, alias="GROQ_MAX_RETRIES")

    max_themes: int = Field(default=5, alias="MAX_THEMES")
    umap_n_neighbors: int = Field(default=15, alias="UMAP_N_NEIGHBORS")
    umap_n_components: int = Field(default=5, alias="UMAP_N_COMPONENTS")
    umap_min_dist: float = Field(default=0.0, alias="UMAP_MIN_DIST")
    umap_random_state: int = Field(default=42, alias="UMAP_RANDOM_STATE")
    hdbscan_min_cluster_size: int = Field(default=30, alias="HDBSCAN_MIN_CLUSTER_SIZE")
    hdbscan_min_samples: int | None = Field(default=None, alias="HDBSCAN_MIN_SAMPLES")

    theme_label_quote_count: int = Field(default=8, alias="THEME_LABEL_QUOTE_COUNT")
    theme_representative_quotes: int = Field(default=5, alias="THEME_REPRESENTATIVE_QUOTES")
    analysis_export_dir: str = Field(default="../data/analyzed", alias="ANALYSIS_EXPORT_DIR")

    qa_retrieval_count: int = Field(default=20, alias="QA_RETRIEVAL_COUNT")
    qa_synthesis_quote_count: int = Field(default=10, alias="QA_SYNTHESIS_QUOTE_COUNT")
    qa_min_evidence: int = Field(default=3, alias="QA_MIN_EVIDENCE")
    segment_min_items: int = Field(default=5, alias="SEGMENT_MIN_ITEMS")
    unmet_needs_retrieval_count: int = Field(default=30, alias="UNMET_NEEDS_RETRIEVAL_COUNT")
    unmet_needs_max_items: int = Field(default=8, alias="UNMET_NEEDS_MAX_ITEMS")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url_field(cls, value: str) -> str:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "bluesky_search_queries",
        "mastodon_instances",
        "mastodon_tags",
        mode="before",
    )
    @classmethod
    def parse_csv_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def mock_mode(self) -> bool:
        return not self.groq_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
