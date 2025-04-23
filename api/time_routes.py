from fastapi import APIRouter, Depends
from sqlmodel import Session
from datetime import datetime
from models.time_log import PunchType, TimeLog
from db.session import get_session

# Defines API Endpoints For Employee Front-Facing UI/UX Clock Ins

# Collection of Endpoints
router = APIRouter()


# Clock In Endpoint
@router.post("/clock-in")
def clock_in(
    employee_id: str,
    latitude: float = None,
    longitude: float = None,
    session: Session = Depends(get_session),
):
    return save_punch(employee_id, PunchType.CLOCK_IN, latitude, longitude, session)


# Clock Out Endpoint
@router.post("/clock-out")
def clock_out(
    employee_id: str,
    latitude: float = None,
    longitude: float = None,
    session: Session = Depends(get_session),
):
    return save_punch(employee_id, PunchType.CLOCK_OUT, latitude, longitude, session)


# Processes Requests from /clock-in /clock-out endpoints
def save_punch(
    employee_id: str,
    punch_type: PunchType,
    latitude: float,
    longitude: float,
    session: Session,
):

    # Creates a TimeLog Object w/ Data From Endpoint Defined In models/TimeLog
    punch = TimeLog(
        employee_id=employee_id,
        punch_type=punch_type,
        latitude=latitude,
        longitude=longitude,
        timestamp=datetime.utcnow(),
    )

    # Append New Punch to List of Changes
    session.add(punch)

    # Commits Changse to DB
    session.commit()

    # Refereshes Object W/ Auto Generated Fields
    session.refresh(punch)

    # JSON Response back to Call
    return {"status": "success", "data": punch}
