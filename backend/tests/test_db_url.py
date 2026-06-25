from core.db_url import normalize_database_url


def test_render_postgresql_url_gets_psycopg_driver_and_ssl() -> None:
    url = normalize_database_url(
        "postgresql://user:pass@dpg-abc.oregon-postgres.render.com/spotify_discovery"
    )
    assert url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in url


def test_postgres_scheme_alias_is_normalized() -> None:
    url = normalize_database_url("postgres://user:pass@localhost/db")
    assert url == "postgresql+psycopg://user:pass@localhost/db"


def test_sqlalchemy_psycopg_url_is_unchanged() -> None:
    url = "postgresql+psycopg://user:pass@localhost/db"
    assert normalize_database_url(url) == url


def test_sqlite_url_is_unchanged() -> None:
    url = "sqlite+pysqlite:///../data/spotify_discovery.db"
    assert normalize_database_url(url) == url


def test_existing_sslmode_is_preserved() -> None:
    url = normalize_database_url(
        "postgresql://user:pass@dpg-abc.oregon-postgres.render.com/db?sslmode=verify-full"
    )
    assert "sslmode=verify-full" in url
    assert "sslmode=require" not in url
