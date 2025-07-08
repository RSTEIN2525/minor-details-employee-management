from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_serializer
from sqlmodel import Session, select

from core.deps import require_admin_role
from db.session import get_session
from models.time_log import PunchType, TimeLog
from utils.datetime_helpers import format_utc_datetime

router = APIRouter()

# --- Response Models ---


class InjuryReportEntry(BaseModel):
    id: int
    employee_id: str
    dealership_id: str
    timestamp: datetime
    injured_at_work: bool
    safety_signature_photo_id: Optional[int] = None
    admin_notes: Optional[str] = None
    admin_modifier_id: Optional[str] = None

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


class InjuryReportSummary(BaseModel):
    total_clockouts: int
    total_injuries: int
    injury_rate: float  # percentage
    reports: List[InjuryReportEntry]


# --- API Endpoints ---


@router.get("/reports", response_model=InjuryReportSummary)
def get_injury_reports(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    start_date: Optional[date] = Query(
        None, description="Start date for report (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None, description="End date for report (YYYY-MM-DD)"
    ),
    dealership_id: Optional[str] = Query(
        None, description="Filter by specific dealership"
    ),
    employee_id: Optional[str] = Query(None, description="Filter by specific employee"),
    injured_only: bool = Query(False, description="Show only injury reports"),
    limit: int = Query(100, description="Maximum number of records to return"),
    offset: int = Query(0, description="Number of records to skip"),
):
    """
    Get injury reports with optional filtering.
    Returns all clockout entries with injury reporting data.
    """

    # Build the query
    query = select(TimeLog).where(
        TimeLog.punch_type == PunchType.CLOCK_OUT,
        TimeLog.injured_at_work.is_not(None),  # Only entries with injury data
    )

    # Apply filters
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        query = query.where(TimeLog.timestamp >= start_datetime)

    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time()).replace(
            tzinfo=timezone.utc
        )
        query = query.where(TimeLog.timestamp <= end_datetime)

    if dealership_id:
        query = query.where(TimeLog.dealership_id == dealership_id)

    if employee_id:
        query = query.where(TimeLog.employee_id == employee_id)

    if injured_only:
        query = query.where(TimeLog.injured_at_work == True)

    # Get total count for the filtered query (without limit/offset)
    total_query = query
    total_clockouts = len(session.exec(total_query).all())

    # Get injury count
    injury_query = query.where(TimeLog.injured_at_work == True)
    total_injuries = len(session.exec(injury_query).all())

    # Calculate injury rate
    injury_rate = (
        (total_injuries / total_clockouts * 100) if total_clockouts > 0 else 0.0
    )

    # Apply pagination and ordering
    query = query.order_by(TimeLog.timestamp.desc()).offset(offset).limit(limit)

    # Execute the query
    reports = session.exec(query).all()

    # Convert to response model
    report_entries = [
        InjuryReportEntry(
            id=report.id,
            employee_id=report.employee_id,
            dealership_id=report.dealership_id,
            timestamp=report.timestamp,
            injured_at_work=report.injured_at_work,
            safety_signature_photo_id=report.safety_signature_photo_id,
            admin_notes=report.admin_notes,
            admin_modifier_id=report.admin_modifier_id,
        )
        for report in reports
    ]

    return InjuryReportSummary(
        total_clockouts=total_clockouts,
        total_injuries=total_injuries,
        injury_rate=round(injury_rate, 2),
        reports=report_entries,
    )


@router.get("/employee/{employee_id}/reports", response_model=List[InjuryReportEntry])
def get_employee_injury_reports(
    employee_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: int = Query(50, description="Maximum number of records to return"),
):
    """Get injury reports for a specific employee."""

    reports = session.exec(
        select(TimeLog)
        .where(
            TimeLog.employee_id == employee_id,
            TimeLog.punch_type == PunchType.CLOCK_OUT,
            TimeLog.injured_at_work.is_not(None),
        )
        .order_by(TimeLog.timestamp.desc())
        .limit(limit)
    ).all()

    return [
        InjuryReportEntry(
            id=report.id,
            employee_id=report.employee_id,
            dealership_id=report.dealership_id,
            timestamp=report.timestamp,
            injured_at_work=report.injured_at_work,
            safety_signature_photo_id=report.safety_signature_photo_id,
            admin_notes=report.admin_notes,
            admin_modifier_id=report.admin_modifier_id,
        )
        for report in reports
    ]


@router.get("/dealership/{dealership_id}/summary")
def get_dealership_injury_summary(
    dealership_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    days: int = Query(30, description="Number of days to look back"),
):
    """Get injury summary for a specific dealership over the last N days."""

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = (
        end_date.replace(day=end_date.day - days)
        if end_date.day > days
        else end_date.replace(month=end_date.month - 1, day=end_date.day + (31 - days))
    )

    # Get all clockouts with injury data
    clockouts = session.exec(
        select(TimeLog).where(
            TimeLog.dealership_id == dealership_id,
            TimeLog.punch_type == PunchType.CLOCK_OUT,
            TimeLog.injured_at_work.is_not(None),
            TimeLog.timestamp >= start_date,
            TimeLog.timestamp <= end_date,
        )
    ).all()

    total_clockouts = len(clockouts)
    injuries = [c for c in clockouts if c.injured_at_work]
    total_injuries = len(injuries)

    injury_rate = (
        (total_injuries / total_clockouts * 100) if total_clockouts > 0 else 0.0
    )

    return {
        "dealership_id": dealership_id,
        "period_days": days,
        "total_clockouts": total_clockouts,
        "total_injuries": total_injuries,
        "injury_rate": round(injury_rate, 2),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
