from abc import ABC, abstractmethod
from datetime import datetime

from ingestion.types import FetchedRecord, NormalizedItem


class SourceConnector(ABC):
    source_name: str

    @abstractmethod
    def fetch(self, since: datetime, until: datetime) -> list[FetchedRecord]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, record: FetchedRecord) -> NormalizedItem | None:
        raise NotImplementedError
