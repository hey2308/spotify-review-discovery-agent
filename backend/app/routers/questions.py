from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.questions import QuestionsResponse
from app.services.questions import list_questions

router = APIRouter(tags=["questions"])


@router.get("/questions", response_model=QuestionsResponse)
def read_questions(session: Session = Depends(get_db)) -> QuestionsResponse:
    return list_questions(session)
