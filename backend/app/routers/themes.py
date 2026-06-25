import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.themes import ThemeDetail, ThemesResponse
from app.services.themes import get_theme, list_themes

router = APIRouter(tags=["themes"])


@router.get("/themes", response_model=ThemesResponse)
def read_themes(session: Session = Depends(get_db)) -> ThemesResponse:
    return list_themes(session)


@router.get("/themes/{theme_id}", response_model=ThemeDetail)
def read_theme(theme_id: uuid.UUID, session: Session = Depends(get_db)) -> ThemeDetail:
    return get_theme(session, theme_id)
