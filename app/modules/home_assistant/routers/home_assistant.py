from fastapi import APIRouter, HTTPException
from httpx import HTTPError

from app.modules.home_assistant.services.home_assistant_service import (
    home_assistant_service,
)


router = APIRouter(
    prefix="/home-assistant",
    tags=["Home Assistant"],
)


@router.get("/connection")
async def check_home_assistant_connection():
    try:
        result = await home_assistant_service.check_connection()

        return {
            "status": "connected",
            "home_assistant": result,
        }

    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Home Assistant connection failed: {exc}",
        )