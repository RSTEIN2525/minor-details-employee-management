from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

class AdminTimeChangeAction(str, Enum):
    CREATE = "CREATE"
    EDIT = "EDIT"
    DELETE = "DELETE"

class AdminTimeChange(SQLModel, table=True):
    __tablename__ = "admin_time_changes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Admin who made the change
    admin_id: str = Field(index=True)
    
    # Employee affected
    employee_id: str = Field(index=True)
    
    # What action was taken
    action: AdminTimeChangeAction = Field(index=True)
    
    # Reason provided by admin
    reason: str
    
    # When the change was made
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    # For CREATE: the new clock-in/out pair IDs
    # For EDIT: the modified clock-in/out pair IDs  
    # For DELETE: the deleted clock-in/out pair IDs
    clock_in_id: Optional[int] = None
    clock_out_id: Optional[int] = None
    
    # Dealership
    dealership_id: str
    
    # For CREATE and EDIT actions - the new/current times
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # For EDIT actions only - the original times before edit
    original_start_time: Optional[datetime] = None
    original_end_time: Optional[datetime] = None
    
    # For dealership changes
    original_dealership_id: Optional[str] = Field(default=None)
    
    # Date of the punch being affected
    punch_date: Optional[str] = None  # YYYY-MM-DD format 