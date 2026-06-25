import typer

from core.config import get_settings
from db.base import Base
from db.session import SessionLocal, get_engine, reset_engine_cache
from ingestion.connectors import ALL_SOURCES, DEFAULT_SOURCES
from ingestion.export import export_snapshot, export_summary
from ingestion.service import ingest_all

app = typer.Typer(help="Spotify Discovery ingestion commands")


@app.command("ingest")
def ingest(
    source: list[str] = typer.Option(
        None,
        "--source",
        "-s",
        help="Limit ingestion to specific sources (default: all except Reddit)",
    ),
    months: int = typer.Option(6, "--months", min=1, max=24),
    export: bool = typer.Option(True, "--export/--no-export", help="Export JSON snapshot after ingest"),
) -> None:
    """Fetch public feedback and store canonical, PII-scrubbed items."""
    reset_engine_cache()
    settings = get_settings()
    invalid = [name for name in (source or []) if name not in ALL_SOURCES]
    if invalid:
        raise typer.BadParameter(f"Unknown sources: {', '.join(invalid)}")

    with SessionLocal() as session:
        result = ingest_all(
            session,
            sources=source or None,
            months=months,
            settings=settings,
        )
        summary = export_summary(session)
        snapshot_path = None
        if export:
            snapshot_path = export_snapshot(session)

    typer.echo(f"Pipeline run: {result.pipeline_run_id}")
    typer.echo(f"Total items in database: {summary['total_items']}")
    for source_name, stats in result.stats.items():
        typer.echo(
            f"{source_name}: fetched={stats.fetched} inserted={stats.inserted} "
            f"duplicates={stats.skipped_duplicate}"
        )
    if snapshot_path:
        typer.echo(f"Exported snapshot: {snapshot_path}")


@app.command("export")
def export() -> None:
    """Export current ingested data to data/ingested/latest_snapshot.json."""
    reset_engine_cache()
    with SessionLocal() as session:
        path = export_snapshot(session)
        summary = export_summary(session)
    typer.echo(f"Exported {summary['total_items']} items to {path}")


@app.command("init-db")
def init_db() -> None:
    """Create tables when migrations are not available (local dev helper)."""
    reset_engine_cache()
    Base.metadata.create_all(bind=get_engine())
    typer.echo(f"Database tables created at {get_settings().database_url}.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
