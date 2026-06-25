from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.questions import QuestionAnswer, QuestionsResponse
from app.services import QUESTION_ORDER, QUESTION_TEXT, parse_uuid_list, require_active_run
from db.models import Answer


def list_questions(session: Session) -> QuestionsResponse:
    run = require_active_run(session)
    answers = list(
        session.scalars(
            select(Answer)
            .where(Answer.pipeline_run_id == run.id)
            .order_by(Answer.question_id)
        ).all()
    )
    answers_by_id = {answer.question_id: answer for answer in answers}

    items: list[QuestionAnswer] = []
    for question_id in QUESTION_ORDER:
        answer = answers_by_id.get(question_id)
        if answer is None:
            continue
        items.append(
            QuestionAnswer(
                question_id=answer.question_id,
                question_text=QUESTION_TEXT[answer.question_id],
                answer_text=answer.answer_text,
                evidence_ids=parse_uuid_list(answer.evidence_ids or []),
                confidence=answer.confidence,
                source_breakdown=answer.source_breakdown,
            )
        )

    return QuestionsResponse(items=items, pipeline_run_id=run.id)
