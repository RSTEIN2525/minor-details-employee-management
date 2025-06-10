from sqlmodel import SQLModel, Field, Index
from typing import Optional
from enum import Enum
from datetime import datetime, timezone
from datetime import date as Date
from pydantic import field_serializer
from utils.datetime_helpers import format_utc_datetime

class VacationTimeType(str, Enum):
    VACATION = "vacation"
    SICK_LEAVE = "sick_leave"
    PERSONAL_TIME = "personal_time"
    BEREAVEMENT = "bereavement"
    JURY_DUTY = "jury_duty"
    HOLIDAY = "holiday"

class VacationTime(SQLModel, table=True):
    __tablename__ = "vacation_time"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: str = Field(index=True)
    dealership_id: str = Field(index=True)
    
    # Date the vacation applies to
    date: Date = Field(index=True)
    
    # Number of hours for this vacation day
    hours: float = Field(gt=0)  # Must be positive
    
    # Type of time off
    vacation_type: VacationTimeType = Field(default=VacationTimeType.VACATION)
    
    # Admin who granted the vacation
    granted_by_admin_id: str = Field(index=True)
    
    # Notes/reason for the vacation
    notes: Optional[str] = None
    
    # When this vacation entry was created
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Optional: When vacation was last modified
    updated_at: Optional[datetime] = None
    
    @field_serializer('created_at', 'updated_at')
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt) 