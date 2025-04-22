from sqlmodel import SQLModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime

class PunchType(str, Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"

class TimeLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    punch_type: PunchType
    latitude: Optional[float] = None
    longitude: Optional[float] = None