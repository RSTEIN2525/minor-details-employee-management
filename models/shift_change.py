from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone, date
from enum import Enum

class ShiftChangeType(str, Enum):
    SCHEDULE_CHANGE = "schedule_change"  # Change scheduled hours
    LOCATION_CHANGE = "location_change"  # Change dealership/location
    SHIFT_SWAP = "shift_swap"           # Swap shifts between employees
    OVERTIME_ASSIGNMENT = "overtime_assignment"  # Assign overtime
    TIME_OFF_ADJUSTMENT = "time_off_adjustment"  # Adjust time off

class ShiftChange(SQLModel, table=True):
    __tablename__ = "shift_changes"

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Employee affected by the change
    employee_id: str = Field(index=True)
    
    # Owner who created the change
    created_by_owner_id: str = Field(index=True)
    
    # Type of shift change
    change_type: ShiftChangeType
    
    # Date the change applies to
    effective_date: date
    
    # Original shift details (if applicable)
    original_start_time: Optional[str] = Field(default=None)  # e.g., "09:00"
    original_end_time: Optional[str] = Field(default=None)    # e.g., "17:00"
    original_dealership_id: Optional[str] = Field(default=None)
    
    # New shift details
    new_start_time: Optional[str] = Field(default=None)       # e.g., "10:00"
    new_end_time: Optional[str] = Field(default=None)         # e.g., "18:00"
    new_dealership_id: Optional[str] = Field(default=None)
    
    # Additional details
    reason: str  # Reason for the change
    notes: Optional[str] = Field(default=None)  # Additional notes
    
    # For shift swaps - the other employee involved
    swap_with_employee_id: Optional[str] = Field(default=None, index=True)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Auto-approved since only owners can create
    status: str = Field(default="approved")  # Always approved for owner-created changes
    
    # Notification status
    employee_notified: bool = Field(default=False)
    employee_viewed_at: Optional[datetime] = Field(default=None) 