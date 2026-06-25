import logging
import uuid

import typer

from core.config import get_settings
from db.session import SessionLocal, reset_engine_cache
from pipeline.orchestrator import run_analysis
from pipeline.stages import ALL_STAGES

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = typer.Typer(help="Spotify Discovery analysis pipeline commands")


@app.command("analyze")
def analyze(
    stage: list[str] = typer.Option(
        None,
        "--stage",
        "-s",
        help="Limit analysis to specific stages (default: all)",
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Resume a failed analysis run by pipeline run UUID",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Execute the stage chain with mock/no-op stages (writes run metadata)",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Alias for dry-run style mock execution",
    ),
) -> None:
    """Run the AI analysis pipeline (classify → embed → cluster → theme_labels → evidence → qa → segments → unmet_needs)."""
    reset_engine_cache()
    settings = get_settings()

    invalid = [name for name in (stage or []) if name not in ALL_STAGES]
    if invalid:
        raise typer.BadParameter(f"Unknown stages: {', '.join(invalid)}")

    parsed_run_id: uuid.UUID | None = None
    if run_id:
        try:
            parsed_run_id = uuid.UUID(run_id)
        except ValueError as exc:
            raise typer.BadParameter(f"Invalid run-id UUID: {run_id}") from exc

    with SessionLocal() as session:
        result = run_analysis(
            session,
            stages=stage or None,
            run_id=parsed_run_id,
            settings=settings,
            dry_run=dry_run,
            mock=mock,
        )

    typer.echo(f"Pipeline run: {result.pipeline_run_id}")
    typer.echo(f"Status: {result.status}")
    for stage_name, stats in result.stats.items():
        typer.echo(
            f"{stage_name}: processed={stats.processed} skipped={stats.skipped} "
            f"duration={stats.duration_seconds:.3f}s"
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
