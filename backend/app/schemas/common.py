from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DateRange(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")


class CountsSnapshot(BaseModel):
    feedback_items: int = 0
    analyses: int = 0
    themes: int = 0
    answers: int = 0
    segments: int = 0
    unmet_needs: int = 0


def to_date(value: datetime) -> date:
    return value.date()
