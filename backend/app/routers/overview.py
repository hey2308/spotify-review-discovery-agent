from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.overview import OverviewResponse
from app.services.overview import get_overview

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def read_overview(session: Session = Depends(get_db)) -> OverviewResponse:
    return get_overview(session)
