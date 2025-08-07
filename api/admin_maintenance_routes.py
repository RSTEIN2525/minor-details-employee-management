import os
from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from core.deps import get_session, require_admin_role
from services.shift_guard import run_shift_guard_once_async


router = APIRouter()


@router.post("/run-shift-guard")
async def run_shift_guard_single_execution(
    threshold_hours: Optional[float] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    One-shot execution of the Shift Guard. Admin-only (Bearer token with admin role).

    Query params:
    - threshold_hours: optional override; defaults to env SHIFT_GUARD_THRESHOLD_HOURS or 15.0
    """
    default_threshold = float(os.getenv("SHIFT_GUARD_THRESHOLD_HOURS", "15"))
    effective_threshold = float(threshold_hours) if threshold_hours is not None else default_threshold

    await run_shift_guard_once_async(effective_threshold)

    return {"status": "ok", "threshold_hours": effective_threshold}


