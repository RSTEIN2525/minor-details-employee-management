from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, date, time
from typing import Optional
from enum import Enum

class ShiftStatus(str, Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed" 
    CANCELLED = "cancelled"
    COMPLETED = "completed"

class EmployeeScheduledShift(SQLModel, table=True):
    """
    Model for scheduled employee shifts in the drag-and-drop scheduling system
    """
    __tablename__ = "employee_scheduled_shifts"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Employee and dealership assignment
    employee_id: str = Field(index=True)  # Firebase user ID
    employee_name: str = Field(index=True)  # Cached name for quick access
    dealership_id: str = Field(index=True)
    dealership_name: str = Field(index=True)  # Cached name for quick access
    
    # Shift timing
    shift_date: date = Field(index=True)
    start_time: time
    end_time: time
    
    # Shift details
    status: ShiftStatus = Field(default=ShiftStatus.SCHEDULED)
    estimated_hours: float = Field(default=0.0)  # Calculated duration
    break_minutes: int = Field(default=30)  # Default break time
    
    # Administrative
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str  # Admin user who created the schedule
    updated_at: Optional[datetime] = Field(default=None)
    updated_by: Optional[str] = Field(default=None)
    
    # Notes and special instructions
    notes: Optional[str] = Field(default=None)
    special_instructions: Optional[str] = Field(default=None)
    
    # Tracking
    is_overtime_shift: bool = Field(default=False)  # Flag if this puts employee in OT
    weekly_hours_before_shift: float = Field(default=0.0)  # Hours before this shift
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            time: lambda v: v.isoformat()
        } 