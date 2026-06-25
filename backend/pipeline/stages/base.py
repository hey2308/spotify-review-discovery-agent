import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from core.config import Settings


@dataclass(slots=True)
class StageStats:
    stage: str
    status: str = "completed"
    processed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "processed": self.processed,
            "skipped": self.skipped,
            "duration_seconds": round(self.duration_seconds, 3),
            "details": self.details,
        }


class PipelineStage(ABC):
    name: str

    @abstractmethod
    def run(
        self,
        session: Session,
        settings: Settings,
        run_id: uuid.UUID,
        *,
        dry_run: bool = False,
        mock: bool = False,
    ) -> StageStats:
        """Execute one analysis stage and return structured stats."""
