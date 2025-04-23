from fastapi import APIRouter, Depends
from sqlmodel import Session
from datetime import datetime
from models.time_log import PunchType, TimeLog, PunchRequest
from db.session import get_session
from services.punch_service import PunchService

# Defines API Endpoints For Employee Front-Facing UI/UX Clock Ins

# Collection of Endpoints
router = APIRouter()


# Clock In Endpoint
@router.post("/clock-in")
def clock_in(data: PunchRequest, session: Session = Depends(get_session)):
    return PunchService.validate_and_save(
        employee_id=data.employee_id,
        punch_type=PunchType.CLOCK_IN,
        latitude=data.latitude,
        longitude=data.longitude,
        session=session,
    )


# Clock Out Endpoint
@router.post("/clock-out")
def clock_out(data: PunchRequest, session: Session = Depends(get_session)):
    return PunchService.validate_and_save(
        employee_id=data.employee_id,
        punch_type=PunchType.CLOCK_OUT,
        latitude=data.latitude,
        longitude=data.longitude,
        session=session,
    )
