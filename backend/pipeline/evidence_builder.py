import json
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import Settings
from core.vectorstore import VectorStore, get_vector_store
from db.models import Analysis, FeedbackItem, FeedbackTheme, PipelineRun, Theme
from pipeline.embedding_utils import nearest_to_centroid

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EvidenceStats:
    themes_updated: int = 0
    quotes_selected: int = 0
    report_path: str | None = None
    details: dict[str, object] = field(default_factory=dict)


def _load_embedding_map(
    settings: Settings,
    *,
    mock: bool,
    vector_store: VectorStore | None,
) -> dict[str, list[float]]:
    store = vector_store or get_vector_store(settings, force_mock=mock)
    ids, embeddings, _metadatas = store.get_all_vectors()
    return dict(zip(ids, embeddings, strict=True))


def _source_breakdown(items: list[FeedbackItem]) -> dict[str, int]:
    counts = Counter(item.source for item in items)
    return dict(sorted(counts.items()))


def _select_representative_quotes(
    member_ids: set[str],
    embedding_map: dict[str, list[float]],
    *,
    quote_count: int,
) -> list[str]:
    selected = nearest_to_centroid(
        sorted(member_ids),
        embedding_map,
        n_results=quote_count,
    )
    if not selected:
        return sorted(member_ids)[:quote_count]

    invalid = [item_id for item_id in selected if item_id not in member_ids]
    if invalid:
        raise RuntimeError(
            f"Representative quote selection leaked across clusters: {invalid[:3]}"
        )
    return selected


def _build_pipeline_report(
    session: Session,
    run_id: uuid.UUID,
    *,
    themes: list[Theme],
) -> dict[str, object]:
    pipeline_run = session.get(PipelineRun, run_id)
    feedback_count = session.scalar(select(func.count()).select_from(FeedbackItem)) or 0
    classified_count = session.scalar(select(func.count()).select_from(Analysis)) or 0
    coverage = (classified_count / feedback_count) if feedback_count else 0.0

    theme_rows: list[dict[str, object]] = []
    for theme in themes:
        theme_rows.append(
            {
                "theme_id": str(theme.id),
                "cluster_id": theme.cluster_id,
                "name": theme.name,
                "summary": theme.summary,
                "mention_volume": theme.mention_volume,
                "sentiment_score": theme.sentiment_score,
                "representative_quote_ids": theme.representative_quote_ids,
                "source_breakdown": theme.source_breakdown,
            }
        )

    return {
        "pipeline_run_id": str(run_id),
        "generated_at": datetime.now(UTC).isoformat(),
        "status": pipeline_run.status if pipeline_run else "unknown",
        "feedback_items": feedback_count,
        "classified_items": classified_count,
        "classification_coverage": round(coverage, 4),
        "theme_count": len(themes),
        "themes": theme_rows,
        "stage_stats": pipeline_run.item_counts if pipeline_run else {},
    }


def _write_report(settings: Settings, run_id: uuid.UUID, report: dict[str, object]) -> Path:
    export_dir = Path(settings.analysis_export_dir)
    if not export_dir.is_absolute():
        export_dir = Path(__file__).resolve().parents[2] / export_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    report_path = export_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def attach_theme_evidence(
    session: Session,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    dry_run: bool = False,
    mock: bool = False,
    vector_store: VectorStore | None = None,
) -> EvidenceStats:
    stats = EvidenceStats()
    themes = list(
        session.scalars(
            select(Theme)
            .where(Theme.pipeline_run_id == run_id)
            .order_by(Theme.cluster_id)
        ).all()
    )

    if dry_run:
        stats.themes_updated = len(themes)
        stats.quotes_selected = len(themes) * settings.theme_representative_quotes
        stats.details = {"mode": "dry_run"}
        return stats

    if not themes:
        raise RuntimeError(f"No themes found for run {run_id}. Run the theme_labels stage first.")

    if len(themes) > settings.max_themes:
        raise RuntimeError(
            f"Found {len(themes)} themes for run {run_id}; max allowed is {settings.max_themes}"
        )

    embedding_map = _load_embedding_map(settings, mock=mock, vector_store=vector_store)

    for theme in themes:
        member_rows = list(
            session.scalars(
                select(FeedbackItem)
                .join(FeedbackTheme, FeedbackTheme.feedback_item_id == FeedbackItem.id)
                .where(FeedbackTheme.theme_id == theme.id)
            ).all()
        )
        member_ids = {str(item.id) for item in member_rows}

        quote_ids = _select_representative_quotes(
            member_ids,
            embedding_map,
            quote_count=settings.theme_representative_quotes,
        )
        if not quote_ids:
            quote_ids = sorted(member_ids)[: settings.theme_representative_quotes]

        theme.representative_quote_ids = quote_ids
        theme.source_breakdown = _source_breakdown(member_rows)
        theme.mention_volume = len(member_rows)
        theme.sentiment_score = _mean_sentiment(session, member_rows)

        stats.themes_updated += 1
        stats.quotes_selected += len(quote_ids)
        logger.info(
            "Selected %s representative quotes for theme %r",
            len(quote_ids),
            theme.name,
        )

    session.flush()

    report = _build_pipeline_report(session, run_id, themes=themes)
    report_path = _write_report(settings, run_id, report)
    stats.report_path = str(report_path)
    stats.details = {
        "mode": "mock" if mock else "local",
        "theme_count": len(themes),
        "classification_coverage": report["classification_coverage"],
    }

    logger.info("Pipeline report written to %s", report_path)
    return stats


def _mean_sentiment(session: Session, items: list[FeedbackItem]) -> float | None:
    if not items:
        return None

    item_ids = [item.id for item in items]
    scores = list(
        session.scalars(
            select(Analysis.sentiment_score).where(
                Analysis.feedback_item_id.in_(item_ids),
                Analysis.sentiment_score.is_not(None),
            )
        ).all()
    )
    if not scores:
        return None
    return sum(scores) / len(scores)
