import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.integration


@pytest.fixture
def alembic_config(tmp_path, monkeypatch):
    database_url = os.getenv("DATABASE_URL")
    if not database_url or database_url.startswith("sqlite"):
        pytest.skip("DATABASE_URL must point to PostgreSQL for migration integration tests")

    monkeypatch.chdir(os.path.dirname(os.path.dirname(__file__)))
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config, database_url


def test_migration_upgrade_and_downgrade(alembic_config):
    config, database_url = alembic_config
    engine = create_engine(database_url)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "pipeline_runs",
        "raw_documents",
        "feedback_items",
        "themes",
        "feedback_themes",
        "segments",
        "analyses",
        "answers",
        "unmet_needs",
        "alembic_version",
    }
    assert expected.issubset(tables)

    command.downgrade(config, "base")
    tables_after = set(inspect(engine).get_table_names())
    assert "feedback_items" not in tables_after
