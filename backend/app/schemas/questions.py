import uuid

from pydantic import BaseModel, ConfigDict


class QuestionAnswer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: str
    question_text: str
    answer_text: str
    evidence_ids: list[uuid.UUID] = []
    confidence: str | None = None
    source_breakdown: dict[str, int] | None = None


class QuestionsResponse(BaseModel):
    items: list[QuestionAnswer]
    pipeline_run_id: uuid.UUID | None = None
