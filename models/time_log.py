from sqlmodel import SQLModel, Field, Index
from typing import Optional
from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel

# Defines the Structure of Data for a Clock in Call
class PunchRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    
# Enum Limiting Punch Type to Just Two Vals
class PunchType(str, Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"

# Defines a Table "Time_Log" w/ Cols emp_id, punch_type, timestamp, ...
class TimeLog(SQLModel, table=True):
    __tablename__ = "time_log"
    
    # Define indexes for frequently queried columns
    __table_args__ = (
        # Index for queries filtering by employee_id
        Index("ix_time_log_employee_id", "employee_id"),
        
        # Index for queries filtering by timestamp
        Index("ix_time_log_timestamp", "timestamp"),
        
        # Composite index for queries filtering by both employee_id and timestamp
        # This is our most common query pattern in analytics
        Index("ix_time_log_employee_id_timestamp", "employee_id", "timestamp"),
        
        # Index for dealership queries
        Index("ix_time_log_dealership_id", "dealership_id"),
        
        # Composite index for dealership + timestamp queries
        Index("ix_time_log_dealership_id_timestamp", "dealership_id", "timestamp"),
        
        # Index for punch type filtering
        Index("ix_time_log_punch_type", "punch_type"),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: str
    dealership_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    punch_type: PunchType
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    admin_notes: Optional[str] = Field(default=None)
    admin_modifier_id: Optional[str] = Field(default=None)
