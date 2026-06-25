from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.unmet_needs import UnmetNeedsResponse
from app.services.unmet_needs import list_unmet_needs

router = APIRouter(tags=["unmet-needs"])


@router.get("/unmet-needs", response_model=UnmetNeedsResponse)
def read_unmet_needs(session: Session = Depends(get_db)) -> UnmetNeedsResponse:
    return list_unmet_needs(session)
