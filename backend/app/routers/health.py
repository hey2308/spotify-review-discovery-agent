from fastapi import APIRouter

from core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.app_env,
        "mock_mode": str(settings.mock_mode).lower(),
    }
