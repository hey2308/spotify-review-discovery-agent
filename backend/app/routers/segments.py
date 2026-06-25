from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.segments import SegmentsResponse
from app.services.segments import list_segments

router = APIRouter(tags=["segments"])


@router.get("/segments", response_model=SegmentsResponse)
def read_segments(session: Session = Depends(get_db)) -> SegmentsResponse:
    return list_segments(session)
