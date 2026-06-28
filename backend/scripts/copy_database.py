"""Copy an existing SQLite snapshot into PostgreSQL (e.g. Render) without re-running the pipeline."""

from __future__ import annotations

from pathlib import Path

import typer
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.db_copy import normalize_copy_row
from core.config import get_settings
from core.db_url import normalize_database_url
from db import models  # noqa: F401 — register ORM tables
from db.base import Base

app = typer.Typer(help="Copy database snapshot between SQLite and PostgreSQL")

# Insert order respects foreign keys.
TABLE_ORDER = [
    "pipeline_runs",
    "raw_documents",
    "feedback_items",
    "themes",
    "feedback_themes",
    "cluster_assignments",
    "segments",
    "analyses",
    "answers",
    "unmet_needs",
]

DEFAULT_SQLITE = (
    Path(__file__).resolve().parents[2] / "data" / "spotify_discovery.db"
)


def _normalize_row(row: dict) -> dict:
    return normalize_copy_row(row)


def _truncate_target(session: Session) -> None:
    tables = ", ".join(TABLE_ORDER)
    session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    session.commit()


def _copy_table(source: Session, target: Session, table_name: str, batch_size: int) -> int:
    table = Base.metadata.tables[table_name]
    rows = [dict(row) for row in source.execute(select(table)).mappings()]
    if not rows:
        return 0

    payload = [_normalize_row(row) for row in rows]
    for offset in range(0, len(payload), batch_size):
        target.execute(table.insert(), payload[offset : offset + batch_size])
    target.commit()
    return len(payload)


def _summarize(session: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in TABLE_ORDER:
        counts[table_name] = session.scalar(
            text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608 — fixed table names
        ) or 0
    return counts


def _engine(url: str) -> Engine:
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


@app.callback(invoke_without_command=True)
def main(
    source: str = typer.Option(
        f"sqlite+pysqlite:///{DEFAULT_SQLITE.as_posix()}",
        "--source",
        help="Source database URL (default: local SQLite snapshot)",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Target PostgreSQL URL (defaults to DATABASE_URL from .env)",
    ),
    batch_size: int = typer.Option(500, "--batch-size", min=1, max=5000),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print row counts only"),
) -> None:
    """Copy all dashboard tables from SQLite into PostgreSQL."""
    if not source.startswith("sqlite"):
        raise typer.BadParameter("Source must be a SQLite database URL.")

    resolved_target = target or get_settings().database_url
    if not (resolved_target.startswith("postgresql") or resolved_target.startswith("postgres")):
        raise typer.BadParameter("Target must be a PostgreSQL database URL in .env or --target.")

    resolved_target = normalize_database_url(resolved_target)

    source_path = source.split("///", 1)[-1]
    if source.startswith("sqlite") and not Path(source_path).exists():
        raise typer.BadParameter(f"SQLite file not found: {source_path}")

    source_engine = _engine(source)
    target_engine = _engine(resolved_target)
    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    with SourceSession() as source_session:
        source_counts = _summarize(source_session)
        typer.echo("Source row counts:")
        for table_name, count in source_counts.items():
            typer.echo(f"  {table_name}: {count}")

        if dry_run:
            return

        with TargetSession() as target_session:
            typer.echo("Truncating target tables...")
            _truncate_target(target_session)

            total = 0
            for table_name in TABLE_ORDER:
                copied = _copy_table(source_session, target_session, table_name, batch_size)
                total += copied
                typer.echo(f"  copied {table_name}: {copied}")

            target_counts = _summarize(target_session)
            typer.echo("Target row counts:")
            for table_name, count in target_counts.items():
                typer.echo(f"  {table_name}: {count}")

    typer.echo(f"Done. Copied {total} rows into PostgreSQL.")


if __name__ == "__main__":
    app()
