from fastapi import APIRouter, Depends
from sqlmodel import Session
from datetime import datetime
from models.time_log import PunchType, TimeLog
from db.session import get_session

router = APIRouter()

@router.post("/clock-in")
def clock_in(employee_id: str, latitude: float = None, longitude: float = None, session: Session = Depends(get_session)):
    return save_punch(employee_id, PunchType.CLOCK_IN, latitude, longitude, session)

@router.post("/clock-out")
def clock_out(employee_id: str, latitude: float = None, longitude: float = None, session: Session = Depends(get_session)):
    return save_punch(employee_id, PunchType.CLOCK_OUT, latitude, longitude, session)

def save_punch(employee_id: str, punch_type: PunchType, latitude: float, longitude: float, session: Session):
    punch = TimeLog(
        employee_id=employee_id,
        punch_type=punch_type,
        latitude=latitude,
        longitude=longitude,
        timestamp=datetime.utcnow()
    )
    session.add(punch)
    session.commit()
    session.refresh(punch)
    return {"status": "success", "data": punch}
