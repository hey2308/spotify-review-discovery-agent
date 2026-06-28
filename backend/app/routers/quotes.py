import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.quotes import PaginatedQuotes, QuoteFilters
from app.services.quotes import list_quotes

router = APIRouter(tags=["quotes"])


@router.get("/quotes", response_model=PaginatedQuotes)
def read_quotes(
    session: Session = Depends(get_db),
    theme_id: uuid.UUID | None = None,
    source: str | None = None,
    rating: int | None = None,
    rating_min: int | None = None,
    rating_max: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=200),
    discovery_only: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedQuotes:
    filters = QuoteFilters(
        theme_id=theme_id,
        source=source,
        rating=rating,
        rating_min=rating_min,
        rating_max=rating_max,
        date_from=date_from,
        date_to=date_to,
        q=q,
        discovery_only=discovery_only,
        page=page,
        page_size=page_size,
    )
    return list_quotes(session, filters)
