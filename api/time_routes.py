from datetime import date, datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session, SQLModel, select

from core.deps import get_current_user
from db.session import get_session
from models.clock_request_log import ClockRequestLog, RequestStatusEnum, RequestTypeEnum
from models.time_log import PunchRequest, PunchType, TimeLog
from services.punch_service import PunchService
from utils.database_storage import (
    link_signature_to_time_log,
    store_signature_photo_in_db,
)

# --- Pydantic Models for Request Payloads ---


class BaseClockRequestPayload(SQLModel):
    day_of_punch: date
    requested_start_time_str: str
    requested_end_time_str: str
    dealership_id: str
    reason: str


class ClockEditRequestPayload(BaseClockRequestPayload):
    original_clock_in_timelog_id: int
    original_clock_out_timelog_id: int


class ClockCreateRequestPayload(BaseClockRequestPayload):
    pass


# Defines API Endpoints
router = APIRouter()


# Clock In Endpoint
@router.post("/clock-in")
def clock_in(
    data: PunchRequest,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    # Validate required location data
    if data.latitude is None or data.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Location (latitude and longitude) is required for clock-in.",
        )

    return PunchService.validate_and_save(
        employee_id=user["uid"],
        dealership_id=user["dealerships"],
        punch_type=PunchType.CLOCK_IN,
        latitude=data.latitude,
        longitude=data.longitude,
        session=session,
    )


# Clock Out Endpoint
@router.post("/clock-out")
async def clock_out(
    latitude: Annotated[float, Form()],
    longitude: Annotated[float, Form()],
    injured_at_work: Annotated[bool, Form()],
    safety_signature: Annotated[UploadFile, File(description="Safety signature image")],
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    # First, store the signature photo and get its ID
    signature_photo_id = await store_signature_photo_in_db(
        file=safety_signature, employee_id=user["uid"]
    )

    # Now perform the clock-out with the signature photo ID
    result = PunchService.validate_and_save(
        employee_id=user["uid"],
        dealership_id=user["dealerships"],
        punch_type=PunchType.CLOCK_OUT,
        latitude=latitude,
        longitude=longitude,
        session=session,
        injured_at_work=injured_at_work,
        safety_signature_photo_id=signature_photo_id,
    )

    # Link the signature photo to the created time log entry
    if result["status"] == "success" and "data" in result:
        time_log_id = result["data"].id
        await link_signature_to_time_log(signature_photo_id, time_log_id)

    return result


# Get Today's Punches
@router.get("/today")
def get_todays_logs(
    session: Session = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user["uid"])
        .where(TimeLog.timestamp >= start_of_day)
        .order_by(TimeLog.timestamp)
    ).all()
    return {"status": "success", "data": punches}


# Get All Punches
@router.get("/logs")
def get_all_logs(
    session: Session = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user["uid"])
        .order_by(TimeLog.timestamp.desc())
    ).all()
    return {"status": "success", "data": punches}


# Get Last Punch
@router.get("/last-punch")
def get_last_punch(
    session: Session = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    last_punch = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user["uid"])
        .order_by(TimeLog.timestamp.desc())
    ).first()

    if not last_punch:
        return {"status": "success", "data": None, "message": "No punches found."}

    return {"status": "success", "data": last_punch}


@router.post("/request-clock-edit", response_model=ClockRequestLog)
def request_clock_edit(
    payload: ClockEditRequestPayload,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    # Validate original clock-in punch
    original_clock_in = session.get(TimeLog, payload.original_clock_in_timelog_id)
    if not original_clock_in:
        raise HTTPException(
            status_code=404,
            detail=f"Original clock-in punch with ID {payload.original_clock_in_timelog_id} not found.",
        )
    if original_clock_in.employee_id != current_user["uid"]:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to edit clock-in punch ID {payload.original_clock_in_timelog_id}.",
        )
    if original_clock_in.punch_type != PunchType.CLOCK_IN:
        raise HTTPException(
            status_code=400,
            detail=f"Punch ID {payload.original_clock_in_timelog_id} is not a clock-in punch.",
        )

    # Validate original clock-out punch
    original_clock_out = session.get(TimeLog, payload.original_clock_out_timelog_id)
    if not original_clock_out:
        raise HTTPException(
            status_code=404,
            detail=f"Original clock-out punch with ID {payload.original_clock_out_timelog_id} not found.",
        )
    if original_clock_out.employee_id != current_user["uid"]:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to edit clock-out punch ID {payload.original_clock_out_timelog_id}.",
        )
    if original_clock_out.punch_type != PunchType.CLOCK_OUT:
        raise HTTPException(
            status_code=400,
            detail=f"Punch ID {payload.original_clock_out_timelog_id} is not a clock-out punch.",
        )

    # Optional: Add check to ensure clock_out is after clock_in and they form a reasonable pair
    if original_clock_out.timestamp <= original_clock_in.timestamp:
        raise HTTPException(
            status_code=400,
            detail="Original clock-out time must be after original clock-in time.",
        )
    # Optional: Check if dealership_id matches for both original punches, if relevant
    # if original_clock_in.dealership_id != original_clock_out.dealership_id:
    #     raise HTTPException(status_code=400, detail="Original punches are from different dealerships.")

    new_request = ClockRequestLog(
        employee_id=current_user["uid"],
        request_type=RequestTypeEnum.EDIT,
        original_clock_in_timelog_id=payload.original_clock_in_timelog_id,
        original_clock_out_timelog_id=payload.original_clock_out_timelog_id,
        day_of_punch=payload.day_of_punch,
        requested_start_time_str=payload.requested_start_time_str,
        requested_end_time_str=payload.requested_end_time_str,
        dealership_id=payload.dealership_id,
        reason=payload.reason,
        status=RequestStatusEnum.PENDING,
        requested_at=datetime.now(timezone.utc),
    )

    session.add(new_request)
    session.commit()
    session.refresh(new_request)

    return new_request


@router.post("/request-clock-creation", response_model=ClockRequestLog)
def request_clock_creation(
    payload: ClockCreateRequestPayload,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    new_request = ClockRequestLog(
        employee_id=current_user["uid"],
        request_type=RequestTypeEnum.CREATION,
        day_of_punch=payload.day_of_punch,
        requested_start_time_str=payload.requested_start_time_str,
        requested_end_time_str=payload.requested_end_time_str,
        dealership_id=payload.dealership_id,
        reason=payload.reason,
        status=RequestStatusEnum.PENDING,
        requested_at=datetime.now(timezone.utc),
    )

    session.add(new_request)
    session.commit()
    session.refresh(new_request)

    return new_request


@router.get("/my-clock-requests", response_model=List[ClockRequestLog])
def get_my_clock_requests(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    limit: int = 10,  # Default limit to 5, can be overridden by query parameter e.g. /my-clock-requests?limit=10
):
    """
    Retrieves the most recent clock edit or creation requests made by the authenticated user.
    """
    requests = session.exec(
        select(ClockRequestLog)
        .where(ClockRequestLog.employee_id == current_user["uid"])
        .order_by(ClockRequestLog.requested_at.desc())  # Get newest first
        .limit(limit)  # Limit the number of results
    ).all()

    return requests
