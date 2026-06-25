import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import FeedbackItem, PipelineRun, RawDocument

EXPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "ingested"


def export_snapshot(session: Session, output_path: Path | None = None) -> Path:
    """Write a JSON snapshot of ingested data for local inspection."""
    output_path = output_path or (EXPORT_DIR / "latest_snapshot.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = session.scalars(select(FeedbackItem).order_by(FeedbackItem.item_date.desc())).all()
    runs = session.scalars(select(PipelineRun).order_by(PipelineRun.started_at.desc())).all()

    per_source = session.execute(
        select(FeedbackItem.source, func.count()).group_by(FeedbackItem.source)
    ).all()

    payload: dict[str, Any] = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "total_items": len(items),
        "items_per_source": {source: count for source, count in per_source},
        "pipeline_runs": [
            {
                "id": str(run.id),
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "item_counts": run.item_counts,
            }
            for run in runs
        ],
        "feedback_items": [
            {
                "id": str(item.id),
                "source": item.source,
                "external_id": item.external_id,
                "title": item.title,
                "text": item.text,
                "rating": item.rating,
                "item_date": item.item_date.isoformat(),
                "raw_document_id": str(item.raw_document_id) if item.raw_document_id else None,
            }
            for item in items
        ],
    }

    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def export_summary(session: Session) -> dict[str, Any]:
    per_source = session.execute(
        select(FeedbackItem.source, func.count()).group_by(FeedbackItem.source)
    ).all()
    return {
        "total_items": session.scalar(select(func.count()).select_from(FeedbackItem)) or 0,
        "raw_documents": session.scalar(select(func.count()).select_from(RawDocument)) or 0,
        "items_per_source": {source: count for source, count in per_source},
    }
