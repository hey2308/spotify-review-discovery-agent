from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.meta import MetaResponse
from app.services.meta import get_meta

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse)
def read_meta(
    response: Response,
    session: Session = Depends(get_db),
) -> MetaResponse:
    response.headers["Cache-Control"] = "public, max-age=300"
    return get_meta(session)
