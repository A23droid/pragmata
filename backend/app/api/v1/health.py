from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.db.session import get_db
from backend.app.schemas.health import HealthResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def check_health(
    check_db: bool = Query(False, description="Whether to check database connectivity"),
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    db_status = "not_checked"

    if check_db:
        try:
            result = await db.execute(text("SELECT 1"))
            if result.scalar() == 1:
                db_status = "connected"
            else:
                db_status = "unexpected_response"
        except Exception as e:
            logger.warning(f"Database health check failed: {e}")
            db_status = "disconnected"

    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc),
        database=db_status,
    )
