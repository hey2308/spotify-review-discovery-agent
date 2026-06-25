"""Resync feedback_themes from cluster assignments for a pipeline run."""

from __future__ import annotations

import json
import uuid

from db.session import SessionLocal
from pipeline.theme_membership import sync_feedback_themes_from_clusters

RUN_ID = uuid.UUID("669ca52cc5eb4c6f852a9a278f2679cc")


def main() -> None:
    with SessionLocal() as session:
        stats = sync_feedback_themes_from_clusters(session, RUN_ID)
        session.commit()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
