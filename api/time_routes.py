from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from datetime import datetime, timezone
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


# Get Todays Logs
@router.get("/today")
def get_todays_logs(employee_id: str, session=Depends(get_session)):
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= start_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    return {"status": "success", "data": punches}


# Get All Logs
@router.get("/logs")
def get_all_logs(employee_id: str, session: Session = Depends(get_session)):
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .order_by(TimeLog.timestamp.desc())
    ).all()
    return {"status": "success", "data": punches}


# Get Most Recent Punch
@router.get("/last-punch")
def get_last_punch(employee_id: str, session: Session = Depends(get_session)):
    last_punch = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .order_by(TimeLog.timestamp.desc())
    ).first()

    if not last_punch:
        return {"status": "success", "data": None, "message": "No punches found."}

    return {"status": "success", "data": last_punch}
