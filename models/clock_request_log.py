from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone, date
from enum import Enum
from pydantic import field_serializer
from utils.datetime_helpers import format_utc_datetime

class RequestTypeEnum(str, Enum):
    EDIT = "edit"
    CREATION = "creation"

class RequestStatusEnum(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class ClockRequestLog(SQLModel, table=True):
    __tablename__ = "clock_request_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: str = Field(index=True)
    request_type: RequestTypeEnum
    
    original_clock_in_timelog_id: Optional[int] = Field(default=None, foreign_key="time_log.id", nullable=True)
    original_clock_out_timelog_id: Optional[int] = Field(default=None, foreign_key="time_log.id", nullable=True)

    day_of_punch: date 

    requested_start_time_str: str # e.g., "09:00"
    requested_end_time_str: str   # e.g., "17:00"

    dealership_id: str
    reason: str
    
    status: RequestStatusEnum = Field(default=RequestStatusEnum.PENDING)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    reviewed_by_admin_id: Optional[str] = Field(default=None, index=True)
    reviewed_at: Optional[datetime] = Field(default=None)
    admin_notes: Optional[str] = Field(default=None)

    @field_serializer('requested_at', 'reviewed_at')
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt) 