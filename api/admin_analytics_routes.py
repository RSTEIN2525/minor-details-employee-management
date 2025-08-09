from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_serializer
from sqlmodel import Session, func, select

from core.deps import (
    get_current_user,
    require_admin_or_supervisor_role,
    require_admin_role,
)
from core.firebase import db as firestore_db
from db.session import get_session
from models.shop import Shop
from models.time_log import PunchType, TimeLog
from models.vacation_time import VacationTime
from utils.breaks import apply_unpaid_break, calculate_daily_hours_with_breaks
from utils.datetime_helpers import format_utc_datetime

router = APIRouter()

# --- Pydantic Models for Responses ---


class DealershipLaborSpend(BaseModel):
    dealership_id: str
    total_labor_spend: float
    total_hours: float


class HourlyLaborSpend(BaseModel):
    hour: int  # 0-23
    total_labor_spend: float
    total_employees: int


# Enhanced models for the new detailed daily labor endpoint
class EnhancedDealershipBreakdown(BaseModel):
    dealership_id: str
    dealership_name: Optional[str] = None
    total_labor_spend: float
    total_hours: float
    employee_count: int


class EnhancedDailyLaborSummary(BaseModel):
    target_date: str
    total_labor_spend: float
    total_hours: float
    dealership_breakdown: List[EnhancedDealershipBreakdown]
    hourly_breakdown: List[HourlyLaborSpend]


class DailyLaborSummary(BaseModel):
    date: str
    total_labor_spend: float
    total_hours: float
    hourly_breakdown: List[HourlyLaborSpend]
    dealership_breakdown: List[DealershipLaborSpend]


class EmployeeShiftInfo(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    dealership_id: str
    hourly_wage: Optional[float] = None
    shift_start_time: datetime
    current_shift_duration_hours: float
    weekly_hours_worked: float
    is_overtime: bool = False

    @field_serializer("shift_start_time")
    def serialize_shift_start_time(self, dt: datetime) -> str:
        """Ensure shift_start_time is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


class DealershipEmployeeStatus(BaseModel):
    dealership_id: str
    active_employees: List[EmployeeShiftInfo]
    active_employee_count: int
    total_current_hourly_rate: float
    total_labor_spend_today: float


# --- New Employee Detail Models and Endpoints ---


class EmployeeClockEntry(BaseModel):
    id: int
    timestamp: datetime
    punch_type: PunchType
    dealership_id: str

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


class WeekSummary(BaseModel):
    week_start_date: str
    week_end_date: str
    total_hours: float
    regular_hours: float
    overtime_hours: float
    total_pay: float
    vacation_hours: float = 0.0
    is_current_week: bool


class TodaysSummary(BaseModel):
    date: str
    total_hours: float
    regular_hours: float
    overtime_hours: float
    total_pay: float
    vacation_hours: float = 0.0
    is_currently_clocked_in: bool


class EmployeeDetailResponse(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    hourly_wage: float
    recent_clocks: List[EmployeeClockEntry]
    week_summaries: List[WeekSummary]
    todays_summary: TodaysSummary
    two_week_total_pay: float

    # Aggregated totals for the entire requested date range
    date_range_total_hours: Optional[float] = None
    date_range_regular_hours: Optional[float] = None
    date_range_overtime_hours: Optional[float] = None
    date_range_total_pay: Optional[float] = None


# New model for dealership employee hours breakdown
class EmployeeHoursBreakdown(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    hourly_wage: Optional[float] = None
    total_hours: float
    regular_hours: float
    overtime_hours: float
    estimated_pay: float
    is_currently_active: bool


class DealershipEmployeeHoursResponse(BaseModel):
    dealership_id: str
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    employees: List[EmployeeHoursBreakdown]
    summary: Dict[str, float]  # totals for all employees combined


# Comprehensive Labor Spend Models
class EmployeeLaborDetail(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    hourly_wage: Optional[float] = None

    # Current status
    is_currently_active: bool = False
    current_shift_start_time: Optional[datetime] = None
    current_shift_duration_hours: float = 0.0

    # Today's work
    todays_total_hours: float = 0.0
    todays_regular_hours: float = 0.0
    todays_overtime_hours: float = 0.0
    todays_labor_cost: float = 0.0
    todays_vacation_hours: float = 0.0
    todays_vacation_cost: float = 0.0
    todays_total_cost: float = 0.0  # work + vacation

    # Weekly aggregates
    weekly_total_hours: float = 0.0
    weekly_regular_hours: float = 0.0
    weekly_overtime_hours: float = 0.0
    weekly_labor_cost: float = 0.0

    # Today's clock info
    todays_clock_in_count: int = 0
    todays_first_clock_in: Optional[datetime] = None
    todays_last_clock_out: Optional[datetime] = None

    @field_serializer(
        "current_shift_start_time", "todays_first_clock_in", "todays_last_clock_out"
    )
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt)


class DealershipLaborSpendSummary(BaseModel):
    # Basic info
    dealership_id: str
    analysis_date: str  # ISO date string
    analysis_timestamp: datetime

    # Employee counts
    total_employees: int = 0
    active_employees_today: int = 0
    employees_who_clocked_in_today: int = 0
    employees_currently_clocked_in: int = 0

    # Today's labor costs
    todays_total_work_hours: float = 0.0
    todays_total_vacation_hours: float = 0.0
    todays_total_combined_hours: float = 0.0
    todays_total_work_cost: float = 0.0
    todays_total_vacation_cost: float = 0.0
    todays_total_labor_cost: float = 0.0  # work + vacation

    # Today's time breakdown
    todays_regular_hours: float = 0.0
    todays_overtime_hours: float = 0.0
    todays_regular_cost: float = 0.0
    todays_overtime_cost: float = 0.0

    # Current rates
    current_hourly_labor_rate: float = 0.0  # Sum of all active employees' wages
    average_hourly_wage: float = 0.0  # Average across all employees
    weighted_average_hourly_rate: float = 0.0  # Weighted by hours worked

    # Weekly aggregates (current week)
    weekly_total_hours: float = 0.0
    weekly_regular_hours: float = 0.0
    weekly_overtime_hours: float = 0.0
    weekly_total_cost: float = 0.0

    # Clock activity
    total_clock_ins_today: int = 0
    total_clock_outs_today: int = 0

    # Cost efficiency metrics
    cost_per_employee_today: float = 0.0
    hours_per_employee_today: float = 0.0

    @field_serializer("analysis_timestamp")
    def serialize_analysis_timestamp(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


class ComprehensiveLaborSpendResponse(BaseModel):
    summary: DealershipLaborSpendSummary
    employees: List[EmployeeLaborDetail]

    # Additional insights
    top_earners_today: List[EmployeeLaborDetail] = []  # Top 5 by cost
    most_hours_today: List[EmployeeLaborDetail] = []  # Top 5 by hours

    # Data freshness
    data_generated_at: datetime

    @field_serializer("data_generated_at")
    def serialize_data_generated_at(self, dt: datetime) -> str:
        """Ensure data_generated_at is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


class AllDealershipsComprehensiveLaborSpendResponse(BaseModel):
    """Response model for comprehensive labor spend data for ALL dealerships"""

    analysis_date: str  # ISO date string
    analysis_timestamp: datetime
    total_company_labor_cost: float
    total_company_employees: int
    dealerships: List[ComprehensiveLaborSpendResponse]

    @field_serializer("analysis_timestamp")
    def serialize_analysis_timestamp(self, dt: datetime) -> str:
        """Ensure analysis_timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


# Flexible Date Range Labor Spend Models
class FlexibleDateRangeSummary(BaseModel):
    """Date range summary for flexible labor spend analysis"""

    # Date range info
    start_date: str  # ISO date string
    end_date: str  # ISO date string
    analysis_timestamp: datetime

    # Employee counts
    total_employees: int = 0
    active_employees_in_range: int = 0

    # Labor costs for the date range
    total_work_hours: float = 0.0
    total_vacation_hours: float = 0.0
    total_combined_hours: float = 0.0
    total_work_cost: float = 0.0
    total_vacation_cost: float = 0.0
    total_labor_cost: float = 0.0  # work + vacation

    # Time breakdown
    total_regular_hours: float = 0.0
    total_overtime_hours: float = 0.0
    total_regular_cost: float = 0.0
    total_overtime_cost: float = 0.0

    # Rates and averages
    average_hourly_wage: float = 0.0
    weighted_average_hourly_rate: float = 0.0
    cost_per_employee: float = 0.0
    hours_per_employee: float = 0.0

    @field_serializer("analysis_timestamp")
    def serialize_analysis_timestamp(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


class FlexibleEmployeeLaborDetail(BaseModel):
    """Employee labor details for flexible date range analysis"""

    employee_id: str
    employee_name: Optional[str] = None
    hourly_wage: Optional[float] = None

    # Date range work
    total_hours: float = 0.0
    regular_hours: float = 0.0
    overtime_hours: float = 0.0
    labor_cost: float = 0.0
    vacation_hours: float = 0.0
    vacation_cost: float = 0.0
    total_cost: float = 0.0  # work + vacation

    # Clock activity in range
    total_clock_ins: int = 0
    first_clock_in: Optional[datetime] = None
    last_clock_out: Optional[datetime] = None

    @field_serializer("first_clock_in", "last_clock_out")
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt)


class FlexibleEmployeeDailyDetail(BaseModel):
    """Daily hours and pay breakdown for an employee"""

    date: str  # ISO date string (YYYY-MM-DD)
    hours: float = 0.0
    regular_hours: float = 0.0
    overtime_hours: float = 0.0
    vacation_hours: float = 0.0

    pay: float = 0.0
    regular_pay: float = 0.0
    overtime_pay: float = 0.0
    vacation_pay: float = 0.0
    total_pay: float = 0.0  # work + vacation

    clock_ins: int = 0
    first_clock_in: Optional[datetime] = None
    last_clock_out: Optional[datetime] = None

    @field_serializer("first_clock_in", "last_clock_out")
    def serialize_timestamps(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        return format_utc_datetime(dt)


class FlexibleEmployeeLaborDetailWithDaily(FlexibleEmployeeLaborDetail):
    """Extended employee labor details with daily breakdown"""

    daily_breakdown: Optional[List["DailyLaborBreakdown"]] = None


class FlexibleDealershipLaborSpendResponse(BaseModel):
    """Flexible dealership labor spend response for date range analysis"""

    dealership_id: str
    summary: FlexibleDateRangeSummary
    employees: List[FlexibleEmployeeLaborDetail]
    top_earners: List[FlexibleEmployeeLaborDetail]
    most_hours: List[FlexibleEmployeeLaborDetail]
    daily_breakdown: Optional[List["DailyLaborBreakdown"]] = None


class FlexibleLaborSpendResponse(BaseModel):
    """Response model for flexible labor spend data with date range and dealership filtering"""

    start_date: str  # ISO date string
    end_date: str  # ISO date string
    analysis_timestamp: datetime
    dealership_ids: List[str]  # List of requested dealerships
    total_company_labor_cost: float
    total_company_employees: int
    dealerships: List[FlexibleDealershipLaborSpendResponse]

    @field_serializer("analysis_timestamp")
    def serialize_analysis_timestamp(self, dt: datetime) -> str:
        """Ensure analysis_timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


# Quick Preview Labor Spend Models
class QuickLaborPreview(BaseModel):
    dealership_id: str
    current_time: datetime

    # Today's spending so far
    total_labor_cost_today: float = 0.0
    total_work_cost_today: float = 0.0
    total_vacation_cost_today: float = 0.0

    # Hours so far today
    total_hours_today: float = 0.0
    total_work_hours_today: float = 0.0
    total_vacation_hours_today: float = 0.0

    # Current activity
    employees_currently_clocked_in: int = 0
    employees_who_worked_today: int = 0
    current_hourly_burn_rate: float = (
        0.0  # Sum of wages of currently clocked in employees
    )

    # Quick stats
    average_cost_per_employee_today: float = 0.0
    projected_daily_cost: float = 0.0  # Based on current burn rate

    @field_serializer("current_time")
    def serialize_current_time(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


# All Dealerships Labor Cost Model
class DealershipLaborCost(BaseModel):
    dealership_id: str
    total_labor_cost_today: float


class AllDealershipsLaborCostResponse(BaseModel):
    analysis_date: str  # ISO date string
    total_company_labor_cost: float
    dealerships: List[DealershipLaborCost]
    analysis_time: datetime

    @field_serializer("analysis_time")
    def serialize_analysis_time(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)


# --- Helper Functions ---


async def get_user_details(user_id: str) -> Dict[str, Any]:
    """Fetch user details from Firestore."""
    user_ref = firestore_db.collection("users").document(user_id)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()
        return {
            "id": user_id,
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": user_data.get("hourlyWage", 0.0),
        }
    return {"id": user_id, "name": "Unknown", "hourly_wage": 0.0}


def calculate_regular_and_overtime_hours(total_hours: float) -> Tuple[float, float]:
    """Calculate regular and overtime hours based on total hours worked."""
    if total_hours <= 40.0:
        return total_hours, 0.0
    else:
        return 40.0, total_hours - 40.0


def calculate_pay_with_overtime(
    regular_hours: float, overtime_hours: float, hourly_wage: float
) -> float:
    """Calculate total pay including overtime rate (1.5x) for overtime hours."""
    regular_pay = regular_hours * hourly_wage
    overtime_pay = overtime_hours * hourly_wage * 1.5
    return regular_pay + overtime_pay


async def calculate_todays_hours_and_status(
    session: Session, employee_id: str
) -> Tuple[float, bool]:
    """Calculate hours worked today and current clock status for an employee."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Start and end of today in UTC
    start_of_day = datetime.combine(today, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end_of_day = datetime.combine(today, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all clock entries for today
    todays_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    total_hours = 0.0
    clock_in_time = None
    is_currently_clocked_in = False

    for clock in todays_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        if clock.punch_type == PunchType.CLOCK_IN:
            clock_in_time = ts
        elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            raw_hours = (ts - clock_in_time).total_seconds() / 3600
            paid_hours = apply_unpaid_break(raw_hours)
            total_hours += paid_hours
            clock_in_time = None

    # If still clocked in, add time until now and set status
    if clock_in_time:
        raw_hours = (now - clock_in_time).total_seconds() / 3600
        paid_hours = apply_unpaid_break(raw_hours)
        total_hours += paid_hours
        is_currently_clocked_in = True

    return total_hours, is_currently_clocked_in


async def calculate_weekly_hours(session: Session, employee_id: str) -> float:
    """Calculate total hours worked by an employee in the current week."""
    # Get start of week (Monday)
    today = datetime.now(timezone.utc).date()
    start_of_week = (
        datetime.now(timezone.utc) - timedelta(days=today.weekday())
    ).replace(hour=0, minute=0, second=0, microsecond=0)

    # Get all punches for this week
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= start_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Calculate total hours
    total_hours = 0.0
    clock_in_time: Optional[datetime] = None

    for punch in punches:
        punch_ts = punch.timestamp
        if punch_ts.tzinfo is None:
            punch_ts = punch_ts.replace(tzinfo=timezone.utc)

        if punch.punch_type == PunchType.CLOCK_IN:
            clock_in_time = punch_ts
        elif punch.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            # clock_in_time is already UTC aware from previous assignment or loop
            raw_hours = (punch_ts - clock_in_time).total_seconds() / 3600
            paid_hours = apply_unpaid_break(raw_hours)
            total_hours += paid_hours
            clock_in_time = None

    # If still clocked in, add time until now
    if clock_in_time:
        # clock_in_time is already UTC aware
        now = datetime.now(timezone.utc)
        raw_hours = (now - clock_in_time).total_seconds() / 3600
        paid_hours = apply_unpaid_break(raw_hours)
        total_hours += paid_hours

    return total_hours


async def is_employee_currently_active(
    session: Session, employee_id: str, dealership_id: Optional[str] = None
) -> Tuple[bool, Optional[datetime]]:
    """
    Determine if an employee is currently active (clocked in) by checking their most recent clock action.
    If their last clock was a CLOCK_IN, they're active. If it was a CLOCK_OUT, they're not.

    Returns:
        Tuple[bool, Optional[datetime]]: (is_active, most_recent_clock_in_time)
    """
    # Look back a reasonable amount to handle cross-day shifts
    lookback_date = datetime.now(timezone.utc) - timedelta(days=3)

    # STEP 1: Fetch the employee's single most recent clock entry across ALL dealerships.
    most_recent_overall_clock = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= lookback_date)
        .order_by(TimeLog.timestamp.desc())
        .limit(1)
    ).first()

    if not most_recent_overall_clock:
        # No recent activity at all → definitely not active
        return False, None

    # Ensure the timestamp is timezone-aware for safety
    ts = (
        most_recent_overall_clock.timestamp.replace(tzinfo=timezone.utc)
        if most_recent_overall_clock.timestamp.tzinfo is None
        else most_recent_overall_clock.timestamp
    )

    # If the caller cares about a specific dealership we must ensure the MOST RECENT clock-in
    # belongs to that dealership.  (An open shift at dealership A is implicitly closed by any
    # clock action at dealership B.)
    if dealership_id is not None:
        if (
            most_recent_overall_clock.punch_type == PunchType.CLOCK_IN
            and most_recent_overall_clock.dealership_id == dealership_id
        ):
            return True, ts
        # Otherwise the employee is either clocked out, or their open shift (if any)
        # is at a different dealership.
        return False, None

    # No dealership filter → active if the very last punch was a CLOCK_IN
    if most_recent_overall_clock.punch_type == PunchType.CLOCK_IN:
        return True, ts

    return False, None


async def calculate_vacation_hours(
    session: Session, employee_id: str, start_date: date, end_date: date
) -> float:
    """Calculate total vacation hours for an employee within a date range."""
    vacation_entries = session.exec(
        select(VacationTime)
        .where(VacationTime.employee_id == employee_id)
        .where(VacationTime.date >= start_date)
        .where(VacationTime.date <= end_date)
    ).all()

    return sum(entry.hours for entry in vacation_entries)


# --- API Endpoints ---


@router.get("/labor/daily/enhanced", response_model=EnhancedDailyLaborSummary)
async def get_enhanced_daily_labor_spend(
    target_date: date,  # Required parameter
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get enhanced daily labor spend with detailed dealership breakdown including employee counts.
    Requires a specific target date.

    Now uses the same robust calculation logic as the comprehensive endpoint:
    - Proper overtime calculation based on weekly context
    - Correct dealership assignment handling
    - Includes currently clocked-in employees
    - Applies unpaid break deductions
    """
    print(
        f"\n--- Starting enhanced daily labor spend analysis for date: {target_date} ---"
    )

    # Use Eastern timezone for date boundaries to align with business operations
    from zoneinfo import ZoneInfo

    analysis_tz = ZoneInfo("America/New_York")
    start_of_day = datetime.combine(
        target_date, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_day = datetime.combine(
        target_date, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    # Current week boundaries (Monday to Sunday) for overtime calculation
    current_week_start = target_date - timedelta(days=target_date.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    start_of_week = datetime.combine(
        current_week_start, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_week = datetime.combine(
        current_week_end, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    now = datetime.now(timezone.utc)

    print(f"Analysis period (UTC) - Day: {start_of_day} to {end_of_day}")
    print(f"Analysis period (UTC) - Week: {start_of_week} to {end_of_week}")

    # Get ALL employees from Firestore to properly handle dealership assignments
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    all_employees = {}
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id

        # Parse dealership assignments
        raw_dealerships = user_data.get("dealerships", "")
        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [
                s.strip() for s in str(raw_dealerships).split(",") if s.strip()
            ]

        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [
                s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()
            ]

        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)

        all_employees[employee_id] = {
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": (
                float(user_data.get("hourlyWage", 0.0))
                if user_data.get("hourlyWage")
                else 0.0
            ),
            "dealerships": combined_dealerships,
        }

    print(f"Found {len(all_employees)} total employees")

    if not all_employees:
        return EnhancedDailyLaborSummary(
            target_date=target_date.isoformat(),
            total_labor_spend=0.0,
            total_hours=0.0,
            dealership_breakdown=[],
            hourly_breakdown=[],
        )

    employee_ids = list(all_employees.keys())

    # Get time logs for the target day across all dealerships
    today_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(employee_ids))
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Get weekly logs for overtime calculation
    week_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(employee_ids))
        .where(TimeLog.timestamp >= start_of_week)
        .where(TimeLog.timestamp <= end_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    print(f"Found {len(today_logs)} today logs and {len(week_logs)} week logs")

    # Get dealership names from Firestore
    dealership_names = {}
    try:
        dealerships_ref = firestore_db.collection("dealerships").stream()
        for doc in dealerships_ref:
            dealership_data = doc.to_dict()
            dealership_names[doc.id] = dealership_data.get("name", doc.id)
    except Exception as e:
        print(f"Warning: Could not fetch dealership names: {e}")

    # Process by dealership
    dealership_breakdowns = []
    hourly_breakdown = defaultdict(lambda: {"spend": 0.0, "employees": set()})
    total_labor_spend = 0.0
    total_hours = 0.0

    # Get unique dealerships from logs
    dealerships_with_activity = set()
    for log in today_logs:
        dealerships_with_activity.add(log.dealership_id)

    for dealership_id in dealerships_with_activity:
        print(f"Processing dealership: {dealership_id}")

        dealership_labor_spend = 0.0
        dealership_hours = 0.0
        employees_with_activity = set()

        # Get employees assigned to this dealership
        dealership_employees = [
            emp_id
            for emp_id, emp_data in all_employees.items()
            if dealership_id in emp_data["dealerships"]
        ]

        for employee_id in dealership_employees:
            try:
                employee_data = all_employees[employee_id]
                hourly_wage = employee_data["hourly_wage"]

                # Get this employee's logs for today and this week
                employee_today_logs = [
                    log for log in today_logs if log.employee_id == employee_id
                ]
                employee_week_logs = [
                    log for log in week_logs if log.employee_id == employee_id
                ]

                if not employee_today_logs:
                    continue

                employees_with_activity.add(employee_id)

                # Calculate hours worked this week BEFORE today for overtime context
                week_logs_before_today = []
                for log in employee_week_logs:
                    log_ts = log.timestamp
                    if log_ts.tzinfo is None:
                        log_ts = log_ts.replace(tzinfo=timezone.utc)
                    if log_ts < start_of_day:
                        week_logs_before_today.append(log)

                hours_worked_before_today = calculate_hours_from_logs(
                    week_logs_before_today, start_of_day
                )

                # Calculate today's hours for this dealership
                todays_hours = calculate_hours_by_dealership_from_logs(
                    employee_today_logs, dealership_id, now
                )

                if todays_hours <= 0:
                    continue

                # Calculate regular vs overtime hours based on weekly context
                if hours_worked_before_today >= 40.0:
                    # All of today's hours are overtime
                    regular_hours = 0.0
                    overtime_hours = todays_hours
                else:
                    # Some may be regular, some overtime
                    remaining_regular_hours = 40.0 - hours_worked_before_today
                    regular_hours = min(todays_hours, remaining_regular_hours)
                    overtime_hours = max(0.0, todays_hours - remaining_regular_hours)

                # Calculate cost with proper overtime pay
                labor_cost = calculate_pay_with_overtime(
                    regular_hours, overtime_hours, hourly_wage
                )

                dealership_labor_spend += labor_cost
                dealership_hours += todays_hours

                # Add to hourly breakdown
                # Find first and last clock times for this employee at this dealership today
                dealership_logs_today = [
                    log
                    for log in employee_today_logs
                    if log.dealership_id == dealership_id
                ]

                if dealership_logs_today:
                    # Simple distribution across hours based on first and last activity
                    first_log = min(dealership_logs_today, key=lambda x: x.timestamp)
                    last_log = max(dealership_logs_today, key=lambda x: x.timestamp)

                    start_hour = (
                        first_log.timestamp.hour
                        if first_log.timestamp.tzinfo
                        else first_log.timestamp.replace(tzinfo=timezone.utc).hour
                    )
                    end_hour = (
                        last_log.timestamp.hour
                        if last_log.timestamp.tzinfo
                        else last_log.timestamp.replace(tzinfo=timezone.utc).hour
                    )

                    # If employee is currently active, extend to current hour
                    is_active, _ = await is_employee_currently_active(
                        session, employee_id, dealership_id
                    )
                    if is_active:
                        end_hour = max(end_hour, now.hour)

                    # Distribute cost across hours
                    if start_hour == end_hour:
                        hourly_breakdown[start_hour]["spend"] += labor_cost
                        hourly_breakdown[start_hour]["employees"].add(employee_id)
                    else:
                        hours_span = end_hour - start_hour + 1
                        cost_per_hour = labor_cost / hours_span
                        for hour in range(start_hour, end_hour + 1):
                            hour_mod = hour % 24
                            hourly_breakdown[hour_mod]["spend"] += cost_per_hour
                            hourly_breakdown[hour_mod]["employees"].add(employee_id)

            except Exception as e:
                print(f"Error processing employee {employee_id}: {e}")
                continue

        # Only include dealerships with activity
        if dealership_hours > 0 and len(employees_with_activity) > 0:
            total_labor_spend += dealership_labor_spend
            total_hours += dealership_hours

            dealership_breakdowns.append(
                EnhancedDealershipBreakdown(
                    dealership_id=dealership_id,
                    dealership_name=dealership_names.get(dealership_id),
                    total_labor_spend=round(dealership_labor_spend, 2),
                    total_hours=round(dealership_hours, 2),
                    employee_count=len(employees_with_activity),
                )
            )

    # Format hourly breakdown for response
    formatted_hourly_breakdown = [
        HourlyLaborSpend(
            hour=hour,
            total_labor_spend=round(data["spend"], 2),
            total_employees=len(data["employees"]),
        )
        for hour, data in sorted(hourly_breakdown.items())
    ]

    # Sort dealership breakdown by labor spend (highest first)
    dealership_breakdowns.sort(key=lambda x: x.total_labor_spend, reverse=True)

    print(
        f"Enhanced analysis complete. Total: ${total_labor_spend:.2f}, {total_hours:.2f} hours"
    )

    return EnhancedDailyLaborSummary(
        target_date=target_date.isoformat(),
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2),
        dealership_breakdown=dealership_breakdowns,
        hourly_breakdown=formatted_hourly_breakdown,
    )


@router.get("/labor/daily", response_model=DailyLaborSummary)
async def get_daily_labor_spend(
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get the total labor spend for a specific day, broken down by hour and dealership.
    If no date is provided, defaults to today.
    """
    # Default to today if no date provided
    if not target_date:
        target_date = datetime.now(timezone.utc).date()

    # Start and end of the target day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all time logs for the day
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Group time logs by dealership and employee for accurate counting
    dealership_employee_logs = defaultdict(lambda: defaultdict(list))
    for log in time_logs:
        dealership_employee_logs[log.dealership_id][log.employee_id].append(log)

    # Calculate hours and labor spend for each employee
    total_labor_spend = 0.0
    total_hours = 0.0

    # Track hourly and dealership breakdowns
    hourly_breakdown = defaultdict(lambda: {"spend": 0.0, "employees": set()})
    dealership_breakdown = defaultdict(
        lambda: {"spend": 0.0, "hours": 0.0, "employees": set()}
    )

    # Process each dealership and its employees
    for dealership_id, employee_logs in dealership_employee_logs.items():
        for employee_id, logs in employee_logs.items():
            # Get employee's hourly wage
            user_details = await get_user_details(employee_id)
            hourly_wage = user_details.get("hourly_wage", 0.0)

            # Sort logs by timestamp
            sorted_logs = sorted(logs, key=lambda x: x.timestamp)

            # Calculate hours worked and corresponding spend
            clock_in_time: Optional[datetime] = None
            employee_had_activity = False

            for log in sorted_logs:
                log_ts = log.timestamp
                if log_ts.tzinfo is None:
                    log_ts = log_ts.replace(tzinfo=timezone.utc)

                if log.punch_type == PunchType.CLOCK_IN:
                    clock_in_time = log_ts
                    employee_had_activity = True
                elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                    # clock_in_time is already UTC aware
                    raw_hours = (log_ts - clock_in_time).total_seconds() / 3600
                    paid_hours = apply_unpaid_break(raw_hours)
                    spend = paid_hours * hourly_wage

                    # Add to totals
                    total_labor_spend += spend
                    total_hours += paid_hours

                    # Add to dealership breakdown
                    dealership_breakdown[dealership_id]["spend"] += spend
                    dealership_breakdown[dealership_id]["hours"] += paid_hours

                    # Add to hourly breakdown
                    # For each hour of the shift, distribute the labor spend proportionally
                    shift_start_hour = clock_in_time.hour  # clock_in_time is UTC aware
                    shift_end_hour = log_ts.hour  # log_ts is UTC aware

                    # Handle shifts that span multiple hours
                    if shift_start_hour == shift_end_hour:
                        # Shift within the same hour
                        hourly_breakdown[shift_start_hour]["spend"] += spend
                        hourly_breakdown[shift_start_hour]["employees"].add(employee_id)
                    else:
                        # Distribute across hours
                        for hour in range(shift_start_hour, shift_end_hour + 1):
                            hour_mod = hour % 24  # Handle overnight shifts
                            hourly_breakdown[hour_mod]["employees"].add(employee_id)

                            # Simple proportional distribution
                            hour_fraction = 1.0 / (
                                shift_end_hour - shift_start_hour + 1
                            )
                            hourly_breakdown[hour_mod]["spend"] += spend * hour_fraction

                    clock_in_time = None
                    employee_had_activity = True

            # Handle active shifts (if employee is still clocked in)
            if clock_in_time is not None:
                # Employee is currently clocked in - calculate time until target date end OR current time (whichever is earlier)
                now = datetime.now(timezone.utc)
                end_time = min(now, end_of_day)

                if end_time > clock_in_time:
                    raw_hours = (end_time - clock_in_time).total_seconds() / 3600
                    paid_hours = apply_unpaid_break(raw_hours)
                    spend = paid_hours * hourly_wage

                    # Add to totals
                    total_labor_spend += spend
                    total_hours += paid_hours

                    # Add to dealership breakdown
                    dealership_breakdown[dealership_id]["spend"] += spend
                    dealership_breakdown[dealership_id]["hours"] += paid_hours

                    # Add to hourly breakdown for active shift
                    shift_start_hour = clock_in_time.hour
                    current_hour = end_time.hour

                    if shift_start_hour == current_hour:
                        # Active shift within the same hour
                        hourly_breakdown[shift_start_hour]["spend"] += spend
                        hourly_breakdown[shift_start_hour]["employees"].add(employee_id)
                    else:
                        # Distribute across hours for active shift
                        for hour in range(shift_start_hour, current_hour + 1):
                            hour_mod = hour % 24
                            hourly_breakdown[hour_mod]["employees"].add(employee_id)
                            # Simple proportional distribution
                            hour_fraction = 1.0 / (current_hour - shift_start_hour + 1)
                            hourly_breakdown[hour_mod]["spend"] += spend * hour_fraction

                    employee_had_activity = True

            # Count employee if they had any clock activity at this dealership (including active shifts)
            if employee_had_activity:
                dealership_breakdown[dealership_id]["employees"].add(employee_id)

    # Format hourly breakdown for response
    formatted_hourly_breakdown = [
        HourlyLaborSpend(
            hour=hour,
            total_labor_spend=round(data["spend"], 2),
            total_employees=len(data["employees"]),
        )
        for hour, data in sorted(hourly_breakdown.items())
    ]

    # Format dealership breakdown for response
    formatted_dealership_breakdown = [
        DealershipLaborSpend(
            dealership_id=dealership_id,
            total_labor_spend=round(data["spend"], 2),
            total_hours=round(data["hours"], 2),
        )
        for dealership_id, data in dealership_breakdown.items()
    ]

    return DailyLaborSummary(
        date=target_date.isoformat(),
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2),
        hourly_breakdown=formatted_hourly_breakdown,
        dealership_breakdown=formatted_dealership_breakdown,
    )


@router.get("/labor/dealership/{dealership_id}", response_model=DealershipLaborSpend)
async def get_dealership_labor_spend(
    dealership_id: str,
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get the labor spend for a specific dealership on a specific day.
    If no date is provided, defaults to today.
    """
    # Default to today if no date provided
    if not target_date:
        target_date = datetime.now(timezone.utc).date()

    # Start and end of the target day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all time logs for the dealership on the target day
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Group time logs by employee
    employee_logs = defaultdict(list)
    for log in time_logs:
        employee_logs[log.employee_id].append(log)

    # Calculate total labor spend and hours
    total_labor_spend = 0.0
    total_hours = 0.0

    for employee_id, logs in employee_logs.items():
        # Get employee's hourly wage
        user_details = await get_user_details(employee_id)
        hourly_wage = user_details.get("hourly_wage", 0.0)

        # Sort logs by timestamp
        sorted_logs = sorted(logs, key=lambda x: x.timestamp)

        # Calculate hours worked and corresponding spend
        clock_in_time: Optional[datetime] = None
        for log in sorted_logs:
            log_ts = log.timestamp
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=timezone.utc)

            if log.punch_type == PunchType.CLOCK_IN:
                clock_in_time = log_ts
            elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                # clock_in_time is already UTC aware
                raw_hours = (log_ts - clock_in_time).total_seconds() / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                total_labor_spend += paid_hours * hourly_wage
                total_hours += paid_hours
                clock_in_time = None

        # Handle active shifts (if employee is still clocked in at this dealership)
        if clock_in_time is not None:
            # Employee is currently clocked in - calculate time until target date end OR current time (whichever is earlier)
            now = datetime.now(timezone.utc)
            end_time = min(now, end_of_day)

            if end_time > clock_in_time:
                raw_hours = (end_time - clock_in_time).total_seconds() / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                total_labor_spend += paid_hours * hourly_wage
                total_hours += paid_hours

    return DealershipLaborSpend(
        dealership_id=dealership_id,
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2),
    )


@router.get(
    "/active/dealership/{dealership_id}", response_model=DealershipEmployeeStatus
)
async def get_active_employees_by_dealership(
    dealership_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    print(
        f"\n--- Processing get_active_employees_by_dealership for dealership_id: {dealership_id} ---"
    )
    """
    Get information about all currently active employees at a specific dealership,
    including their hourly rates, shift duration, and weekly hours.
    """
    # Get all employees who have clocked in at this dealership recently
    # Look back a few days to catch cross-day shifts
    lookback_date = datetime.now(timezone.utc) - timedelta(days=2)

    # Get recent clock entries for this dealership
    recent_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= lookback_date)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    print(f"Found {len(recent_clocks)} recent clock entries for {dealership_id}")

    # Get unique employee IDs who have clocked at this dealership recently
    employee_ids = list(set(clock.employee_id for clock in recent_clocks))
    print(f"Found {len(employee_ids)} unique employees for {dealership_id}")

    # Check each employee's current active status
    active_employees = []
    total_current_hourly_rate = 0.0
    total_labor_spend_today = 0.0

    for employee_id in employee_ids:
        # Use the more robust active detection
        is_active, most_recent_clock_in_ts = await is_employee_currently_active(
            session, employee_id, dealership_id
        )

        if is_active and most_recent_clock_in_ts:
            print(
                f"Employee {employee_id} determined ACTIVE. Most recent clock-in: {most_recent_clock_in_ts}"
            )

            # Get employee details
            user_details = await get_user_details(employee_id)
            print(f"User details for {employee_id}: {user_details}")
            hourly_wage = user_details.get("hourly_wage", 0.0)
            employee_name = user_details.get("name", "Unknown")

            # Calculate current shift duration
            now = datetime.now(timezone.utc)
            shift_duration_hours = (
                now - most_recent_clock_in_ts
            ).total_seconds() / 3600

            # Calculate weekly hours
            weekly_hours = await calculate_weekly_hours(session, employee_id)
            print(
                f"Calculated shift_duration_hours for {employee_id}: {shift_duration_hours}"
            )
            print(f"Calculated weekly_hours for {employee_id}: {weekly_hours}")

            # Check if in overtime
            is_overtime = weekly_hours > 40.0

            # Calculate today's labor spend for this employee
            today = datetime.now(timezone.utc).date()
            start_of_day = datetime.combine(today, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
            end_of_day = datetime.combine(today, datetime.max.time()).replace(
                tzinfo=timezone.utc
            )

            # Get today's clocks for this employee at this dealership
            todays_clocks = session.exec(
                select(TimeLog)
                .where(TimeLog.employee_id == employee_id)
                .where(TimeLog.dealership_id == dealership_id)
                .where(TimeLog.timestamp >= start_of_day)
                .where(TimeLog.timestamp <= end_of_day)
                .order_by(TimeLog.timestamp.asc())
            ).all()

            today_labor_spend = 0.0
            current_shift_clock_in_time: Optional[datetime] = None

            for punch in todays_clocks:
                punch_ts = punch.timestamp
                if punch_ts.tzinfo is None:
                    punch_ts = punch_ts.replace(tzinfo=timezone.utc)

                if punch.punch_type == PunchType.CLOCK_IN:
                    current_shift_clock_in_time = punch_ts
                elif (
                    punch.punch_type == PunchType.CLOCK_OUT
                    and current_shift_clock_in_time
                ):
                    raw_hours = (
                        punch_ts - current_shift_clock_in_time
                    ).total_seconds() / 3600
                    paid_hours = apply_unpaid_break(raw_hours)
                    today_labor_spend += paid_hours * hourly_wage
                    current_shift_clock_in_time = None

            # Add current open shift (if the active clock-in was today)
            if current_shift_clock_in_time:
                raw_hours = (now - current_shift_clock_in_time).total_seconds() / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                today_labor_spend += paid_hours * hourly_wage
            elif most_recent_clock_in_ts >= start_of_day:
                # The active clock-in was today but not captured in today's clocks (edge case)
                raw_hours = (now - most_recent_clock_in_ts).total_seconds() / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                today_labor_spend += paid_hours * hourly_wage

            total_labor_spend_today += today_labor_spend
            total_current_hourly_rate += hourly_wage

            active_employees.append(
                EmployeeShiftInfo(
                    employee_id=employee_id,
                    employee_name=employee_name,
                    dealership_id=dealership_id,
                    hourly_wage=hourly_wage,
                    shift_start_time=most_recent_clock_in_ts,
                    current_shift_duration_hours=round(shift_duration_hours, 2),
                    weekly_hours_worked=round(weekly_hours, 2),
                    is_overtime=is_overtime,
                )
            )

    print(f"Final active_employees list for {dealership_id}: {active_employees}")

    # Sort by shift duration (longest first)
    active_employees.sort(key=lambda x: x.current_shift_duration_hours, reverse=True)

    result = DealershipEmployeeStatus(
        dealership_id=dealership_id,
        active_employees=active_employees,
        active_employee_count=len(active_employees),
        total_current_hourly_rate=round(total_current_hourly_rate, 2),
        total_labor_spend_today=round(total_labor_spend_today, 2),
    )
    print(f"Returning DealershipEmployeeStatus for {dealership_id}: {result}")
    return result


@router.get("/active/all", response_model=List[DealershipEmployeeStatus])
async def get_all_active_employees(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_or_supervisor_role),
):
    print(f"\n--- Processing get_all_active_employees ---")
    """
    Get information about all currently active employees across all dealerships.
    This provides a company-wide overview of current labor utilization.
    """
    # First, get a list of all dealerships
    dealerships_ref = firestore_db.collection("dealerships").stream()
    dealership_ids = [doc.id for doc in dealerships_ref]
    print(f"Found dealership_ids: {dealership_ids}")

    # For each dealership, get active employees
    all_dealership_statuses = []

    for dealership_id in dealership_ids:
        dealership_status = await get_active_employees_by_dealership(
            dealership_id=dealership_id, session=session, admin_user=admin_user
        )
        print(
            f"Status for dealership {dealership_id} (from get_active_employees_by_dealership): {dealership_status}"
        )

        # Only include dealerships with active employees
        if dealership_status.active_employee_count > 0:
            all_dealership_statuses.append(dealership_status)

    # Sort by active employee count (highest first)
    all_dealership_statuses.sort(key=lambda x: x.active_employee_count, reverse=True)

    print(f"Final all_dealership_statuses before returning: {all_dealership_statuses}")
    return all_dealership_statuses


@router.get("/labor/weekly", response_model=List[DealershipLaborSpend])
async def get_weekly_labor_spend(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get the weekly labor spend across all dealerships.
    If no dates are provided, defaults to the current week (Monday to Sunday).
    """
    # Default to current week if no dates provided
    today = datetime.now(timezone.utc).date()
    if not start_date:
        # Get Monday of current week
        start_date = today - timedelta(days=today.weekday())

    if not end_date:
        # Get Sunday of current week
        end_date = start_date + timedelta(days=6)

    # Start and end of the date range in UTC
    start_datetime = datetime.combine(start_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end_datetime = datetime.combine(end_date, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all time logs for the week
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_datetime)
        .where(TimeLog.timestamp <= end_datetime)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Group time logs by dealership and employee
    dealership_employee_logs = defaultdict(lambda: defaultdict(list))
    for log in time_logs:
        dealership_employee_logs[log.dealership_id][log.employee_id].append(log)

    # Calculate labor spend for each dealership
    dealership_labor_spend = []

    for dealership_id, employee_logs in dealership_employee_logs.items():
        total_labor_spend = 0.0
        total_hours = 0.0

        for employee_id, logs in employee_logs.items():
            # Get employee's hourly wage
            user_details = await get_user_details(employee_id)
            hourly_wage = user_details.get("hourly_wage", 0.0)

            # Sort logs by timestamp
            sorted_logs = sorted(logs, key=lambda x: x.timestamp)

            # Calculate hours worked and corresponding spend
            clock_in_time: Optional[datetime] = None
            for log in sorted_logs:
                log_ts = log.timestamp
                if log_ts.tzinfo is None:
                    log_ts = log_ts.replace(tzinfo=timezone.utc)

                if log.punch_type == PunchType.CLOCK_IN:
                    clock_in_time = log_ts
                elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                    # clock_in_time is already UTC aware
                    raw_hours = (log_ts - clock_in_time).total_seconds() / 3600
                    paid_hours = apply_unpaid_break(raw_hours)

                    # Apply overtime rate for hours > 40 in the week
                    # This is a simplified approach; in a real system you'd track
                    # cumulative hours throughout the week more precisely
                    if (
                        employee_logs[employee_id].index(log) > 8
                    ):  # Rough approximation of 40 hours
                        total_labor_spend += paid_hours * hourly_wage * 1.5
                    else:
                        total_labor_spend += paid_hours * hourly_wage

                    total_hours += paid_hours
                    clock_in_time = None

        dealership_labor_spend.append(
            DealershipLaborSpend(
                dealership_id=dealership_id,
                total_labor_spend=round(total_labor_spend, 2),
                total_hours=round(total_hours, 2),
            )
        )

    # Sort by total labor spend (highest first)
    dealership_labor_spend.sort(key=lambda x: x.total_labor_spend, reverse=True)

    return dealership_labor_spend


@router.get("/employee/{employee_id}/details", response_model=EmployeeDetailResponse)
async def get_employee_details(
    employee_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get detailed information about a specific employee including:
    - Recent clock entries (last two weeks)
    - Hours worked per week
    - Pay per week
    - Hourly rate
    """
    # Get current date and calculate date ranges
    now = datetime.now(timezone.utc)
    today = now.date()

    # Calculate start of current week (Monday)
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)

    # Calculate previous week
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_end = current_week_start - timedelta(days=1)

    # Start date for fetching clocks (2 weeks ago) - ORIGINAL ENDPOINT
    two_weeks_ago = now - timedelta(days=14)
    print(f"DEBUG: Fetching clocks since {two_weeks_ago} for employee {employee_id}")

    # Get employee details from Firestore
    user_details = await get_user_details(employee_id)
    employee_name = user_details.get("name", "Unknown")
    hourly_wage = user_details.get("hourly_wage", 0.0)

    # Get all clock entries for the past two weeks
    recent_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= two_weeks_ago)
        .order_by(TimeLog.timestamp.desc())
    ).all()

    print(f"DEBUG: Found {len(recent_clocks)} clock entries for employee {employee_id}")

    # Print the first few clock entries for debugging
    for i, clock in enumerate(recent_clocks[:5]):
        print(f"DEBUG: Clock {i+1}: {clock.timestamp} - {clock.punch_type}")

    # Format clock entries
    clock_entries = []
    for clock in recent_clocks:
        # Ensure timestamp is timezone aware
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        clock_entries.append(
            EmployeeClockEntry(
                id=clock.id,
                timestamp=ts,
                punch_type=clock.punch_type,
                dealership_id=clock.dealership_id,
            )
        )

    print(f"DEBUG: Formatted {len(clock_entries)} clock entries for response")

    # Calculate hours and pay for current week
    current_week_hours = 0.0
    # Use EST timezone for week calculations to match business operations
    from zoneinfo import ZoneInfo

    est_timezone = ZoneInfo("America/New_York")

    current_week_start_dt = (
        datetime.combine(current_week_start, datetime.min.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )
    current_week_end_dt = (
        datetime.combine(current_week_end, datetime.max.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )

    current_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= current_week_start_dt)
        .where(TimeLog.timestamp <= current_week_end_dt)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Calculate hours for current week using helper (handles implicit clock-outs)
    current_week_hours = calculate_hours_from_logs_with_daily_breaks(
        current_week_clocks, now
    )

    current_week_pay = current_week_hours * hourly_wage

    # Calculate hours and pay for previous week
    prev_week_hours = 0.0
    prev_week_start_dt = (
        datetime.combine(prev_week_start, datetime.min.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )
    prev_week_end_dt = (
        datetime.combine(prev_week_end, datetime.max.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )

    prev_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= prev_week_start_dt)
        .where(TimeLog.timestamp <= prev_week_end_dt)
        .order_by(TimeLog.timestamp.asc(), TimeLog.punch_type.desc())
    ).all()

    # Calculate hours for previous week using helper (handles implicit clock-outs)
    prev_week_hours = calculate_hours_from_logs_with_daily_breaks(
        prev_week_clocks, prev_week_end_dt
    )

    prev_week_pay = prev_week_hours * hourly_wage

    # Calculate regular and overtime hours for each week
    prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(
        prev_week_hours
    )
    prev_week_pay = calculate_pay_with_overtime(
        prev_week_regular, prev_week_overtime, hourly_wage
    )

    current_week_regular, current_week_overtime = calculate_regular_and_overtime_hours(
        current_week_hours
    )
    current_week_pay = calculate_pay_with_overtime(
        current_week_regular, current_week_overtime, hourly_wage
    )

    # Calculate today's hours and clock status
    todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(
        session, employee_id
    )
    todays_regular, todays_overtime = calculate_regular_and_overtime_hours(todays_hours)
    todays_pay = calculate_pay_with_overtime(
        todays_regular, todays_overtime, hourly_wage
    )

    # Calculate vacation hours for each period
    prev_week_vacation_hours = await calculate_vacation_hours(
        session, employee_id, prev_week_start, prev_week_end
    )
    current_week_vacation_hours = await calculate_vacation_hours(
        session, employee_id, current_week_start, current_week_end
    )
    todays_vacation_hours = await calculate_vacation_hours(
        session, employee_id, today, today
    )

    # Create week summaries
    week_summaries = [
        WeekSummary(
            week_start_date=prev_week_start.isoformat(),
            week_end_date=prev_week_end.isoformat(),
            total_hours=round(prev_week_hours, 2),
            regular_hours=round(prev_week_regular, 2),
            overtime_hours=round(prev_week_overtime, 2),
            total_pay=round(prev_week_pay, 2),
            vacation_hours=round(prev_week_vacation_hours, 2),
            is_current_week=False,
        ),
        WeekSummary(
            week_start_date=current_week_start.isoformat(),
            week_end_date=current_week_end.isoformat(),
            total_hours=round(current_week_hours, 2),
            regular_hours=round(current_week_regular, 2),
            overtime_hours=round(current_week_overtime, 2),
            total_pay=round(current_week_pay, 2),
            vacation_hours=round(current_week_vacation_hours, 2),
            is_current_week=True,
        ),
    ]

    # Calculate total pay for both weeks
    two_week_total_pay = prev_week_pay + current_week_pay

    # ------------------------------------------------------------
    # NEW: Aggregated totals for the entire requested date range
    # ------------------------------------------------------------
    range_total_hours = 0.0
    range_regular_hours = 0.0
    range_overtime_hours = 0.0
    range_total_pay = 0.0

    # Group recent clock entries by the ISO week they belong to and compute
    week_logs_map: Dict[date, List[TimeLog]] = {}
    for clock in recent_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        week_start_date = ts.date() - timedelta(days=ts.date().weekday())
        week_logs_map.setdefault(week_start_date, []).append(clock)

    for week_start_date, week_logs in week_logs_map.items():
        week_end_dt = datetime.combine(
            week_start_date + timedelta(days=6),
            datetime.max.time(),
            tzinfo=timezone.utc,
        )
        week_hours = calculate_hours_from_logs_with_daily_breaks(week_logs, week_end_dt)
        week_regular, week_overtime = calculate_regular_and_overtime_hours(week_hours)
        week_pay = calculate_pay_with_overtime(week_regular, week_overtime, hourly_wage)

        range_total_hours += week_hours
        range_regular_hours += week_regular
        range_overtime_hours += week_overtime
        range_total_pay += week_pay

    range_total_hours = round(range_total_hours, 2)
    range_regular_hours = round(range_regular_hours, 2)
    range_overtime_hours = round(range_overtime_hours, 2)
    range_total_pay = round(range_total_pay, 2)

    return EmployeeDetailResponse(
        employee_id=employee_id,
        employee_name=employee_name,
        hourly_wage=hourly_wage,
        recent_clocks=clock_entries,
        week_summaries=week_summaries,
        todays_summary=TodaysSummary(
            date=today.isoformat(),
            total_hours=round(todays_hours, 2),
            regular_hours=round(todays_regular, 2),
            overtime_hours=round(todays_overtime, 2),
            total_pay=round(todays_pay, 2),
            vacation_hours=round(todays_vacation_hours, 2),
            is_currently_clocked_in=is_currently_clocked_in,
        ),
        two_week_total_pay=round(two_week_total_pay, 2),
        date_range_total_hours=range_total_hours,
        date_range_regular_hours=range_regular_hours,
        date_range_overtime_hours=range_overtime_hours,
        date_range_total_pay=range_total_pay,
    )


@router.get(
    "/employee/{employee_id}/details-by-date-range",
    response_model=EmployeeDetailResponse,
)
async def get_employee_details_by_date_range(
    employee_id: str,
    start_date: date,
    end_date: date,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get detailed information about a specific employee including:
    - Recent clock entries (within specified date range)
    - Hours worked per week
    - Pay per week
    - Hourly rate

        This endpoint accepts a date range in EST for filtering clock entries.

    Args:
        employee_id: The ID of the employee
        start_date: Start date for clock entries (YYYY-MM-DD format, EST)
        end_date: End date for clock entries (YYYY-MM-DD format, EST)
    """
    # Get current date and calculate date ranges
    now = datetime.now(timezone.utc)
    today = now.date()

    # Calculate start of current week (Monday)
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)

    # Calculate previous week
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_end = current_week_start - timedelta(days=1)

    # Convert input dates to datetime objects with EST timezone for filtering
    # The user passes dates in EST, so we need to convert them properly
    from zoneinfo import ZoneInfo

    est_timezone = ZoneInfo("America/New_York")

    date_range_start = (
        datetime.combine(start_date, datetime.min.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )
    date_range_end = (
        datetime.combine(end_date, datetime.max.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )
    print(
        f"DEBUG: Fetching clocks from {date_range_start} to {date_range_end} for employee {employee_id} (converted from EST)"
    )

    # Get employee details from Firestore
    user_details = await get_user_details(employee_id)
    employee_name = user_details.get("name", "Unknown")
    hourly_wage = user_details.get("hourly_wage", 0.0)

    # Get all clock entries within the specified date range
    recent_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= date_range_start)
        .where(TimeLog.timestamp <= date_range_end)
        .order_by(TimeLog.timestamp.desc())
    ).all()

    print(f"DEBUG: Found {len(recent_clocks)} clock entries for employee {employee_id}")

    # Print the first few clock entries for debugging
    for i, clock in enumerate(recent_clocks[:5]):
        print(f"DEBUG: Clock {i+1}: {clock.timestamp} - {clock.punch_type}")

    # Format clock entries
    clock_entries = []
    for clock in recent_clocks:
        # Ensure timestamp is timezone aware
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        clock_entries.append(
            EmployeeClockEntry(
                id=clock.id,
                timestamp=ts,
                punch_type=clock.punch_type,
                dealership_id=clock.dealership_id,
            )
        )

    print(f"DEBUG: Formatted {len(clock_entries)} clock entries for response")

    # Calculate hours and pay for current week
    current_week_hours = 0.0
    current_week_start_dt = datetime.combine(
        current_week_start, datetime.min.time()
    ).replace(tzinfo=timezone.utc)
    current_week_end_dt = datetime.combine(
        current_week_end, datetime.max.time()
    ).replace(tzinfo=timezone.utc)

    current_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= current_week_start_dt)
        .where(TimeLog.timestamp <= current_week_end_dt)
        .order_by(TimeLog.timestamp.asc(), TimeLog.punch_type.desc())
    ).all()

    # Calculate hours for current week using helper (handles implicit clock-outs)
    current_week_hours = calculate_hours_from_logs_with_daily_breaks(
        current_week_clocks, now
    )

    current_week_pay = current_week_hours * hourly_wage

    # Calculate hours and pay for previous week
    prev_week_hours = 0.0
    prev_week_start_dt = datetime.combine(prev_week_start, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    prev_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= prev_week_start_dt)
        .where(TimeLog.timestamp <= prev_week_end_dt)
        .order_by(TimeLog.timestamp.asc(), TimeLog.punch_type.desc())
    ).all()

    # Calculate hours for previous week using helper (handles implicit clock-outs)
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )
    prev_week_hours = calculate_hours_from_logs_with_daily_breaks(
        prev_week_clocks, prev_week_end_dt
    )

    prev_week_pay = prev_week_hours * hourly_wage

    # Calculate regular and overtime hours for each week
    prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(
        prev_week_hours
    )
    prev_week_pay = calculate_pay_with_overtime(
        prev_week_regular, prev_week_overtime, hourly_wage
    )

    current_week_regular, current_week_overtime = calculate_regular_and_overtime_hours(
        current_week_hours
    )
    current_week_pay = calculate_pay_with_overtime(
        current_week_regular, current_week_overtime, hourly_wage
    )

    # Calculate today's hours and clock status
    todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(
        session, employee_id
    )
    todays_regular, todays_overtime = calculate_regular_and_overtime_hours(todays_hours)
    todays_pay = calculate_pay_with_overtime(
        todays_regular, todays_overtime, hourly_wage
    )

    # Calculate vacation hours for each period
    prev_week_vacation_hours = await calculate_vacation_hours(
        session, employee_id, prev_week_start, prev_week_end
    )
    current_week_vacation_hours = await calculate_vacation_hours(
        session, employee_id, current_week_start, current_week_end
    )
    todays_vacation_hours = await calculate_vacation_hours(
        session, employee_id, today, today
    )

    # Create week summaries
    week_summaries = [
        WeekSummary(
            week_start_date=prev_week_start.isoformat(),
            week_end_date=prev_week_end.isoformat(),
            total_hours=round(prev_week_hours, 2),
            regular_hours=round(prev_week_regular, 2),
            overtime_hours=round(prev_week_overtime, 2),
            total_pay=round(prev_week_pay, 2),
            vacation_hours=round(prev_week_vacation_hours, 2),
            is_current_week=False,
        ),
        WeekSummary(
            week_start_date=current_week_start.isoformat(),
            week_end_date=current_week_end.isoformat(),
            total_hours=round(current_week_hours, 2),
            regular_hours=round(current_week_regular, 2),
            overtime_hours=round(current_week_overtime, 2),
            total_pay=round(current_week_pay, 2),
            vacation_hours=round(current_week_vacation_hours, 2),
            is_current_week=True,
        ),
    ]

    # Calculate total pay for both weeks
    two_week_total_pay = prev_week_pay + current_week_pay

    # ------------------------------------------------------------
    # Aggregated totals for the entire user-supplied date range
    # ------------------------------------------------------------
    range_total_hours = 0.0
    range_regular_hours = 0.0
    range_overtime_hours = 0.0
    range_total_pay = 0.0

    # Group the recent clock entries (already filtered by date range) by ISO week
    from collections import defaultdict

    week_logs_map: Dict[date, List[TimeLog]] = defaultdict(list)
    for clock in recent_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        week_start_date = ts.date() - timedelta(days=ts.date().weekday())
        week_logs_map[week_start_date].append(clock)

    # Compute hours / pay for each partial week in the range
    for week_start_date, week_logs in week_logs_map.items():
        week_end_dt = datetime.combine(
            week_start_date + timedelta(days=6),
            datetime.max.time(),
            tzinfo=timezone.utc,
        )

        week_hours = calculate_hours_from_logs_with_daily_breaks(week_logs, week_end_dt)
        week_regular, week_overtime = calculate_regular_and_overtime_hours(week_hours)
        week_pay = calculate_pay_with_overtime(week_regular, week_overtime, hourly_wage)

        range_total_hours += week_hours
        range_regular_hours += week_regular
        range_overtime_hours += week_overtime
        range_total_pay += week_pay

    # Round to 2-decimal precision for response
    range_total_hours = round(range_total_hours, 2)
    range_regular_hours = round(range_regular_hours, 2)
    range_overtime_hours = round(range_overtime_hours, 2)
    range_total_pay = round(range_total_pay, 2)

    return EmployeeDetailResponse(
        employee_id=employee_id,
        employee_name=employee_name,
        hourly_wage=hourly_wage,
        recent_clocks=clock_entries,
        week_summaries=week_summaries,
        todays_summary=TodaysSummary(
            date=today.isoformat(),
            total_hours=round(todays_hours, 2),
            regular_hours=round(todays_regular, 2),
            overtime_hours=round(todays_overtime, 2),
            total_pay=round(todays_pay, 2),
            vacation_hours=round(todays_vacation_hours, 2),
            is_currently_clocked_in=is_currently_clocked_in,
        ),
        two_week_total_pay=round(two_week_total_pay, 2),
        date_range_total_hours=range_total_hours,
        date_range_regular_hours=range_regular_hours,
        date_range_overtime_hours=range_overtime_hours,
        date_range_total_pay=range_total_pay,
    )


@router.get("/employees/details", response_model=List[EmployeeDetailResponse])
async def get_all_employees_details(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    limit: Optional[int] = 100,
    offset: Optional[int] = 0,
):
    """
    Get detailed information about all employees including:
    - Recent clock entries (last two weeks)
    - Hours worked per week
    - Pay per week
    - Hourly rate

    This endpoint uses pagination with limit and offset parameters.
    """
    # Calculate date ranges once for all employees
    now = datetime.now(timezone.utc)
    today = now.date()

    # Calculate start of current week (Monday)
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)

    # Calculate previous week
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_end = current_week_start - timedelta(days=1)

    # Start date for fetching clocks (2 weeks ago)
    two_weeks_ago = now - timedelta(days=14)

    # Convert to datetime objects with timezone
    current_week_start_dt = datetime.combine(
        current_week_start, datetime.min.time()
    ).replace(tzinfo=timezone.utc)
    current_week_end_dt = datetime.combine(
        current_week_end, datetime.max.time()
    ).replace(tzinfo=timezone.utc)
    prev_week_start_dt = datetime.combine(prev_week_start, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all employees from Firestore
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    employees_data = {}
    employee_ids = []

    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        employee_ids.append(employee_id)
        employees_data[employee_id] = {
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": user_data.get("hourlyWage", 0.0),
        }

    # Apply pagination to employee list
    total_employees = len(employee_ids)
    paginated_employee_ids = sorted(employee_ids)[offset : offset + limit]

    # If no employees, return empty list
    if not paginated_employee_ids:
        return []

    # Batch fetch all clock entries for the past two weeks for all paginated employees
    all_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(paginated_employee_ids))
        .where(TimeLog.timestamp >= two_weeks_ago)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Ensure all timestamps from DB are timezone-aware before comparisons
    for clock in all_clocks:
        if clock.timestamp.tzinfo is None:
            clock.timestamp = clock.timestamp.replace(tzinfo=timezone.utc)

    # Group clocks by employee_id
    employee_clocks = {}
    for clock in all_clocks:
        employee_id = clock.employee_id
        if employee_id not in employee_clocks:
            employee_clocks[employee_id] = []
        employee_clocks[employee_id].append(clock)

    # Process each employee
    all_employee_details = []
    for employee_id in paginated_employee_ids:
        employee_name = employees_data[employee_id]["name"]
        hourly_wage = employees_data[employee_id]["hourly_wage"]

        # Get this employee's clocks
        employee_clock_list = employee_clocks.get(employee_id, [])

        # Format clock entries (most recent first)
        clock_entries = []
        for clock in sorted(
            employee_clock_list, key=lambda x: x.timestamp, reverse=True
        ):
            # Ensure timestamp is timezone aware
            ts = clock.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            clock_entries.append(
                EmployeeClockEntry(
                    id=clock.id,
                    timestamp=ts,
                    punch_type=clock.punch_type,
                    dealership_id=clock.dealership_id,
                )
            )

        # Calculate hours and pay
        current_week_hours = 0.0
        prev_week_hours = 0.0

        # Calculate hours using shared helper for consistency
        current_week_clocks = [
            c
            for c in employee_clock_list
            if current_week_start_dt <= c.timestamp <= current_week_end_dt
        ]
        prev_week_clocks = [
            c
            for c in employee_clock_list
            if prev_week_start_dt <= c.timestamp <= prev_week_end_dt
        ]

        current_week_hours = calculate_hours_from_logs(current_week_clocks, now)
        # Cap previous week's calculation at the end of that week
        prev_week_hours = calculate_hours_from_logs(prev_week_clocks, prev_week_end_dt)

        current_week_pay = current_week_hours * hourly_wage
        prev_week_pay = prev_week_hours * hourly_wage

        # Calculate regular and overtime hours for each week
        prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(
            prev_week_hours
        )
        prev_week_pay = calculate_pay_with_overtime(
            prev_week_regular, prev_week_overtime, hourly_wage
        )

        current_week_regular, current_week_overtime = (
            calculate_regular_and_overtime_hours(current_week_hours)
        )
        current_week_pay = calculate_pay_with_overtime(
            current_week_regular, current_week_overtime, hourly_wage
        )

        # Calculate today's hours and clock status
        todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(
            session, employee_id
        )
        todays_regular, todays_overtime = calculate_regular_and_overtime_hours(
            todays_hours
        )
        todays_pay = calculate_pay_with_overtime(
            todays_regular, todays_overtime, hourly_wage
        )

        # Calculate vacation hours for each period
        prev_week_vacation_hours = await calculate_vacation_hours(
            session, employee_id, prev_week_start, prev_week_end
        )
        current_week_vacation_hours = await calculate_vacation_hours(
            session, employee_id, current_week_start, current_week_end
        )
        todays_vacation_hours = await calculate_vacation_hours(
            session, employee_id, today, today
        )

        # Create week summaries
        week_summaries = [
            WeekSummary(
                week_start_date=prev_week_start.isoformat(),
                week_end_date=prev_week_end.isoformat(),
                total_hours=round(prev_week_hours, 2),
                regular_hours=round(prev_week_regular, 2),
                overtime_hours=round(prev_week_overtime, 2),
                total_pay=round(prev_week_pay, 2),
                is_current_week=False,
            ),
            WeekSummary(
                week_start_date=current_week_start.isoformat(),
                week_end_date=current_week_end.isoformat(),
                total_hours=round(current_week_hours, 2),
                regular_hours=round(current_week_regular, 2),
                overtime_hours=round(current_week_overtime, 2),
                total_pay=round(current_week_pay, 2),
                is_current_week=True,
            ),
        ]

        # Calculate total pay for both weeks
        two_week_total_pay = prev_week_pay + current_week_pay

        all_employee_details.append(
            EmployeeDetailResponse(
                employee_id=employee_id,
                employee_name=employee_name,
                hourly_wage=hourly_wage,
                recent_clocks=clock_entries,
                week_summaries=week_summaries,
                todays_summary=TodaysSummary(
                    date=today.isoformat(),
                    total_hours=round(todays_hours, 2),
                    regular_hours=round(todays_regular, 2),
                    overtime_hours=round(todays_overtime, 2),
                    total_pay=round(todays_pay, 2),
                    is_currently_clocked_in=is_currently_clocked_in,
                ),
                two_week_total_pay=round(two_week_total_pay, 2),
            )
        )

    # Sort by name
    all_employee_details.sort(key=lambda x: x.employee_name or "")

    return all_employee_details


@router.get(
    "/employees/details-by-date-range", response_model=List[EmployeeDetailResponse]
)
async def get_all_employees_details_by_date_range(
    start_date: date,
    end_date: date,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get detailed information about all employees including:
    - Recent clock entries (within specified date range)
    - Hours worked per week
    - Pay per week
    - Hourly rate

        This endpoint accepts a date range in EST for filtering clock entries.

    Args:
        start_date: Start date for clock entries (YYYY-MM-DD format, EST)
        end_date: End date for clock entries (YYYY-MM-DD format, EST)
    """
    # Calculate date ranges once for all employees
    now = datetime.now(timezone.utc)
    today = now.date()

    # Calculate start of current week (Monday)
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)

    # Calculate previous week
    prev_week_start = current_week_start - timedelta(days=7)
    prev_week_end = current_week_start - timedelta(days=1)

    # Convert input dates to datetime objects with EST timezone for filtering
    # The user passes dates in EST, so we need to convert them properly
    from zoneinfo import ZoneInfo

    est_timezone = ZoneInfo("America/New_York")

    date_range_start = (
        datetime.combine(start_date, datetime.min.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )
    date_range_end = (
        datetime.combine(end_date, datetime.max.time())
        .replace(tzinfo=est_timezone)
        .astimezone(timezone.utc)
    )

    # Convert to datetime objects with timezone
    current_week_start_dt = datetime.combine(
        current_week_start, datetime.min.time()
    ).replace(tzinfo=timezone.utc)
    current_week_end_dt = datetime.combine(
        current_week_end, datetime.max.time()
    ).replace(tzinfo=timezone.utc)
    prev_week_start_dt = datetime.combine(prev_week_start, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all employees from Firestore
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    employees_data = {}
    employee_ids = []

    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        employee_ids.append(employee_id)
        employees_data[employee_id] = {
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": user_data.get("hourlyWage", 0.0),
        }

    # No pagination - get all employees
    all_employee_ids = sorted(employee_ids)

    # If no employees, return empty list
    if not all_employee_ids:
        return []

    # Batch fetch all clock entries within the specified date range for all employees
    all_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(all_employee_ids))
        .where(TimeLog.timestamp >= date_range_start)
        .where(TimeLog.timestamp <= date_range_end)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Ensure all timestamps from DB are timezone-aware before comparisons
    for clock in all_clocks:
        if clock.timestamp.tzinfo is None:
            clock.timestamp = clock.timestamp.replace(tzinfo=timezone.utc)

    # Group clocks by employee_id
    employee_clocks = {}
    for clock in all_clocks:
        employee_id = clock.employee_id
        if employee_id not in employee_clocks:
            employee_clocks[employee_id] = []
        employee_clocks[employee_id].append(clock)

    # Process each employee
    all_employee_details = []
    for employee_id in all_employee_ids:
        employee_name = employees_data[employee_id]["name"]
        hourly_wage = employees_data[employee_id]["hourly_wage"]

        # Get this employee's clocks
        employee_clock_list = employee_clocks.get(employee_id, [])

        # Format clock entries (most recent first)
        clock_entries = []
        for clock in sorted(
            employee_clock_list, key=lambda x: x.timestamp, reverse=True
        ):
            # Ensure timestamp is timezone aware
            ts = clock.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            clock_entries.append(
                EmployeeClockEntry(
                    id=clock.id,
                    timestamp=ts,
                    punch_type=clock.punch_type,
                    dealership_id=clock.dealership_id,
                )
            )

        # Calculate hours and pay
        current_week_hours = 0.0
        prev_week_hours = 0.0

        # Calculate hours using shared helper for consistency
        current_week_clocks = [
            c
            for c in employee_clock_list
            if current_week_start_dt <= c.timestamp <= current_week_end_dt
        ]
        prev_week_clocks = [
            c
            for c in employee_clock_list
            if prev_week_start_dt <= c.timestamp <= prev_week_end_dt
        ]

        current_week_hours = calculate_hours_from_logs(current_week_clocks, now)
        # Cap previous week's calculation at the end of that week
        prev_week_hours = calculate_hours_from_logs(prev_week_clocks, prev_week_end_dt)

        current_week_pay = current_week_hours * hourly_wage
        prev_week_pay = prev_week_hours * hourly_wage

        # Calculate regular and overtime hours for each week
        prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(
            prev_week_hours
        )
        prev_week_pay = calculate_pay_with_overtime(
            prev_week_regular, prev_week_overtime, hourly_wage
        )

        current_week_regular, current_week_overtime = (
            calculate_regular_and_overtime_hours(current_week_hours)
        )
        current_week_pay = calculate_pay_with_overtime(
            current_week_regular, current_week_overtime, hourly_wage
        )

        # Calculate today's hours and clock status
        todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(
            session, employee_id
        )
        todays_regular, todays_overtime = calculate_regular_and_overtime_hours(
            todays_hours
        )
        todays_pay = calculate_pay_with_overtime(
            todays_regular, todays_overtime, hourly_wage
        )

        # Calculate vacation hours for each period
        prev_week_vacation_hours = await calculate_vacation_hours(
            session, employee_id, prev_week_start, prev_week_end
        )
        current_week_vacation_hours = await calculate_vacation_hours(
            session, employee_id, current_week_start, current_week_end
        )
        todays_vacation_hours = await calculate_vacation_hours(
            session, employee_id, today, today
        )

        # Create week summaries
        week_summaries = [
            WeekSummary(
                week_start_date=prev_week_start.isoformat(),
                week_end_date=prev_week_end.isoformat(),
                total_hours=round(prev_week_hours, 2),
                regular_hours=round(prev_week_regular, 2),
                overtime_hours=round(prev_week_overtime, 2),
                total_pay=round(prev_week_pay, 2),
                is_current_week=False,
            ),
            WeekSummary(
                week_start_date=current_week_start.isoformat(),
                week_end_date=current_week_end.isoformat(),
                total_hours=round(current_week_hours, 2),
                regular_hours=round(current_week_regular, 2),
                overtime_hours=round(current_week_overtime, 2),
                total_pay=round(current_week_pay, 2),
                is_current_week=True,
            ),
        ]

        # Calculate total pay for both weeks
        two_week_total_pay = prev_week_pay + current_week_pay

        all_employee_details.append(
            EmployeeDetailResponse(
                employee_id=employee_id,
                employee_name=employee_name,
                hourly_wage=hourly_wage,
                recent_clocks=clock_entries,
                week_summaries=week_summaries,
                todays_summary=TodaysSummary(
                    date=today.isoformat(),
                    total_hours=round(todays_hours, 2),
                    regular_hours=round(todays_regular, 2),
                    overtime_hours=round(todays_overtime, 2),
                    total_pay=round(todays_pay, 2),
                    is_currently_clocked_in=is_currently_clocked_in,
                ),
                two_week_total_pay=round(two_week_total_pay, 2),
            )
        )

    # Sort by name
    all_employee_details.sort(key=lambda x: x.employee_name or "")

    return all_employee_details


@router.get(
    "/dealership/{dealership_id}/employee-hours",
    response_model=DealershipEmployeeHoursResponse,
)
async def get_dealership_employee_hours_breakdown(
    dealership_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get a breakdown of all employees at a dealership with their regular and overtime hours.
    Perfect for labor cost overview and management.

    Args:
        dealership_id: The ID of the dealership
        start_date: Start date for the calculation (defaults to current week start)
        end_date: End date for the calculation (defaults to current week end)

    Returns:
        DealershipEmployeeHoursResponse with each employee's hours breakdown
    """

    # Set default date range to current week if not provided
    now = datetime.now(timezone.utc)
    today = now.date()

    if not start_date:
        # Default to start of current week (Monday)
        start_date = today - timedelta(days=today.weekday())

    if not end_date:
        # Default to end of current week (Sunday)
        end_date = start_date + timedelta(days=6)

    # Convert dates to datetime objects with timezone
    start_datetime = datetime.combine(start_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end_datetime = datetime.combine(end_date, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all time logs for this dealership in the date range
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_datetime)
        .where(TimeLog.timestamp <= end_datetime)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Group time logs by employee
    employee_logs = defaultdict(list)
    for log in time_logs:
        employee_logs[log.employee_id].append(log)

    # Get all unique employee IDs for this dealership
    employee_ids = list(employee_logs.keys())

    # Calculate summary totals
    summary_total_hours = 0.0
    summary_regular_hours = 0.0
    summary_overtime_hours = 0.0
    summary_estimated_pay = 0.0

    employee_breakdown_list = []

    for employee_id in employee_ids:
        # Get employee details from Firestore
        user_details = await get_user_details(employee_id)
        employee_name = user_details.get("name", "Unknown")
        hourly_wage = user_details.get("hourly_wage", 0.0)

        # Check if employee is currently active at this dealership
        is_currently_active, _ = await is_employee_currently_active(
            session, employee_id, dealership_id
        )

        # Calculate total hours worked by this employee using helper
        logs = employee_logs[employee_id]
        # Cap the calculation at the end of the requested period
        calculation_end_time = min(now, end_datetime)
        total_hours_worked = calculate_hours_from_logs(logs, calculation_end_time)

        # Calculate regular vs overtime hours
        regular_hours, overtime_hours = calculate_regular_and_overtime_hours(
            total_hours_worked
        )

        # Calculate estimated pay with overtime
        estimated_pay = calculate_pay_with_overtime(
            regular_hours, overtime_hours, hourly_wage
        )

        # Add to summary totals
        summary_total_hours += total_hours_worked
        summary_regular_hours += regular_hours
        summary_overtime_hours += overtime_hours
        summary_estimated_pay += estimated_pay

        employee_breakdown_list.append(
            EmployeeHoursBreakdown(
                employee_id=employee_id,
                employee_name=employee_name,
                hourly_wage=hourly_wage,
                total_hours=round(total_hours_worked, 2),
                regular_hours=round(regular_hours, 2),
                overtime_hours=round(overtime_hours, 2),
                estimated_pay=round(estimated_pay, 2),
                is_currently_active=is_currently_active,
            )
        )

    # Sort by total hours (highest first) for better overview
    employee_breakdown_list.sort(key=lambda x: x.total_hours, reverse=True)

    # Create summary dictionary
    summary = {
        "total_hours": round(summary_total_hours, 2),
        "regular_hours": round(summary_regular_hours, 2),
        "overtime_hours": round(summary_overtime_hours, 2),
        "estimated_total_pay": round(summary_estimated_pay, 2),
        "employee_count": len(employee_breakdown_list),
        "average_hours_per_employee": round(
            (
                summary_total_hours / len(employee_breakdown_list)
                if employee_breakdown_list
                else 0
            ),
            2,
        ),
    }

    return DealershipEmployeeHoursResponse(
        dealership_id=dealership_id,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        employees=employee_breakdown_list,
        summary=summary,
    )


def calculate_dealership_weekly_breakdown(
    logs: List[TimeLog],
    target_dealership_id: str,
    hourly_wage: float,
    current_time: datetime,
) -> Dict[str, float]:
    """
    Calculates a breakdown of hours and cost for a single dealership from a list of
    an employee's logs, correctly attributing regular vs. overtime hours chronologically.
    """
    if not logs:
        return {"total": 0.0, "regular": 0.0, "overtime": 0.0, "cost": 0.0}

    sorted_logs = sorted(logs, key=lambda x: x.timestamp)

    breakdown = {"total": 0.0, "regular": 0.0, "overtime": 0.0}

    cumulative_hours_this_week = 0.0
    clock_in_log: Optional[TimeLog] = None

    # Process logs into pairs of (start, end) to represent shifts
    processed_shifts = []
    for log in sorted_logs:
        if log.punch_type == PunchType.CLOCK_IN:
            if clock_in_log:  # Implicit clock-out
                processed_shifts.append({"start": clock_in_log, "end": log})
            clock_in_log = log
        elif log.punch_type == PunchType.CLOCK_OUT:
            if clock_in_log:
                processed_shifts.append({"start": clock_in_log, "end": log})
                clock_in_log = None

    # Account for a shift that is still open
    if clock_in_log:
        # Create a temporary 'end' log at the current time to cap the shift
        end_log = TimeLog(
            timestamp=current_time,
            punch_type=PunchType.CLOCK_OUT,
            employee_id="",
            dealership_id="",
        )
        processed_shifts.append({"start": clock_in_log, "end": end_log})

    # Iterate through the processed shifts to calculate hours
    for shift in processed_shifts:
        start_log = shift["start"]
        end_log = shift["end"]

        start_ts = start_log.timestamp
        if start_ts.tzinfo is None:
            start_ts = start_ts.replace(tzinfo=timezone.utc)

        end_ts = end_log.timestamp
        if end_ts.tzinfo is None:
            end_ts = end_ts.replace(tzinfo=timezone.utc)

        raw_hours = (end_ts - start_ts).total_seconds() / 3600
        paid_hours = apply_unpaid_break(raw_hours)

        # Only add to dealership breakdown if the shift started at the target dealership
        if start_log.dealership_id == target_dealership_id:
            remaining_before_ot = 40.0 - cumulative_hours_this_week

            if remaining_before_ot <= 0:
                # All hours for this shift are overtime
                breakdown["overtime"] += paid_hours
            elif paid_hours <= remaining_before_ot:
                # All hours for this shift are regular
                breakdown["regular"] += paid_hours
            else:
                # A mix of regular and overtime hours
                regular_part = remaining_before_ot
                overtime_part = paid_hours - regular_part
                breakdown["regular"] += regular_part
                breakdown["overtime"] += overtime_part

        # IMPORTANT: Always update cumulative hours with hours from all dealerships
        # to correctly track when the 40-hour overtime threshold is met.
        cumulative_hours_this_week += paid_hours

    breakdown["total"] = breakdown["regular"] + breakdown["overtime"]
    breakdown["cost"] = calculate_pay_with_overtime(
        breakdown["regular"], breakdown["overtime"], hourly_wage
    )

    return breakdown


@router.get(
    "/dealership/{dealership_id}/comprehensive-labor-spend",
    response_model=ComprehensiveLaborSpendResponse,
)
async def get_comprehensive_labor_spend(
    dealership_id: str,
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_or_supervisor_role),
):
    """
    Get absolutely comprehensive labor spend information for a dealership.

    This endpoint returns EVERYTHING you could want to know about labor costs:
    - All employees (active and inactive)
    - Individual and total labor costs for today
    - Vacation costs
    - Current rates and averages
    - Weekly aggregates
    - Clock activity
    - Cost efficiency metrics
    - Top performers
    """
    print(
        f"\n--- Starting comprehensive labor spend analysis for dealership: {dealership_id} ---"
    )

    # Current time and date setup
    now = datetime.now(timezone.utc)

    # If a target date is not provided, default to the current date in US/Eastern timezone
    # to better align with user expectations.
    if target_date:
        analysis_date = target_date
    else:
        analysis_date = datetime.now(ZoneInfo("America/New_York")).date()

    # Define the boundaries for the analysis date. All calculations will be based on this day.
    analysis_tz = ZoneInfo("America/New_York")
    start_of_analysis_day = datetime.combine(
        analysis_date, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_analysis_day = datetime.combine(
        analysis_date, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    # Current week boundaries (Monday to Sunday) based on the analysis date
    current_week_start = analysis_date - timedelta(days=analysis_date.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    start_of_week = datetime.combine(
        current_week_start, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_week = datetime.combine(
        current_week_end, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    print(
        f"Analysis period (UTC) - Day: {start_of_analysis_day} to {end_of_analysis_day}"
    )
    print(f"Analysis period (UTC) - Week: {start_of_week} to {end_of_week}")

    # Get ALL employees from Firestore (not just those who clocked in)
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    all_employees = {}
    for doc in users_ref:
        user_data = doc.to_dict()
        # --- Dealership assignment check ---
        # Parse "dealerships" field
        raw_dealerships = user_data.get("dealerships", "")
        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [
                s.strip() for s in str(raw_dealerships).split(",") if s.strip()
            ]

        # Parse optional "timeClockDealerships" field (same format)
        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [
                s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()
            ]

        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)

        # Skip employees not assigned to this dealership
        if dealership_id not in combined_dealerships:
            continue

        employee_id = doc.id
        all_employees[employee_id] = {
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": (
                float(user_data.get("hourlyWage", 0.0))
                if user_data.get("hourlyWage")
                else 0.0
            ),
        }

    print(f"Found {len(all_employees)} total employees assigned to {dealership_id}")

    # ALSO get employees who have clocked in at this dealership recently (like active/all does)
    # This ensures we catch employees working here who aren't formally assigned
    lookback_date = datetime.now(timezone.utc) - timedelta(days=2)
    recent_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= lookback_date)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Get unique employee IDs who have clocked at this dealership recently
    recent_employee_ids = set(clock.employee_id for clock in recent_clocks)
    print(
        f"Found {len(recent_employee_ids)} employees who have clocked in at {dealership_id} recently"
    )

    # For recently clocked employees not already in our list, fetch their details
    for employee_id in recent_employee_ids:
        if employee_id not in all_employees:
            # Get this employee's details from Firestore
            try:
                user_details = await get_user_details(employee_id)
                all_employees[employee_id] = {
                    "name": user_details.get("name", "Unknown"),
                    "hourly_wage": user_details.get("hourly_wage", 0.0),
                }
                print(
                    f"Added recently active employee {employee_id} ({user_details.get('name', 'Unknown')}) who isn't assigned to {dealership_id}"
                )
            except Exception as e:
                print(
                    f"Error fetching details for recently active employee {employee_id}: {e}"
                )
                continue

    print(
        f"Total employees to process for {dealership_id}: {len(all_employees)} (assigned + recently active)"
    )

    # Get ALL time logs for THIS WEEK for ALL RELEVANT EMPLOYEES across ALL dealerships.
    # This is crucial for correctly calculating cross-dealership implicit clock-outs.
    employee_ids = list(all_employees.keys())

    if not employee_ids:
        # No employees for this dealership, so return an empty response.
        return ComprehensiveLaborSpendResponse(
            summary=summary, employees=[], data_generated_at=now
        )

    today_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(employee_ids))
        .where(TimeLog.timestamp >= start_of_analysis_day)
        .where(TimeLog.timestamp <= end_of_analysis_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    week_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(employee_ids))
        .where(TimeLog.timestamp >= start_of_week)
        .where(TimeLog.timestamp <= end_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    print(
        f"Found {len(today_logs)} today logs and {len(week_logs)} week logs for these employees across all dealerships"
    )

    # Get vacation time for the target dealership
    vacation_today = session.exec(
        select(VacationTime)
        .where(VacationTime.dealership_id == dealership_id)
        .where(VacationTime.date == analysis_date)
    ).all()

    vacation_this_week = session.exec(
        select(VacationTime)
        .where(VacationTime.dealership_id == dealership_id)
        .where(VacationTime.date >= current_week_start)
        .where(VacationTime.date <= current_week_end)
    ).all()

    print(
        f"Found {len(vacation_today)} vacation entries for today, {len(vacation_this_week)} for this week"
    )

    # Initialize summary
    summary = DealershipLaborSpendSummary(
        dealership_id=dealership_id,
        analysis_date=analysis_date.isoformat(),
        analysis_timestamp=now,
    )

    employee_details = []
    employees_who_worked_today = set()
    employees_currently_active = set()

    # Process each employee
    for employee_id, employee_data in all_employees.items():
        try:
            employee_name = employee_data["name"]
            hourly_wage = employee_data["hourly_wage"]

            print(
                f"Processing employee: {employee_id} ({employee_name}) @ ${hourly_wage}/hr"
            )

            # Initialize employee detail
            detail = EmployeeLaborDetail(
                employee_id=employee_id,
                employee_name=employee_name,
                hourly_wage=hourly_wage,
            )

            # Check if currently active
            is_active, most_recent_clock_in_ts = await is_employee_currently_active(
                session, employee_id, dealership_id
            )
            detail.is_currently_active = is_active
            if is_active and most_recent_clock_in_ts:
                detail.current_shift_start_time = most_recent_clock_in_ts
                detail.current_shift_duration_hours = (
                    now - most_recent_clock_in_ts
                ).total_seconds() / 3600
                employees_currently_active.add(employee_id)

            # First, calculate hours worked this week BEFORE today
            employee_week_logs = [
                log for log in week_logs if log.employee_id == employee_id
            ]
            week_logs_before_today = []
            for log in employee_week_logs:
                log_ts = log.timestamp
                if log_ts.tzinfo is None:
                    log_ts = log_ts.replace(tzinfo=timezone.utc)
                if log_ts < start_of_analysis_day:
                    week_logs_before_today.append(log)
            hours_worked_before_today = calculate_hours_by_dealership_from_logs(
                week_logs_before_today, dealership_id, start_of_analysis_day
            )

            # Process today's time logs for this employee
            employee_today_logs = [
                log for log in today_logs if log.employee_id == employee_id
            ]

            if employee_today_logs:
                employees_who_worked_today.add(employee_id)

                # Count clock-ins and find first/last
                clock_ins = [
                    log
                    for log in employee_today_logs
                    if log.punch_type == PunchType.CLOCK_IN
                ]
                clock_outs = [
                    log
                    for log in employee_today_logs
                    if log.punch_type == PunchType.CLOCK_OUT
                ]

                detail.todays_clock_in_count = len(clock_ins)
                if clock_ins:
                    detail.todays_first_clock_in = min(
                        clock_ins, key=lambda x: x.timestamp
                    ).timestamp
                if clock_outs:
                    detail.todays_last_clock_out = max(
                        clock_outs, key=lambda x: x.timestamp
                    ).timestamp

                # Calculate today's total hours
                # Special handling: if the employee is currently active and their shift started before today,
                # we need to calculate how many hours they've worked TODAY from their ongoing shift
                if (
                    detail.is_currently_active
                    and detail.current_shift_start_time
                    and detail.current_shift_start_time < start_of_analysis_day
                ):
                    # Employee has been clocked in since before today - calculate hours worked today only
                    hours_since_start_of_today = (
                        now - start_of_analysis_day
                    ).total_seconds() / 3600
                    detail.todays_total_hours = hours_since_start_of_today
                else:
                    # Standard calculation for shifts that started today
                    detail.todays_total_hours = calculate_hours_by_dealership_from_logs(
                        employee_today_logs, dealership_id, now
                    )

                # Correctly allocate today's hours into regular and overtime based on weekly context
                # If employee has already worked 40+ hours this week, all of today's hours are overtime
                if hours_worked_before_today >= 40.0:
                    detail.todays_regular_hours = 0.0
                    detail.todays_overtime_hours = detail.todays_total_hours
                else:
                    # Some of today's hours may be regular, some overtime
                    remaining_regular_hours = 40.0 - hours_worked_before_today
                    detail.todays_regular_hours = min(
                        detail.todays_total_hours, remaining_regular_hours
                    )
                    detail.todays_overtime_hours = max(
                        0.0, detail.todays_total_hours - remaining_regular_hours
                    )

                detail.todays_labor_cost = calculate_pay_with_overtime(
                    detail.todays_regular_hours,
                    detail.todays_overtime_hours,
                    hourly_wage,
                )

            # Process this week's time logs for this employee
            employee_week_logs = [
                log for log in week_logs if log.employee_id == employee_id
            ]
            if employee_week_logs:
                detail.weekly_total_hours = calculate_hours_by_dealership_from_logs(
                    employee_week_logs, dealership_id, now
                )
                detail.weekly_regular_hours, detail.weekly_overtime_hours = (
                    calculate_regular_and_overtime_hours(detail.weekly_total_hours)
                )
                detail.weekly_labor_cost = calculate_pay_with_overtime(
                    detail.weekly_regular_hours,
                    detail.weekly_overtime_hours,
                    hourly_wage,
                )

            # Process vacation for today
            employee_vacation_today = [
                v for v in vacation_today if v.employee_id == employee_id
            ]
            if employee_vacation_today:
                detail.todays_vacation_hours = sum(
                    v.hours for v in employee_vacation_today
                )
                detail.todays_vacation_cost = detail.todays_vacation_hours * hourly_wage

            # Calculate total cost for today (work + vacation)
            detail.todays_total_cost = (
                detail.todays_labor_cost + detail.todays_vacation_cost
            )

            employee_details.append(detail)

            # Add to summary totals
            summary.todays_total_work_hours += detail.todays_total_hours
            summary.todays_total_vacation_hours += detail.todays_vacation_hours
            summary.todays_total_work_cost += detail.todays_labor_cost
            summary.todays_total_vacation_cost += detail.todays_vacation_cost
            summary.todays_regular_hours += detail.todays_regular_hours
            summary.todays_overtime_hours += detail.todays_overtime_hours

            # --- Weekly Calculations ---
            # First, calculate totals for the individual employee detail (across all dealerships)
            employee_week_logs = [
                log for log in week_logs if log.employee_id == employee_id
            ]
            if employee_week_logs:
                employee_total_weekly_hours = calculate_hours_from_logs(
                    employee_week_logs, now
                )
                detail.weekly_total_hours = employee_total_weekly_hours
                detail.weekly_regular_hours, detail.weekly_overtime_hours = (
                    calculate_regular_and_overtime_hours(employee_total_weekly_hours)
                )
                detail.weekly_labor_cost = calculate_pay_with_overtime(
                    detail.weekly_regular_hours,
                    detail.weekly_overtime_hours,
                    hourly_wage,
                )

            # Second, calculate the dealership-specific breakdown for the main summary
            dealership_weekly_breakdown = calculate_dealership_weekly_breakdown(
                employee_week_logs, dealership_id, hourly_wage, now
            )

            # Add dealership-specific weekly hours and costs to the main summary
            employee_week_vacation = [
                v for v in vacation_this_week if v.employee_id == employee_id
            ]
            weekly_vacation_hours = sum(v.hours for v in employee_week_vacation)
            weekly_vacation_cost = weekly_vacation_hours * hourly_wage

            summary.weekly_total_hours += (
                dealership_weekly_breakdown["total"] + weekly_vacation_hours
            )
            summary.weekly_regular_hours += dealership_weekly_breakdown["regular"]
            summary.weekly_overtime_hours += dealership_weekly_breakdown["overtime"]
            summary.weekly_total_cost += (
                dealership_weekly_breakdown["cost"] + weekly_vacation_cost
            )

            if is_active:
                summary.current_hourly_labor_rate += hourly_wage

        except Exception as e:
            print(
                f"--- ERROR processing employee {employee_id} ({employee_data.get('name', 'Unknown')}) ---"
            )
            print(f"Error: {e}")
            # Optionally, re-raise if you want to stop execution, or just continue
            # For robustness, we'll log and continue
            continue

    # Calculate summary metrics
    summary.total_employees = len(all_employees)
    summary.active_employees_today = len(
        employees_who_worked_today | employees_currently_active
    )
    summary.employees_who_clocked_in_today = len(employees_who_worked_today)
    summary.employees_currently_clocked_in = len(employees_currently_active)

    summary.todays_total_combined_hours = (
        summary.todays_total_work_hours + summary.todays_total_vacation_hours
    )
    summary.todays_total_labor_cost = (
        summary.todays_total_work_cost + summary.todays_total_vacation_cost
    )

    # Calculate regular vs overtime costs
    total_regular_cost = 0.0
    total_overtime_cost = 0.0
    total_wages = 0.0
    total_weighted_hours = 0.0

    for detail in employee_details:
        if detail.hourly_wage and detail.hourly_wage > 0:
            total_wages += detail.hourly_wage
            if detail.todays_total_hours > 0:
                total_weighted_hours += detail.todays_total_hours * detail.hourly_wage

            # Calculate regular and overtime costs
            total_regular_cost += detail.todays_regular_hours * detail.hourly_wage
            total_overtime_cost += (
                detail.todays_overtime_hours * detail.hourly_wage * 1.5
            )

    summary.todays_regular_cost = total_regular_cost
    summary.todays_overtime_cost = total_overtime_cost

    # Calculate averages safely
    if summary.total_employees > 0:
        summary.average_hourly_wage = total_wages / summary.total_employees
        summary.cost_per_employee_today = (
            summary.todays_total_labor_cost / summary.total_employees
        )
        summary.hours_per_employee_today = (
            summary.todays_total_combined_hours / summary.total_employees
        )
    else:
        summary.average_hourly_wage = 0.0
        summary.cost_per_employee_today = 0.0
        summary.hours_per_employee_today = 0.0

    if summary.todays_total_combined_hours > 0:
        summary.weighted_average_hourly_rate = (
            total_weighted_hours / summary.todays_total_combined_hours
        )
    else:
        summary.weighted_average_hourly_rate = 0.0

    # Count clock activities
    summary.total_clock_ins_today = len(
        [log for log in today_logs if log.punch_type == PunchType.CLOCK_IN]
    )
    summary.total_clock_outs_today = len(
        [log for log in today_logs if log.punch_type == PunchType.CLOCK_OUT]
    )

    # Sort employees for insights
    employee_details.sort(key=lambda x: x.employee_name or "")

    # Top performers
    top_earners = sorted(
        employee_details, key=lambda x: x.todays_total_cost, reverse=True
    )[:5]
    most_hours = sorted(
        employee_details, key=lambda x: x.todays_total_hours, reverse=True
    )[:5]

    print(
        f"Analysis complete. Summary: {summary.total_employees} employees, ${summary.todays_total_labor_cost:.2f} total cost today"
    )

    return ComprehensiveLaborSpendResponse(
        summary=summary,
        employees=employee_details,
        top_earners_today=top_earners,
        most_hours_today=most_hours,
        data_generated_at=now,
    )


def calculate_hours_from_logs(logs: List[TimeLog], current_time: datetime) -> float:
    """Calculate total hours from a list of time logs"""
    if not logs:
        return 0.0

    # Sort logs by timestamp
    sorted_logs = sorted(logs, key=lambda x: x.timestamp)

    total_hours = 0.0
    clock_in_time = None

    for log in sorted_logs:
        log_ts = log.timestamp
        if log_ts.tzinfo is None:
            log_ts = log_ts.replace(tzinfo=timezone.utc)

        if log.punch_type == PunchType.CLOCK_IN:
            # If there's already an open shift, close it at the moment of this new CLOCK_IN
            if clock_in_time is not None:
                raw_hours = (log_ts - clock_in_time).total_seconds() / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                total_hours += paid_hours
            # Start new shift window
            clock_in_time = log_ts
        elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            raw_hours = (log_ts - clock_in_time).total_seconds() / 3600
            paid_hours = apply_unpaid_break(raw_hours)
            total_hours += paid_hours
            clock_in_time = None

    # If still clocked in, add time until current_time
    if clock_in_time:
        raw_hours = (current_time - clock_in_time).total_seconds() / 3600
        paid_hours = apply_unpaid_break(raw_hours)
        total_hours += paid_hours

    return total_hours


def calculate_hours_from_logs_with_daily_breaks(
    logs: List[TimeLog], current_time: datetime
) -> float:
    """Calculate total hours from a list of time logs with DAILY break deductions.

    Business rule: One 30-minute lunch break per day if daily total >= 5 hours,
    regardless of how many shifts or dealerships the employee worked.

    Args:
        logs: List of TimeLog entries for an employee
        current_time: Current time for calculating open shifts

    Returns:
        float: Total paid hours with daily break deductions applied
    """
    if not logs:
        return 0.0

    # Sort logs by timestamp
    sorted_logs = sorted(logs, key=lambda x: x.timestamp)

    # Group shifts by day and calculate raw hours
    shifts_by_day = {}  # date -> [(raw_hours, dealership_id), ...]
    clock_in_time = None
    clock_in_dealership = None

    for log in sorted_logs:
        log_ts = log.timestamp
        if log_ts.tzinfo is None:
            log_ts = log_ts.replace(tzinfo=timezone.utc)

        if log.punch_type == PunchType.CLOCK_IN:
            # If there's already an open shift, close it at the moment of this new CLOCK_IN
            if clock_in_time is not None:
                raw_hours = (log_ts - clock_in_time).total_seconds() / 3600

                # Get the date for this shift (use clock_in date for consistency)
                shift_date = clock_in_time.date()

                if shift_date not in shifts_by_day:
                    shifts_by_day[shift_date] = []
                shifts_by_day[shift_date].append((raw_hours, clock_in_dealership))

            # Start new shift window
            clock_in_time = log_ts
            clock_in_dealership = log.dealership_id

        elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            raw_hours = (log_ts - clock_in_time).total_seconds() / 3600

            # Get the date for this shift (use clock_in date for consistency)
            shift_date = clock_in_time.date()

            if shift_date not in shifts_by_day:
                shifts_by_day[shift_date] = []
            shifts_by_day[shift_date].append((raw_hours, clock_in_dealership))

            clock_in_time = None
            clock_in_dealership = None

    # If still clocked in, add time until current_time
    if clock_in_time:
        raw_hours = (current_time - clock_in_time).total_seconds() / 3600

        # Get the date for this shift (use clock_in date for consistency)
        shift_date = clock_in_time.date()

        if shift_date not in shifts_by_day:
            shifts_by_day[shift_date] = []
        shifts_by_day[shift_date].append((raw_hours, clock_in_dealership))

    # Apply daily break deductions
    from utils.breaks import calculate_daily_hours_with_breaks

    return calculate_daily_hours_with_breaks(shifts_by_day)


def calculate_hours_by_dealership_from_logs(
    logs: List[TimeLog], target_dealership_id: str, current_time: datetime
) -> float:
    """
    Calculates total paid hours for a specific dealership from a list of time logs,
    while correctly handling shifts implicitly closed by a clock-in at another dealership.
    """
    if not logs:
        return 0.0

    sorted_logs = sorted(logs, key=lambda x: x.timestamp)

    dealership_hours = 0.0
    clock_in_log: Optional[TimeLog] = None

    for log in sorted_logs:
        log_ts = log.timestamp
        if log_ts.tzinfo is None:
            log_ts = log_ts.replace(tzinfo=timezone.utc)

        is_clock_in = log.punch_type == PunchType.CLOCK_IN
        is_clock_out = log.punch_type == PunchType.CLOCK_OUT

        if clock_in_log:
            # A shift is currently open. This new log might close it.
            is_new_shift_at_different_dealership = (
                is_clock_in and log.dealership_id != clock_in_log.dealership_id
            )

            # A shift is closed by either an explicit CLOCK_OUT or an implicit one (a CLOCK_IN anywhere).
            if is_clock_out or is_clock_in:

                # Only calculate hours if the OPEN shift belongs to the target dealership.
                if clock_in_log.dealership_id == target_dealership_id:
                    clock_in_ts = clock_in_log.timestamp
                    if clock_in_ts.tzinfo is None:
                        clock_in_ts = clock_in_ts.replace(tzinfo=timezone.utc)

                    raw_hours = (log_ts - clock_in_ts).total_seconds() / 3600
                    paid_hours = apply_unpaid_break(raw_hours)
                    dealership_hours += paid_hours

                # If this log is a clock_in, it starts the next shift. Otherwise, no shift is open.
                clock_in_log = log if is_clock_in else None

        elif is_clock_in:
            # No shift was open, so this log starts a new one.
            clock_in_log = log

    # After the loop, check if a shift is still open.
    if clock_in_log and clock_in_log.dealership_id == target_dealership_id:
        clock_in_ts = clock_in_log.timestamp
        if clock_in_ts.tzinfo is None:
            clock_in_ts = clock_in_ts.replace(tzinfo=timezone.utc)

        raw_hours = (current_time - clock_in_ts).total_seconds() / 3600
        paid_hours = apply_unpaid_break(raw_hours)
        dealership_hours += paid_hours

    return dealership_hours


@router.get(
    "/dealership/{dealership_id}/labor-preview", response_model=QuickLaborPreview
)
async def get_labor_preview(
    dealership_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Quick preview of labor spending for a dealership TODAY.

    Returns essential metrics for current day's labor costs without detailed breakdowns.
    Perfect for dashboards, status displays, or quick checks.

    Shows:
    - Total money spent on labor so far today
    - Current employees clocked in
    - Current hourly burn rate
    - Projected daily spending
    """
    print(f"\n--- Getting labor preview for dealership: {dealership_id} ---")

    # Current time and today's boundaries
    now = datetime.now(timezone.utc)
    today = now.date()
    start_of_today = datetime.combine(today, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end_of_today = datetime.combine(today, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    # Get all employees with their wages
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    employee_wages = {}
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        hourly_wage = (
            float(user_data.get("hourlyWage", 0.0))
            if user_data.get("hourlyWage")
            else 0.0
        )
        employee_wages[employee_id] = hourly_wage

    # Get today's time logs for this dealership
    today_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_of_today)
        .where(TimeLog.timestamp <= end_of_today)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Get today's vacation time for this dealership
    vacation_today = session.exec(
        select(VacationTime)
        .where(VacationTime.dealership_id == dealership_id)
        .where(VacationTime.date == today)
    ).all()

    print(
        f"Found {len(today_logs)} time logs and {len(vacation_today)} vacation entries for today"
    )

    # Initialize counters
    total_work_cost = 0.0
    total_vacation_cost = 0.0
    total_work_hours = 0.0
    total_vacation_hours = 0.0
    current_burn_rate = 0.0
    employees_who_worked = set()
    employees_currently_active = set()

    # Group logs by employee
    employee_logs = {}
    for log in today_logs:
        if log.employee_id not in employee_logs:
            employee_logs[log.employee_id] = []
        employee_logs[log.employee_id].append(log)
        employees_who_worked.add(log.employee_id)

    # Calculate work costs and hours for each employee
    for employee_id, logs in employee_logs.items():
        hourly_wage = employee_wages.get(employee_id, 0.0)

        # Calculate hours worked today
        hours_worked = calculate_hours_from_logs(logs, now)
        total_work_hours += hours_worked

        # Calculate cost (with overtime)
        regular_hours, overtime_hours = calculate_regular_and_overtime_hours(
            hours_worked
        )
        cost = calculate_pay_with_overtime(regular_hours, overtime_hours, hourly_wage)
        total_work_cost += cost

        # Check if currently active
        is_active, _ = await is_employee_currently_active(
            session, employee_id, dealership_id
        )
        if is_active:
            employees_currently_active.add(employee_id)
            current_burn_rate += hourly_wage

    # Calculate vacation costs
    for vacation in vacation_today:
        employee_id = vacation.employee_id
        hourly_wage = employee_wages.get(employee_id, 0.0)
        vacation_cost = vacation.hours * hourly_wage
        total_vacation_cost += vacation_cost
        total_vacation_hours += vacation.hours

    # Calculate projections
    # Project daily cost based on current burn rate and hours remaining in workday
    # Assume 8-hour workday, adjust based on current time
    hours_into_workday = (
        (now.hour - 8) if now.hour >= 8 else 0
    )  # Assume workday starts at 8 AM
    hours_remaining_in_workday = max(0, 8 - hours_into_workday)  # Assume 8-hour workday
    projected_additional_cost = current_burn_rate * hours_remaining_in_workday
    projected_daily_cost = total_work_cost + projected_additional_cost

    # Calculate averages
    total_employees_today = len(employees_who_worked)
    average_cost_per_employee = (
        (total_work_cost + total_vacation_cost) / total_employees_today
        if total_employees_today > 0
        else 0.0
    )

    print(
        f"Preview calculated: ${total_work_cost + total_vacation_cost:.2f} total cost, {len(employees_currently_active)} currently active"
    )

    return QuickLaborPreview(
        dealership_id=dealership_id,
        current_time=now,
        total_labor_cost_today=total_work_cost + total_vacation_cost,
        total_work_cost_today=total_work_cost,
        total_vacation_cost_today=total_vacation_cost,
        total_hours_today=total_work_hours + total_vacation_hours,
        total_work_hours_today=total_work_hours,
        total_vacation_hours_today=total_vacation_hours,
        employees_currently_clocked_in=len(employees_currently_active),
        employees_who_worked_today=len(employees_who_worked),
        current_hourly_burn_rate=current_burn_rate,
        average_cost_per_employee_today=average_cost_per_employee,
        projected_daily_cost=projected_daily_cost,
    )


@router.get(
    "/all-dealerships/labor-costs-today", response_model=AllDealershipsLaborCostResponse
)
async def get_all_dealerships_labor_costs_today(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_or_supervisor_role),
):
    """
    Get today's total labor costs for ALL dealerships.

    Super lightweight endpoint that returns just the money spent on labor today
    for each dealership. Perfect for company-wide dashboard overview.

    Now uses the same robust calculation logic as comprehensive endpoint:
    - Proper weekly overtime calculation
    - Correct dealership assignment handling
    - Eastern timezone for business day boundaries
    - Cross-dealership hour attribution

    Returns:
    - Each dealership's total labor cost today (work + vacation)
    - Company-wide total
    - Current timestamp
    """
    print(f"\n--- Getting labor costs for all dealerships ---")

    # Use Eastern timezone for business day boundaries
    from zoneinfo import ZoneInfo

    analysis_tz = ZoneInfo("America/New_York")
    now = datetime.now(timezone.utc)
    today = now.astimezone(analysis_tz).date()

    start_of_today = datetime.combine(
        today, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_today = datetime.combine(
        today, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    # Current week boundaries for overtime calculation
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    start_of_week = datetime.combine(
        current_week_start, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_week = datetime.combine(
        current_week_end, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    print(f"Analysis period (UTC) - Day: {start_of_today} to {end_of_today}")
    print(f"Analysis period (UTC) - Week: {start_of_week} to {end_of_week}")

    # Get all dealerships
    dealerships_ref = firestore_db.collection("dealerships").stream()
    dealership_ids = [doc.id for doc in dealerships_ref]

    print(f"Found {len(dealership_ids)} dealerships to analyze")

    # Get ALL employees from Firestore with proper dealership assignments
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    all_employees = {}
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id

        # Parse dealership assignments
        raw_dealerships = user_data.get("dealerships", "")
        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [
                s.strip() for s in str(raw_dealerships).split(",") if s.strip()
            ]

        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [
                s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()
            ]

        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)

        all_employees[employee_id] = {
            "hourly_wage": (
                float(user_data.get("hourlyWage", 0.0))
                if user_data.get("hourlyWage")
                else 0.0
            ),
            "dealerships": combined_dealerships,
        }

    print(f"Found {len(all_employees)} total employees")

    if not all_employees:
        return AllDealershipsLaborCostResponse(
            analysis_date=today.isoformat(),
            total_company_labor_cost=0.0,
            dealerships=[],
            analysis_time=now,
        )

    employee_ids = list(all_employees.keys())

    # Get all time logs for today and this week
    today_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(employee_ids))
        .where(TimeLog.timestamp >= start_of_today)
        .where(TimeLog.timestamp <= end_of_today)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    week_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id.in_(employee_ids))
        .where(TimeLog.timestamp >= start_of_week)
        .where(TimeLog.timestamp <= end_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Get all vacation for today
    all_vacation_today = session.exec(
        select(VacationTime).where(VacationTime.date == today)
    ).all()

    print(
        f"Found {len(today_logs)} today logs, {len(week_logs)} week logs, {len(all_vacation_today)} vacation entries"
    )

    # Calculate costs for each dealership
    dealership_costs = []
    total_company_cost = 0.0

    for dealership_id in dealership_ids:
        dealership_total_cost = 0.0

        # Get employees assigned to this dealership
        dealership_employees = [
            emp_id
            for emp_id, emp_data in all_employees.items()
            if dealership_id in emp_data["dealerships"]
        ]

        if not dealership_employees:
            dealership_costs.append(
                DealershipLaborCost(
                    dealership_id=dealership_id, total_labor_cost_today=0.0
                )
            )
            continue

        # Calculate work costs for employees assigned to this dealership
        for employee_id in dealership_employees:
            try:
                employee_data = all_employees[employee_id]
                hourly_wage = employee_data["hourly_wage"]

                # Get this employee's logs
                employee_today_logs = [
                    log for log in today_logs if log.employee_id == employee_id
                ]
                employee_week_logs = [
                    log for log in week_logs if log.employee_id == employee_id
                ]

                if not employee_today_logs:
                    continue

                # Calculate hours worked this week BEFORE today for overtime context
                week_logs_before_today = []
                for log in employee_week_logs:
                    log_ts = log.timestamp
                    if log_ts.tzinfo is None:
                        log_ts = log_ts.replace(tzinfo=timezone.utc)
                    if log_ts < start_of_today:
                        week_logs_before_today.append(log)

                hours_worked_before_today = calculate_hours_from_logs(
                    week_logs_before_today, start_of_today
                )

                # Calculate today's hours for this dealership
                todays_hours = calculate_hours_by_dealership_from_logs(
                    employee_today_logs, dealership_id, now
                )

                if todays_hours <= 0:
                    continue

                # Calculate regular vs overtime hours based on weekly context
                if hours_worked_before_today >= 40.0:
                    # All of today's hours are overtime
                    regular_hours = 0.0
                    overtime_hours = todays_hours
                else:
                    # Some may be regular, some overtime
                    remaining_regular_hours = 40.0 - hours_worked_before_today
                    regular_hours = min(todays_hours, remaining_regular_hours)
                    overtime_hours = max(0.0, todays_hours - remaining_regular_hours)

                # Calculate cost with proper overtime pay
                labor_cost = calculate_pay_with_overtime(
                    regular_hours, overtime_hours, hourly_wage
                )
                dealership_total_cost += labor_cost

            except Exception as e:
                print(
                    f"Error processing employee {employee_id} for dealership {dealership_id}: {e}"
                )
                continue

        # Calculate vacation costs for this dealership
        dealership_vacations = [
            v for v in all_vacation_today if v.dealership_id == dealership_id
        ]
        for vacation in dealership_vacations:
            employee_data = all_employees.get(vacation.employee_id)
            if employee_data:
                hourly_wage = employee_data["hourly_wage"]
                vacation_cost = vacation.hours * hourly_wage
                dealership_total_cost += vacation_cost

        dealership_costs.append(
            DealershipLaborCost(
                dealership_id=dealership_id,
                total_labor_cost_today=dealership_total_cost,
            )
        )
        total_company_cost += dealership_total_cost

        print(f"Dealership {dealership_id}: ${dealership_total_cost:.2f}")

    # Sort by cost (highest first)
    dealership_costs.sort(key=lambda x: x.total_labor_cost_today, reverse=True)

    print(f"Total company labor cost today: ${total_company_cost:.2f}")

    return AllDealershipsLaborCostResponse(
        analysis_date=today.isoformat(),
        total_company_labor_cost=total_company_cost,
        dealerships=dealership_costs,
        analysis_time=now,
    )


# --- New Basic Weekly Summary Models ---
class BasicEmployeeWeeklySummary(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    hourly_wage: float = 0.0
    weekly_total_hours: float = 0.0
    weekly_regular_hours: float = 0.0
    weekly_overtime_hours: float = 0.0
    weekly_pay: float = 0.0
    current_clock_in_duration_hours: float = 0.0


# --- New Endpoint ---
@router.get(
    "/employees/basic-weekly-summary", response_model=List[BasicEmployeeWeeklySummary]
)
async def get_basic_weekly_summary(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """Return a fast, lightweight weekly summary for ALL employees.

    Optional date range parameters (UTC):
    - start_date: Start date for analysis (defaults to start of current week)
    - end_date: End date for analysis (defaults to end of current week)
    """
    import time

    start_time = time.time()
    now = datetime.now(timezone.utc)
    print(f"[WEEKLY_SUMMARY] Starting basic weekly summary at {now}")
    print(f"[WEEKLY_SUMMARY] Date range: {start_date} to {end_date}")

    if start_date and end_date:
        # Use provided date range (passed in UTC)
        week_start = start_date
        week_end = end_date
    else:
        # Use current week calculation (existing logic)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

    start_dt = datetime.combine(week_start, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    end_dt = datetime.combine(week_end, datetime.max.time()).replace(
        tzinfo=timezone.utc
    )

    step_time = time.time()
    print(
        f"[WEEKLY_SUMMARY] Date calculation completed in {step_time - start_time:.2f}s"
    )

    # Fetch all time logs for the current week once
    print(f"[WEEKLY_SUMMARY] Fetching time logs from {start_dt} to {end_dt}")
    week_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_dt)
        .where(TimeLog.timestamp <= end_dt)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    fetch_time = time.time()
    print(
        f"[WEEKLY_SUMMARY] Fetched {len(week_logs)} time logs in {fetch_time - step_time:.2f}s"
    )

    # Ensure timestamps are tz-aware
    for log in week_logs:
        if log.timestamp.tzinfo is None:
            log.timestamp = log.timestamp.replace(tzinfo=timezone.utc)

    # Group logs by employee
    employee_logs: Dict[str, List[TimeLog]] = {}
    for log in week_logs:
        employee_logs.setdefault(log.employee_id, []).append(log)

    group_time = time.time()
    print(
        f"[WEEKLY_SUMMARY] Grouped logs by {len(employee_logs)} employees in {group_time - fetch_time:.2f}s"
    )

    # Get employee wage and name info from Firestore in one pass
    print(f"[WEEKLY_SUMMARY] Fetching employee data from Firestore...")
    users_ref = (
        firestore_db.collection("users")
        .where(
            "role",
            "in",
            ["employee", "clockOnlyEmployee", "serviceWash", "photos", "lotPrep"],
        )
        .stream()
    )
    employee_wages: Dict[str, Dict[str, Any]] = {}
    for doc in users_ref:
        data = doc.to_dict()
        employee_wages[doc.id] = {
            "name": data.get("displayName", "Unknown"),
            "hourly_wage": (
                float(data.get("hourlyWage", 0.0)) if data.get("hourlyWage") else 0.0
            ),
        }

    firestore_time = time.time()
    print(
        f"[WEEKLY_SUMMARY] Fetched {len(employee_wages)} employee records from Firestore in {firestore_time - group_time:.2f}s"
    )

    # Batch query to get current active status for all employees
    lookback_date = now - timedelta(days=3)
    all_employee_ids = list(employee_wages.keys())

    print(
        f"[WEEKLY_SUMMARY] Fetching active status for {len(all_employee_ids)} employees..."
    )

    # OPTIMIZATION: Process in smaller batches to avoid overwhelming the database
    # Instead of one massive query, break into manageable chunks
    employee_active_status = {}
    batch_size = 25

    for i in range(0, len(all_employee_ids), batch_size):
        batch_ids = all_employee_ids[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(all_employee_ids) + batch_size - 1) // batch_size
        print(
            f"[WEEKLY_SUMMARY] Processing batch {batch_num}/{total_batches} ({len(batch_ids)} employees)"
        )

        # Get recent clocks for this batch only - much smaller query
        batch_clocks = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id.in_(batch_ids))
            .where(TimeLog.timestamp >= lookback_date)
            .order_by(TimeLog.timestamp.desc())
        ).all()

        print(
            f"[WEEKLY_SUMMARY] Batch {batch_num} returned {len(batch_clocks)} clock entries"
        )

        # Process this batch
        for clock in batch_clocks:
            if clock.employee_id not in employee_active_status:
                # Ensure timestamp is timezone-aware
                ts = (
                    clock.timestamp.replace(tzinfo=timezone.utc)
                    if clock.timestamp.tzinfo is None
                    else clock.timestamp
                )

                # Employee is active if their most recent clock was a CLOCK_IN
                is_active = clock.punch_type == PunchType.CLOCK_IN
                employee_active_status[clock.employee_id] = (
                    is_active,
                    ts if is_active else None,
                )

    active_fetch_time = time.time()
    print(
        f"[WEEKLY_SUMMARY] Completed active status processing for {len(employee_active_status)} employees in {active_fetch_time - firestore_time:.2f}s"
    )

    summaries: List[BasicEmployeeWeeklySummary] = []

    print(
        f"[WEEKLY_SUMMARY] Processing {len(employee_wages)} employees for summary calculations..."
    )
    process_start = time.time()
    processed_count = 0

    for employee_id, info in employee_wages.items():
        processed_count += 1
        if processed_count % 50 == 0:  # Log every 50 employees processed
            current_time = time.time()
            print(
                f"[WEEKLY_SUMMARY] Processed {processed_count}/{len(employee_wages)} employees in {current_time - process_start:.2f}s"
            )
        logs = employee_logs.get(employee_id, [])
        total_hours = calculate_hours_from_logs(logs, now)
        regular_hours, overtime_hours = calculate_regular_and_overtime_hours(
            total_hours
        )
        weekly_pay = calculate_pay_with_overtime(
            regular_hours, overtime_hours, info["hourly_wage"]
        )

        # Calculate current clock-in duration
        current_clock_in_duration = 0.0
        is_active, shift_start_time = employee_active_status.get(
            employee_id, (False, None)
        )

        if is_active and shift_start_time:
            # Ensure shift_start_time is timezone-aware
            if shift_start_time.tzinfo is None:
                shift_start_time = shift_start_time.replace(tzinfo=timezone.utc)
            duration_delta = now - shift_start_time
            current_clock_in_duration = duration_delta.total_seconds() / 3600.0

        summaries.append(
            BasicEmployeeWeeklySummary(
                employee_id=employee_id,
                employee_name=info["name"],
                hourly_wage=info["hourly_wage"],
                weekly_total_hours=round(total_hours, 2),
                weekly_regular_hours=round(regular_hours, 2),
                weekly_overtime_hours=round(overtime_hours, 2),
                weekly_pay=round(weekly_pay, 2),
                current_clock_in_duration_hours=round(current_clock_in_duration, 2),
            )
        )

    # Sort alphabetically for convenience
    summaries.sort(key=lambda x: x.employee_name or "")

    final_time = time.time()
    print(
        f"[WEEKLY_SUMMARY] Employee processing completed in {final_time - process_start:.2f}s"
    )
    print(f"[WEEKLY_SUMMARY] Total execution time: {final_time - start_time:.2f}s")
    print(f"[WEEKLY_SUMMARY] Returning {len(summaries)} employee summaries")

    return summaries


@router.get(
    "/all-dealerships/comprehensive-labor-spend",
    response_model=AllDealershipsComprehensiveLaborSpendResponse,
)
async def get_all_dealerships_comprehensive_labor_spend(
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get comprehensive labor spend information for ALL dealerships in a single call.

    This endpoint returns the EXACT same data as calling the individual comprehensive
    endpoint for each dealership, but in a single efficient operation.

    Perfect for replacing multiple parallel API calls with one optimized request.

    Returns:
    - Comprehensive labor data for each dealership
    - Company-wide totals
    - All employee details per dealership
    - Exact same calculations as individual endpoints
    """
    print(f"\n=== Starting comprehensive labor spend analysis for ALL dealerships ===")

    # Current time and date setup
    now = datetime.now(timezone.utc)

    # If a target date is not provided, default to the current date in US/Eastern timezone
    if target_date:
        analysis_date = target_date
    else:
        analysis_date = datetime.now(ZoneInfo("America/New_York")).date()

    # Define the boundaries for the analysis date
    analysis_tz = ZoneInfo("America/New_York")
    start_of_analysis_day = datetime.combine(
        analysis_date, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_analysis_day = datetime.combine(
        analysis_date, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    # Current week boundaries (Monday to Sunday) based on the analysis date
    current_week_start = analysis_date - timedelta(days=analysis_date.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    start_of_week = datetime.combine(
        current_week_start, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_week = datetime.combine(
        current_week_end, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    print(
        f"Analysis period (UTC) - Day: {start_of_analysis_day} to {end_of_analysis_day}"
    )
    print(f"Analysis period (UTC) - Week: {start_of_week} to {end_of_week}")

    # Get all dealerships
    dealerships_ref = firestore_db.collection("dealerships").stream()
    dealership_ids = [doc.id for doc in dealerships_ref]
    print(f"Found {len(dealership_ids)} dealerships to analyze")

    # Get ALL employees from Firestore with their dealership assignments
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    all_employees_by_dealership = {}  # dealership_id -> {employee_id -> employee_data}
    all_employee_ids = set()

    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id

        # Parse dealership assignments
        raw_dealerships = user_data.get("dealerships", "")
        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [
                s.strip() for s in str(raw_dealerships).split(",") if s.strip()
            ]

        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [
                s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()
            ]

        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)

        # Add employee to each dealership they're assigned to
        for dealership_id in combined_dealerships:
            if dealership_id not in all_employees_by_dealership:
                all_employees_by_dealership[dealership_id] = {}

            all_employees_by_dealership[dealership_id][employee_id] = {
                "name": user_data.get("displayName", "Unknown"),
                "hourly_wage": (
                    float(user_data.get("hourlyWage", 0.0))
                    if user_data.get("hourlyWage")
                    else 0.0
                ),
            }
            all_employee_ids.add(employee_id)

    print(
        f"Found {len(all_employee_ids)} total unique employees across all dealerships"
    )

    # Get ALL time logs for this week for ALL employees (single query)
    if all_employee_ids:
        all_today_logs = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id.in_(list(all_employee_ids)))
            .where(TimeLog.timestamp >= start_of_analysis_day)
            .where(TimeLog.timestamp <= end_of_analysis_day)
            .order_by(TimeLog.timestamp.asc())
        ).all()

        all_week_logs = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id.in_(list(all_employee_ids)))
            .where(TimeLog.timestamp >= start_of_week)
            .where(TimeLog.timestamp <= end_of_week)
            .order_by(TimeLog.timestamp.asc())
        ).all()

        print(
            f"Found {len(all_today_logs)} today logs and {len(all_week_logs)} week logs across all employees"
        )
    else:
        all_today_logs = []
        all_week_logs = []

    # Get ALL vacation time for today and this week (single query)
    all_vacation_today = session.exec(
        select(VacationTime).where(VacationTime.date == analysis_date)
    ).all()

    all_vacation_week = session.exec(
        select(VacationTime)
        .where(VacationTime.date >= current_week_start)
        .where(VacationTime.date <= current_week_end)
    ).all()

    print(
        f"Found {len(all_vacation_today)} vacation entries for today, {len(all_vacation_week)} for this week"
    )

    # Process each dealership
    dealership_results = []
    total_company_cost = 0.0
    total_company_employees = 0

    for dealership_id in sorted(dealership_ids):
        try:
            print(f"\n--- Processing dealership: {dealership_id} ---")

            # Get employees for this dealership
            dealership_employees = all_employees_by_dealership.get(dealership_id, {})

            if not dealership_employees:
                print(f"No employees assigned to {dealership_id}, skipping")
                continue

            employee_ids = list(dealership_employees.keys())
            print(f"Found {len(employee_ids)} employees assigned to {dealership_id}")

            # Filter logs for this dealership's employees
            today_logs = [
                log for log in all_today_logs if log.employee_id in employee_ids
            ]
            week_logs = [
                log for log in all_week_logs if log.employee_id in employee_ids
            ]

            # Filter vacation for this dealership
            vacation_today = [
                v for v in all_vacation_today if v.dealership_id == dealership_id
            ]
            vacation_this_week = [
                v for v in all_vacation_week if v.dealership_id == dealership_id
            ]

            # Initialize summary for this dealership
            summary = DealershipLaborSpendSummary(
                dealership_id=dealership_id,
                analysis_date=analysis_date.isoformat(),
                analysis_timestamp=now,
            )

            employee_details = []
            employees_who_worked_today = set()
            employees_currently_active = set()

            # Process each employee for this dealership (same logic as individual endpoint)
            for employee_id, employee_data in dealership_employees.items():
                try:
                    employee_name = employee_data["name"]
                    hourly_wage = employee_data["hourly_wage"]

                    # Initialize employee detail
                    detail = EmployeeLaborDetail(
                        employee_id=employee_id,
                        employee_name=employee_name,
                        hourly_wage=hourly_wage,
                    )

                    # Check if currently active
                    is_active, most_recent_clock_in_ts = (
                        await is_employee_currently_active(
                            session, employee_id, dealership_id
                        )
                    )
                    detail.is_currently_active = is_active
                    if is_active and most_recent_clock_in_ts:
                        detail.current_shift_start_time = most_recent_clock_in_ts
                        detail.current_shift_duration_hours = (
                            now - most_recent_clock_in_ts
                        ).total_seconds() / 3600
                        employees_currently_active.add(employee_id)

                    # Calculate hours worked this week BEFORE today
                    employee_week_logs = [
                        log for log in week_logs if log.employee_id == employee_id
                    ]
                    week_logs_before_today = []
                    for log in employee_week_logs:
                        log_ts = log.timestamp
                        if log_ts.tzinfo is None:
                            log_ts = log_ts.replace(tzinfo=timezone.utc)
                        if log_ts < start_of_analysis_day:
                            week_logs_before_today.append(log)
                    hours_worked_before_today = calculate_hours_by_dealership_from_logs(
                        week_logs_before_today, dealership_id, start_of_analysis_day
                    )

                    # Process today's time logs
                    employee_today_logs = [
                        log for log in today_logs if log.employee_id == employee_id
                    ]

                    if employee_today_logs:
                        employees_who_worked_today.add(employee_id)

                        # Count clock-ins and find first/last
                        clock_ins = [
                            log
                            for log in employee_today_logs
                            if log.punch_type == PunchType.CLOCK_IN
                        ]
                        clock_outs = [
                            log
                            for log in employee_today_logs
                            if log.punch_type == PunchType.CLOCK_OUT
                        ]

                        detail.todays_clock_in_count = len(clock_ins)
                        if clock_ins:
                            detail.todays_first_clock_in = min(
                                clock_ins, key=lambda x: x.timestamp
                            ).timestamp
                        if clock_outs:
                            detail.todays_last_clock_out = max(
                                clock_outs, key=lambda x: x.timestamp
                            ).timestamp

                        # Calculate today's total hours
                        if (
                            detail.is_currently_active
                            and detail.current_shift_start_time
                            and detail.current_shift_start_time < start_of_analysis_day
                        ):
                            hours_since_start_of_today = (
                                now - start_of_analysis_day
                            ).total_seconds() / 3600
                            detail.todays_total_hours = hours_since_start_of_today
                        else:
                            detail.todays_total_hours = (
                                calculate_hours_by_dealership_from_logs(
                                    employee_today_logs, dealership_id, now
                                )
                            )

                        # Allocate today's hours into regular and overtime
                        if hours_worked_before_today >= 40.0:
                            detail.todays_regular_hours = 0.0
                            detail.todays_overtime_hours = detail.todays_total_hours
                        else:
                            remaining_regular_hours = 40.0 - hours_worked_before_today
                            detail.todays_regular_hours = min(
                                detail.todays_total_hours, remaining_regular_hours
                            )
                            detail.todays_overtime_hours = max(
                                0.0, detail.todays_total_hours - remaining_regular_hours
                            )

                        detail.todays_labor_cost = calculate_pay_with_overtime(
                            detail.todays_regular_hours,
                            detail.todays_overtime_hours,
                            hourly_wage,
                        )

                    # Process this week's time logs
                    if employee_week_logs:
                        detail.weekly_total_hours = (
                            calculate_hours_by_dealership_from_logs(
                                employee_week_logs, dealership_id, now
                            )
                        )
                        detail.weekly_regular_hours, detail.weekly_overtime_hours = (
                            calculate_regular_and_overtime_hours(
                                detail.weekly_total_hours
                            )
                        )
                        detail.weekly_labor_cost = calculate_pay_with_overtime(
                            detail.weekly_regular_hours,
                            detail.weekly_overtime_hours,
                            hourly_wage,
                        )

                    # Process vacation for today
                    employee_vacation_today = [
                        v for v in vacation_today if v.employee_id == employee_id
                    ]
                    if employee_vacation_today:
                        detail.todays_vacation_hours = sum(
                            v.hours for v in employee_vacation_today
                        )
                        detail.todays_vacation_cost = (
                            detail.todays_vacation_hours * hourly_wage
                        )

                    # Calculate total cost for today
                    detail.todays_total_cost = (
                        detail.todays_labor_cost + detail.todays_vacation_cost
                    )

                    employee_details.append(detail)

                    # Add to summary totals
                    summary.todays_total_work_hours += detail.todays_total_hours
                    summary.todays_total_vacation_hours += detail.todays_vacation_hours
                    summary.todays_total_work_cost += detail.todays_labor_cost
                    summary.todays_total_vacation_cost += detail.todays_vacation_cost
                    summary.todays_regular_hours += detail.todays_regular_hours
                    summary.todays_overtime_hours += detail.todays_overtime_hours

                    # Weekly calculations
                    dealership_weekly_breakdown = calculate_dealership_weekly_breakdown(
                        employee_week_logs, dealership_id, hourly_wage, now
                    )

                    employee_week_vacation = [
                        v for v in vacation_this_week if v.employee_id == employee_id
                    ]
                    weekly_vacation_hours = sum(v.hours for v in employee_week_vacation)
                    weekly_vacation_cost = weekly_vacation_hours * hourly_wage

                    summary.weekly_total_hours += (
                        dealership_weekly_breakdown["total"] + weekly_vacation_hours
                    )
                    summary.weekly_regular_hours += dealership_weekly_breakdown[
                        "regular"
                    ]
                    summary.weekly_overtime_hours += dealership_weekly_breakdown[
                        "overtime"
                    ]
                    summary.weekly_total_cost += (
                        dealership_weekly_breakdown["cost"] + weekly_vacation_cost
                    )

                    if is_active:
                        summary.current_hourly_labor_rate += hourly_wage

                except Exception as e:
                    print(f"Error processing employee {employee_id}: {e}")
                    continue

            # Calculate summary metrics
            summary.total_employees = len(dealership_employees)
            summary.active_employees_today = len(
                employees_who_worked_today | employees_currently_active
            )
            summary.employees_who_clocked_in_today = len(employees_who_worked_today)
            summary.employees_currently_clocked_in = len(employees_currently_active)

            summary.todays_total_combined_hours = (
                summary.todays_total_work_hours + summary.todays_total_vacation_hours
            )
            summary.todays_total_labor_cost = (
                summary.todays_total_work_cost + summary.todays_total_vacation_cost
            )

            # Calculate costs and averages
            total_regular_cost = 0.0
            total_overtime_cost = 0.0
            total_wages = 0.0
            total_weighted_hours = 0.0

            for detail in employee_details:
                if detail.hourly_wage and detail.hourly_wage > 0:
                    total_wages += detail.hourly_wage
                    if detail.todays_total_hours > 0:
                        total_weighted_hours += (
                            detail.todays_total_hours * detail.hourly_wage
                        )

                    total_regular_cost += (
                        detail.todays_regular_hours * detail.hourly_wage
                    )
                    total_overtime_cost += (
                        detail.todays_overtime_hours * detail.hourly_wage * 1.5
                    )

            summary.todays_regular_cost = total_regular_cost
            summary.todays_overtime_cost = total_overtime_cost

            # Calculate averages
            if summary.total_employees > 0:
                summary.average_hourly_wage = total_wages / summary.total_employees
                summary.cost_per_employee_today = (
                    summary.todays_total_labor_cost / summary.total_employees
                )
                summary.hours_per_employee_today = (
                    summary.todays_total_combined_hours / summary.total_employees
                )

            if summary.todays_total_combined_hours > 0:
                summary.weighted_average_hourly_rate = (
                    total_weighted_hours / summary.todays_total_combined_hours
                )

            # Count clock activities
            summary.total_clock_ins_today = len(
                [log for log in today_logs if log.punch_type == PunchType.CLOCK_IN]
            )
            summary.total_clock_outs_today = len(
                [log for log in today_logs if log.punch_type == PunchType.CLOCK_OUT]
            )

            # Sort employees and get insights
            employee_details.sort(key=lambda x: x.employee_name or "")
            top_earners = sorted(
                employee_details, key=lambda x: x.todays_total_cost, reverse=True
            )[:5]
            most_hours = sorted(
                employee_details, key=lambda x: x.todays_total_hours, reverse=True
            )[:5]

            # Create comprehensive response for this dealership
            dealership_result = ComprehensiveLaborSpendResponse(
                summary=summary,
                employees=employee_details,
                top_earners_today=top_earners,
                most_hours_today=most_hours,
                data_generated_at=now,
            )

            dealership_results.append(dealership_result)
            total_company_cost += summary.todays_total_labor_cost
            total_company_employees += summary.total_employees

            print(
                f"Completed {dealership_id}: {summary.total_employees} employees, ${summary.todays_total_labor_cost:.2f} total cost"
            )

        except Exception as e:
            print(f"ERROR processing dealership {dealership_id}: {e}")
            import traceback

            traceback.print_exc()
            continue

    # Sort dealerships by total cost (highest first)
    dealership_results.sort(
        key=lambda x: x.summary.todays_total_labor_cost, reverse=True
    )

    print(
        f"\n=== Analysis complete: {len(dealership_results)} dealerships, ${total_company_cost:.2f} total cost ==="
    )

    return AllDealershipsComprehensiveLaborSpendResponse(
        analysis_date=analysis_date.isoformat(),
        analysis_timestamp=now,
        total_company_labor_cost=total_company_cost,
        total_company_employees=total_company_employees,
        dealerships=dealership_results,
    )


def calculate_date_range_overtime(
    logs: List[TimeLog],
    target_dealership_id: str,
    start_date: date,
    end_date: date,
    current_time: datetime,
) -> Tuple[float, float]:
    """
    Calculate regular and overtime hours for a date range, properly accounting for weekly context.

    This function replicates the exact overtime logic from the original endpoints but across
    a date range that may span multiple weeks.

    Returns: (regular_hours, overtime_hours)
    """
    if not logs:
        return 0.0, 0.0

    # Filter logs for the target dealership and sort by timestamp
    dealership_logs = [log for log in logs if log.dealership_id == target_dealership_id]
    if not dealership_logs:
        return 0.0, 0.0

    sorted_logs = sorted(dealership_logs, key=lambda x: x.timestamp)

    total_regular_hours = 0.0
    total_overtime_hours = 0.0

    # Process each week in the date range
    current_date = start_date
    while current_date <= end_date:
        # Find the start of the week (Monday) for this date
        week_start = current_date - timedelta(days=current_date.weekday())
        week_end = week_start + timedelta(days=6)

        # Get logs for this week
        analysis_tz = ZoneInfo("America/New_York")
        week_start_utc = datetime.combine(
            week_start, datetime.min.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)
        week_end_utc = datetime.combine(
            week_end, datetime.max.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)

        week_logs = []
        for log in sorted_logs:
            log_ts = log.timestamp
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=timezone.utc)
            if week_start_utc <= log_ts <= week_end_utc:
                week_logs.append(log)

        if week_logs:
            # Process this week day by day to calculate proper overtime allocation
            week_regular, week_overtime = calculate_weekly_overtime_by_day(
                week_logs,
                target_dealership_id,
                week_start,
                week_end,
                start_date,
                end_date,
                current_time,
            )
            total_regular_hours += week_regular
            total_overtime_hours += week_overtime

        # Move to next week
        current_date = week_end + timedelta(days=1)

    return total_regular_hours, total_overtime_hours


def calculate_weekly_overtime_by_day(
    week_logs: List[TimeLog],
    target_dealership_id: str,
    week_start: date,
    week_end: date,
    analysis_start_date: date,
    analysis_end_date: date,
    current_time: datetime,
) -> Tuple[float, float]:
    """
    Calculate overtime for a single week, processing day by day to maintain proper weekly context.
    This replicates the exact logic from the original endpoint.
    """
    week_regular_hours = 0.0
    week_overtime_hours = 0.0
    cumulative_week_hours = 0.0  # Track total hours worked so far this week

    analysis_tz = ZoneInfo("America/New_York")

    # Process each day of the week
    for day_offset in range(7):
        current_day = week_start + timedelta(days=day_offset)

        # Skip days outside our analysis range
        if current_day < analysis_start_date or current_day > analysis_end_date:
            continue

        # Get day boundaries in UTC
        day_start_utc = datetime.combine(
            current_day, datetime.min.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)
        day_end_utc = datetime.combine(
            current_day, datetime.max.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)

        # Get logs for this specific day
        day_logs = []
        for log in week_logs:
            log_ts = log.timestamp
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=timezone.utc)
            if day_start_utc <= log_ts <= day_end_utc:
                day_logs.append(log)

        if day_logs:
            # Calculate total hours for this day using the same function as original
            # Use the END OF DAY as the fallback "current_time" so that
            # unfinished shifts are capped at midnight rather than the analysis
            # execution time (which could wrongly add hours for historical days).
            analysis_cutoff = min(day_end_utc, current_time)
            day_total_hours = calculate_hours_by_dealership_from_logs(
                day_logs, target_dealership_id, analysis_cutoff
            )

            # Apply the EXACT same overtime allocation logic as the original endpoint
            if cumulative_week_hours >= 40.0:
                # All of this day's hours are overtime
                day_regular_hours = 0.0
                day_overtime_hours = day_total_hours
            else:
                # Some may be regular, some overtime
                remaining_regular_hours = 40.0 - cumulative_week_hours
                day_regular_hours = min(day_total_hours, remaining_regular_hours)
                day_overtime_hours = max(0.0, day_total_hours - remaining_regular_hours)

            # Add to weekly totals
            week_regular_hours += day_regular_hours
            week_overtime_hours += day_overtime_hours
            cumulative_week_hours += day_total_hours

    return week_regular_hours, week_overtime_hours


def calculate_daily_breakdown(
    all_range_logs: list[TimeLog],
    all_vacation_range: list[VacationTime],
    dealership_id: str,
    dealership_employees: dict,
    start_date: date,
    end_date: date,
    current_time: datetime,
) -> List["DailyLaborBreakdown"]:
    """
    Calculate day-by-day labor breakdown for a dealership over a date range.

    Returns actual daily labor costs instead of averaged totals.
    """
    daily_breakdowns = []
    analysis_tz = ZoneInfo("America/New_York")

    # Process each day in the date range
    current_date = start_date
    while current_date <= end_date:
        daily_breakdown = DailyLaborBreakdown(date=current_date.isoformat())

        # Get day boundaries in UTC
        day_start_utc = datetime.combine(
            current_date, datetime.min.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)
        day_end_utc = datetime.combine(
            current_date, datetime.max.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)

        # Filter logs for this specific day and dealership
        day_logs = []
        for log in all_range_logs:
            if log.employee_id not in dealership_employees:
                continue
            log_ts = log.timestamp
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=timezone.utc)
            if day_start_utc <= log_ts <= day_end_utc:
                day_logs.append(log)

        # Filter vacation for this day and dealership
        day_vacation = [
            v
            for v in all_vacation_range
            if v.dealership_id == dealership_id and v.date == current_date
        ]

        # Track employees who worked or took vacation this day
        employees_worked_today = set()
        employees_on_vacation_today = set()

        # Process each employee for this day
        for employee_id, employee_data in dealership_employees.items():
            hourly_wage = employee_data["hourly_wage"]

            # Get employee's logs for this day
            employee_day_logs = [
                log for log in day_logs if log.employee_id == employee_id
            ]

            if employee_day_logs:
                employees_worked_today.add(employee_id)

                # Calculate hours for this employee on this day
                # Use day_end_utc as cutoff for historical days, current_time for today
                analysis_cutoff = min(day_end_utc, current_time)
                day_total_hours = calculate_hours_by_dealership_from_logs(
                    employee_day_logs, dealership_id, analysis_cutoff
                )

                # Calculate regular/overtime for this single day
                # For daily breakdown, we need to consider weekly context
                day_regular_hours, day_overtime_hours = calculate_date_range_overtime(
                    employee_day_logs,
                    dealership_id,
                    current_date,
                    current_date,
                    analysis_cutoff,
                )

                # Calculate costs
                day_regular_cost = day_regular_hours * hourly_wage
                day_overtime_cost = day_overtime_hours * hourly_wage * 1.5
                day_labor_cost = day_regular_cost + day_overtime_cost

                # Add to daily totals
                daily_breakdown.daily_hours += day_total_hours
                daily_breakdown.daily_regular_hours += day_regular_hours
                daily_breakdown.daily_overtime_hours += day_overtime_hours
                daily_breakdown.daily_regular_cost += day_regular_cost
                daily_breakdown.daily_overtime_cost += day_overtime_cost
                daily_breakdown.daily_labor_cost += day_labor_cost

            # Check vacation for this employee on this day
            employee_vacation = [
                v for v in day_vacation if v.employee_id == employee_id
            ]
            if employee_vacation:
                employees_on_vacation_today.add(employee_id)
                vacation_hours = sum(v.hours for v in employee_vacation)
                vacation_cost = vacation_hours * hourly_wage

                daily_breakdown.daily_vacation_hours += vacation_hours
                daily_breakdown.daily_vacation_cost += vacation_cost

        # Set employee counts
        daily_breakdown.employees_worked = len(employees_worked_today)
        daily_breakdown.employees_on_vacation = len(employees_on_vacation_today)
        daily_breakdown.total_employees_active = len(
            employees_worked_today | employees_on_vacation_today
        )

        # Calculate totals
        daily_breakdown.daily_total_hours = (
            daily_breakdown.daily_hours + daily_breakdown.daily_vacation_hours
        )
        daily_breakdown.daily_total_cost = (
            daily_breakdown.daily_labor_cost + daily_breakdown.daily_vacation_cost
        )

        daily_breakdowns.append(daily_breakdown)
        current_date += timedelta(days=1)

    return daily_breakdowns


@router.get(
    "/flexible-labor-spend",
    response_model=FlexibleLaborSpendResponse,
)
async def get_flexible_labor_spend(
    start_date: date,
    end_date: date,
    dealership_ids: Optional[str] = None,  # Comma-separated dealership IDs
    include_daily_breakdown: bool = False,  # Whether to include daily breakdown data
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Get comprehensive labor spend information for specified dealerships over a date range.

    This endpoint maintains the EXACT same rigorous calculation methodology as the
    all-dealerships endpoint but adds flexibility for:
    - Custom date ranges (start_date to end_date inclusive)
    - Selective dealership filtering (specify as many or as few as desired)

    **MAINTAINS IDENTICAL RIGOROUS CALCULATIONS:**
    - Same precise timezone handling (America/New_York to UTC)
    - Same overtime calculation logic with 40-hour weekly thresholds
    - Same vacation time integration
    - Same dealership-specific hour allocation from time logs
    - Same regular vs overtime breakdown with 1.5x overtime rate

    Parameters:
    - start_date: Start date of analysis range (YYYY-MM-DD format)
    - end_date: End date of analysis range (YYYY-MM-DD format, inclusive)
    - dealership_ids: Optional comma-separated list of dealership IDs to analyze.
                     If not provided, analyzes ALL dealerships.
    - include_daily_breakdown: Optional flag to include day-by-day labor cost breakdown.
                              When true, returns actual daily labor costs instead of totals only.

    Returns:
    - Comprehensive labor data for each requested dealership
    - Company-wide totals for the date range
    - All employee details per dealership with same precision as individual endpoints
    - Optional daily breakdown with real daily labor costs (when include_daily_breakdown=true)
    - Exact same rigorous calculations as existing endpoints
    """
    print(f"\n=== Starting FLEXIBLE comprehensive labor spend analysis ===")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Dealership filter: {dealership_ids or 'ALL dealerships'}")
    print(f"Daily breakdown: {'ENABLED' if include_daily_breakdown else 'DISABLED'}")

    # Current time
    now = datetime.now(timezone.utc)

    # Validate date range
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    # Define timezone for consistent handling
    analysis_tz = ZoneInfo("America/New_York")

    # Convert date range to UTC boundaries (same logic as original endpoint)
    start_of_range = datetime.combine(
        start_date, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_range = datetime.combine(
        end_date, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    print(f"Analysis period (UTC): {start_of_range} to {end_of_range}")

    # Determine which dealerships to analyze
    if dealership_ids:
        # Parse comma-separated dealership IDs
        requested_dealership_ids = [
            id.strip() for id in dealership_ids.split(",") if id.strip()
        ]
        print(
            f"Analyzing {len(requested_dealership_ids)} specific dealerships: {requested_dealership_ids}"
        )
    else:
        # Get ALL dealerships (same as original endpoint)
        dealerships_ref = firestore_db.collection("dealerships").stream()
        requested_dealership_ids = [doc.id for doc in dealerships_ref]
        print(f"Analyzing ALL {len(requested_dealership_ids)} dealerships")

    # Get ALL employees from Firestore with their dealership assignments
    # (EXACT same logic as original endpoint)
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee"])
        .stream()
    )
    all_employees_by_dealership = {}  # dealership_id -> {employee_id -> employee_data}
    all_employee_ids = set()

    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id

        # Parse dealership assignments (IDENTICAL logic)
        raw_dealerships = user_data.get("dealerships", "")
        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [
                s.strip() for s in str(raw_dealerships).split(",") if s.strip()
            ]

        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [
                s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()
            ]

        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)

        # Add employee to each dealership they're assigned to, but only if it's in our requested list
        for dealership_id in combined_dealerships:
            if dealership_id in requested_dealership_ids:
                if dealership_id not in all_employees_by_dealership:
                    all_employees_by_dealership[dealership_id] = {}

                all_employees_by_dealership[dealership_id][employee_id] = {
                    "name": user_data.get("displayName", "Unknown"),
                    "hourly_wage": (
                        float(user_data.get("hourlyWage", 0.0))
                        if user_data.get("hourlyWage")
                        else 0.0
                    ),
                }
                all_employee_ids.add(employee_id)

    print(
        f"Found {len(all_employee_ids)} total unique employees across requested dealerships"
    )

    # Get ALL time logs for the date range for ALL employees (single query for efficiency)
    # This is the KEY difference - we query the FULL date range instead of just today/this week
    if all_employee_ids:
        all_range_logs = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id.in_(list(all_employee_ids)))
            .where(TimeLog.timestamp >= start_of_range)
            .where(TimeLog.timestamp <= end_of_range)
            .order_by(TimeLog.timestamp.asc())
        ).all()

        print(
            f"Found {len(all_range_logs)} time logs in date range across all employees"
        )
    else:
        all_range_logs = []

    # Get ALL vacation time for the date range (single query)
    all_vacation_range = session.exec(
        select(VacationTime)
        .where(VacationTime.date >= start_date)
        .where(VacationTime.date <= end_date)
    ).all()

    print(f"Found {len(all_vacation_range)} vacation entries in date range")

    # Process each dealership using THE SAME RIGOROUS CALCULATION LOGIC
    dealership_results = []
    total_company_cost = 0.0
    total_company_employees = 0

    for dealership_id in sorted(requested_dealership_ids):
        try:
            print(f"\n--- Processing dealership: {dealership_id} ---")

            # Get employees for this dealership
            dealership_employees = all_employees_by_dealership.get(dealership_id, {})

            if not dealership_employees:
                print(f"No employees assigned to {dealership_id}, skipping")
                continue

            employee_ids = list(dealership_employees.keys())
            print(f"Found {len(employee_ids)} employees assigned to {dealership_id}")

            # Filter logs for this dealership's employees
            range_logs = [
                log for log in all_range_logs if log.employee_id in employee_ids
            ]

            # Filter vacation for this dealership
            vacation_range = [
                v for v in all_vacation_range if v.dealership_id == dealership_id
            ]

            # Initialize summary for this dealership
            summary = FlexibleDateRangeSummary(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                analysis_timestamp=now,
            )

            employee_details = []
            employees_who_worked_in_range = set()

            # Process each employee for this dealership using IDENTICAL CALCULATION LOGIC
            for employee_id, employee_data in dealership_employees.items():
                try:
                    employee_name = employee_data["name"]
                    hourly_wage = employee_data["hourly_wage"]

                    # Initialize employee detail
                    detail = FlexibleEmployeeLaborDetail(
                        employee_id=employee_id,
                        employee_name=employee_name,
                        hourly_wage=hourly_wage,
                    )

                    # Get employee's logs in the date range
                    employee_range_logs = [
                        log for log in range_logs if log.employee_id == employee_id
                    ]

                    if employee_range_logs:
                        employees_who_worked_in_range.add(employee_id)

                        # Count clock-ins and find first/last (same logic as original)
                        clock_ins = [
                            log
                            for log in employee_range_logs
                            if log.punch_type == PunchType.CLOCK_IN
                        ]
                        clock_outs = [
                            log
                            for log in employee_range_logs
                            if log.punch_type == PunchType.CLOCK_OUT
                        ]

                        detail.total_clock_ins = len(clock_ins)
                        if clock_ins:
                            detail.first_clock_in = min(
                                clock_ins, key=lambda x: x.timestamp
                            ).timestamp
                        if clock_outs:
                            detail.last_clock_out = max(
                                clock_outs, key=lambda x: x.timestamp
                            ).timestamp

                        # Calculate total hours using THE SAME RIGOROUS FUNCTION
                        detail.total_hours = calculate_hours_by_dealership_from_logs(
                            employee_range_logs, dealership_id, now
                        )

                        # Calculate regular and overtime hours using PROPER DATE RANGE LOGIC
                        # This is the critical fix - we need to account for weekly overtime context across the date range
                        detail.regular_hours, detail.overtime_hours = (
                            calculate_date_range_overtime(
                                employee_range_logs,
                                dealership_id,
                                start_date,
                                end_date,
                                now,
                            )
                        )

                        # Calculate labor cost using SAME PRECISE FUNCTION
                        detail.labor_cost = calculate_pay_with_overtime(
                            detail.regular_hours,
                            detail.overtime_hours,
                            hourly_wage,
                        )

                        print(
                            f"Employee {employee_id}: {detail.total_hours:.2f} total hrs, {detail.regular_hours:.2f} reg, {detail.overtime_hours:.2f} OT, ${detail.labor_cost:.2f} cost"
                        )

                    # Process vacation for the date range (SAME LOGIC)
                    employee_vacation_range = [
                        v for v in vacation_range if v.employee_id == employee_id
                    ]
                    if employee_vacation_range:
                        detail.vacation_hours = sum(
                            v.hours for v in employee_vacation_range
                        )
                        detail.vacation_cost = detail.vacation_hours * hourly_wage

                    # Calculate total cost
                    detail.total_cost = detail.labor_cost + detail.vacation_cost

                    employee_details.append(detail)

                    # Add to summary totals (SAME AGGREGATION LOGIC)
                    summary.total_work_hours += detail.total_hours
                    summary.total_vacation_hours += detail.vacation_hours
                    summary.total_work_cost += detail.labor_cost
                    summary.total_vacation_cost += detail.vacation_cost
                    summary.total_regular_hours += detail.regular_hours
                    summary.total_overtime_hours += detail.overtime_hours

                except Exception as e:
                    print(f"Error processing employee {employee_id}: {e}")
                    continue

            # Calculate summary metrics (SAME CALCULATION LOGIC)
            summary.total_employees = len(dealership_employees)
            summary.active_employees_in_range = len(employees_who_worked_in_range)
            summary.total_combined_hours = (
                summary.total_work_hours + summary.total_vacation_hours
            )
            summary.total_labor_cost = (
                summary.total_work_cost + summary.total_vacation_cost
            )

            # Calculate costs and averages (IDENTICAL LOGIC)
            total_regular_cost = 0.0
            total_overtime_cost = 0.0
            total_wages = 0.0
            total_weighted_hours = 0.0

            for detail in employee_details:
                if detail.hourly_wage and detail.hourly_wage > 0:
                    total_wages += detail.hourly_wage
                    if detail.total_hours > 0:
                        total_weighted_hours += detail.total_hours * detail.hourly_wage

                    total_regular_cost += detail.regular_hours * detail.hourly_wage
                    total_overtime_cost += (
                        detail.overtime_hours * detail.hourly_wage * 1.5
                    )

            summary.total_regular_cost = total_regular_cost
            summary.total_overtime_cost = total_overtime_cost

            # Calculate averages (SAME LOGIC)
            if summary.total_employees > 0:
                summary.average_hourly_wage = total_wages / summary.total_employees
                summary.cost_per_employee = (
                    summary.total_labor_cost / summary.total_employees
                )
                summary.hours_per_employee = (
                    summary.total_combined_hours / summary.total_employees
                )

            if summary.total_combined_hours > 0:
                summary.weighted_average_hourly_rate = (
                    total_weighted_hours / summary.total_combined_hours
                )

            # Sort employees and get insights (SAME LOGIC)
            employee_details.sort(key=lambda x: x.employee_name or "")
            top_earners = sorted(
                employee_details, key=lambda x: x.total_cost, reverse=True
            )[:5]
            most_hours = sorted(
                employee_details, key=lambda x: x.total_hours, reverse=True
            )[:5]

            # Calculate daily breakdown if requested
            daily_breakdown = None
            if include_daily_breakdown:
                print(f"Calculating daily breakdown for {dealership_id}...")
                daily_breakdown = calculate_daily_breakdown(
                    list(all_range_logs),
                    list(all_vacation_range),
                    dealership_id,
                    dealership_employees,
                    start_date,
                    end_date,
                    now,
                )
                print(f"Generated {len(daily_breakdown)} daily breakdown entries")

            # Create comprehensive response for this dealership
            dealership_result = FlexibleDealershipLaborSpendResponse(
                dealership_id=dealership_id,
                summary=summary,
                employees=employee_details,
                top_earners=top_earners,
                most_hours=most_hours,
                daily_breakdown=daily_breakdown,
            )

            dealership_results.append(dealership_result)
            total_company_cost += summary.total_labor_cost
            total_company_employees += summary.total_employees

            print(
                f"Completed {dealership_id}: {summary.total_employees} employees, ${summary.total_labor_cost:.2f} total cost"
            )

        except Exception as e:
            print(f"ERROR processing dealership {dealership_id}: {e}")
            import traceback

            traceback.print_exc()
            continue

    # Sort dealerships by total cost (highest first) - SAME LOGIC
    dealership_results.sort(key=lambda x: x.summary.total_labor_cost, reverse=True)

    print(
        f"\n=== Flexible analysis complete: {len(dealership_results)} dealerships, ${total_company_cost:.2f} total cost ==="
    )

    return FlexibleLaborSpendResponse(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        analysis_timestamp=now,
        dealership_ids=requested_dealership_ids,
        total_company_labor_cost=total_company_cost,
        total_company_employees=total_company_employees,
        dealerships=dealership_results,
    )


async def _get_employee_active_status_at_time(
    session: Session,
    employee_id: str,
    at_time: datetime,
    dealership_id: Optional[str] = None,
) -> Tuple[bool, Optional[datetime]]:
    """
    Checks if an employee was active at a specific point in time.
    This is a modified version of is_employee_currently_active for historical analysis.
    """
    lookback_date = at_time - timedelta(days=3)

    most_recent_clock = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= lookback_date)
        .where(TimeLog.timestamp <= at_time)
        .order_by(TimeLog.timestamp.desc())
        .limit(1)
    ).first()

    if not most_recent_clock:
        return False, None

    ts = (
        most_recent_clock.timestamp.replace(tzinfo=timezone.utc)
        if most_recent_clock.timestamp.tzinfo is None
        else most_recent_clock.timestamp
    )

    if dealership_id:
        if (
            most_recent_clock.punch_type == PunchType.CLOCK_IN
            and most_recent_clock.dealership_id == dealership_id
        ):
            return True, ts
        return False, None

    if most_recent_clock.punch_type == PunchType.CLOCK_IN:
        return True, ts

    return False, None


@router.get(
    "/all-dealerships/comprehensive-labor-spend-by-range",
    response_model=List[AllDealershipsComprehensiveLaborSpendResponse],
)
async def get_all_dealerships_comprehensive_labor_spend_by_range(
    start_date: date,
    end_date: date,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Hyper-efficient version of the comprehensive labor spend endpoint for a date range.
    """
    print(
        f"\n=== Starting comprehensive labor spend analysis for range: {start_date} to {end_date} ==="
    )

    if start_date > end_date:
        raise HTTPException(
            status_code=400, detail="Start date cannot be after end date."
        )

    # --- 1. One-time data fetching ---
    analysis_tz = ZoneInfo("America/New_York")
    now = datetime.now(timezone.utc)

    # Get all dealerships
    dealerships_ref = firestore_db.collection("dealerships").stream()
    dealership_ids = [doc.id for doc in dealerships_ref]

    # Get all employees and their dealership assignments
    users_ref = (
        firestore_db.collection("users")
        .where("role", "in", ["employee", "clockOnlyEmployee", "serviceWash", "photos"])
        .stream()
    )
    all_employees_by_dealership = defaultdict(dict)
    all_employee_ids = set()
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        raw_dealerships = user_data.get("dealerships", "")
        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [
                s.strip() for s in str(raw_dealerships).split(",") if s.strip()
            ]
        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [
                s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()
            ]
        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)

        for dealership_id in combined_dealerships:
            all_employees_by_dealership[dealership_id][employee_id] = {
                "name": user_data.get("displayName", "Unknown"),
                "hourly_wage": (
                    float(user_data.get("hourlyWage", 0.0))
                    if user_data.get("hourlyWage")
                    else 0.0
                ),
            }
            all_employee_ids.add(employee_id)

    # Determine the full range for time logs to handle weekly overtime
    range_week_start_date = start_date - timedelta(days=start_date.weekday())
    range_week_end_date = end_date + timedelta(days=(6 - end_date.weekday()))

    start_of_range_week = datetime.combine(
        range_week_start_date, datetime.min.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)
    end_of_range_week = datetime.combine(
        range_week_end_date, datetime.max.time(), tzinfo=analysis_tz
    ).astimezone(timezone.utc)

    # Fetch all time logs and vacation data for the entire range once
    all_week_logs = []
    all_vacation_data = []
    if all_employee_ids:
        all_week_logs = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id.in_(list(all_employee_ids)))
            .where(TimeLog.timestamp >= start_of_range_week)
            .where(TimeLog.timestamp <= end_of_range_week)
        ).all()
        for log in all_week_logs:
            if log.timestamp.tzinfo is None:
                log.timestamp = log.timestamp.replace(tzinfo=timezone.utc)
        all_vacation_data = session.exec(
            select(VacationTime)
            .where(VacationTime.date >= start_date)
            .where(VacationTime.date <= end_date)
        ).all()

    # Pre-process logs for efficient lookup
    logs_by_employee = defaultdict(list)
    for log in all_week_logs:
        logs_by_employee[log.employee_id].append(log)

    # --- 2. Process data day by day ---
    daily_reports = []
    current_date = start_date
    while current_date <= end_date:
        analysis_date = current_date
        start_of_analysis_day = datetime.combine(
            analysis_date, datetime.min.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)
        end_of_analysis_day = datetime.combine(
            analysis_date, datetime.max.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)
        current_week_start_date = analysis_date - timedelta(
            days=analysis_date.weekday()
        )
        start_of_week = datetime.combine(
            current_week_start_date, datetime.min.time(), tzinfo=analysis_tz
        ).astimezone(timezone.utc)

        # Filter pre-fetched data for the current day
        today_logs = [
            log
            for log in all_week_logs
            if start_of_analysis_day <= log.timestamp <= end_of_analysis_day
        ]
        week_logs = [
            log
            for log in all_week_logs
            if start_of_week <= log.timestamp <= end_of_analysis_day
        ]
        vacation_today = [v for v in all_vacation_data if v.date == analysis_date]

        # --- Replicate the exact same logic as the single-day endpoint ---
        dealership_results = []
        total_company_cost = 0.0
        total_company_employees = 0

        for dealership_id in sorted(dealership_ids):
            dealership_employees = all_employees_by_dealership.get(dealership_id, {})
            if not dealership_employees:
                continue

            summary = DealershipLaborSpendSummary(
                dealership_id=dealership_id,
                analysis_date=analysis_date.isoformat(),
                analysis_timestamp=now,
            )
            employee_details = []
            employees_who_worked_today = set()
            employees_currently_active = set()

            for employee_id, employee_data in dealership_employees.items():
                detail = EmployeeLaborDetail(
                    employee_id=employee_id,
                    employee_name=employee_data["name"],
                    hourly_wage=employee_data["hourly_wage"],
                )

                # Efficiently check active status using pre-fetched logs
                employee_logs_up_to_day = [
                    log
                    for log in logs_by_employee.get(employee_id, [])
                    if log.timestamp <= end_of_analysis_day
                ]
                most_recent_clock = max(
                    employee_logs_up_to_day, key=lambda x: x.timestamp, default=None
                )

                is_active = False
                most_recent_clock_in_ts = None
                if most_recent_clock:
                    if (
                        most_recent_clock.punch_type == PunchType.CLOCK_IN
                        and most_recent_clock.dealership_id == dealership_id
                    ):
                        is_active = True
                        most_recent_clock_in_ts = most_recent_clock.timestamp

                detail.is_currently_active = is_active
                if is_active and most_recent_clock_in_ts:
                    detail.current_shift_start_time = most_recent_clock_in_ts
                    detail.current_shift_duration_hours = (
                        end_of_analysis_day - most_recent_clock_in_ts
                    ).total_seconds() / 3600
                    employees_currently_active.add(employee_id)

                employee_week_logs = [
                    log for log in week_logs if log.employee_id == employee_id
                ]
                week_logs_before_today = [
                    log
                    for log in employee_week_logs
                    if log.timestamp < start_of_analysis_day
                ]
                hours_worked_before_today = calculate_hours_by_dealership_from_logs(
                    week_logs_before_today, dealership_id, start_of_analysis_day
                )
                employee_today_logs = [
                    log for log in today_logs if log.employee_id == employee_id
                ]

                if employee_today_logs:
                    employees_who_worked_today.add(employee_id)
                    detail.todays_total_hours = calculate_hours_by_dealership_from_logs(
                        employee_today_logs, dealership_id, end_of_analysis_day
                    )

                    if hours_worked_before_today >= 40.0:
                        detail.todays_regular_hours = 0.0
                        detail.todays_overtime_hours = detail.todays_total_hours
                    else:
                        remaining_regular = 40.0 - hours_worked_before_today
                        detail.todays_regular_hours = min(
                            detail.todays_total_hours, remaining_regular
                        )
                        detail.todays_overtime_hours = max(
                            0.0, detail.todays_total_hours - remaining_regular
                        )

                    detail.todays_labor_cost = calculate_pay_with_overtime(
                        detail.todays_regular_hours,
                        detail.todays_overtime_hours,
                        detail.hourly_wage,
                    )

                employee_vacation_today = [
                    v for v in vacation_today if v.employee_id == employee_id
                ]
                if employee_vacation_today:
                    detail.todays_vacation_hours = sum(
                        v.hours for v in employee_vacation_today
                    )
                    detail.todays_vacation_cost = (
                        detail.todays_vacation_hours * detail.hourly_wage
                    )

                detail.todays_total_cost = (
                    detail.todays_labor_cost + detail.todays_vacation_cost
                )
                employee_details.append(detail)

                summary.todays_total_work_hours += detail.todays_total_hours
                summary.todays_total_vacation_hours += detail.todays_vacation_hours
                summary.todays_total_work_cost += detail.todays_labor_cost
                summary.todays_total_vacation_cost += detail.todays_vacation_cost
                summary.todays_regular_hours += detail.todays_regular_hours
                summary.todays_overtime_hours += detail.todays_overtime_hours

                if is_active:
                    summary.current_hourly_labor_rate += detail.hourly_wage

            # Finalize summary calculations
            summary.total_employees = len(dealership_employees)
            summary.employees_who_clocked_in_today = len(employees_who_worked_today)
            summary.employees_currently_clocked_in = len(employees_currently_active)
            summary.todays_total_labor_cost = (
                summary.todays_total_work_cost + summary.todays_total_vacation_cost
            )

            dealership_results.append(
                ComprehensiveLaborSpendResponse(
                    summary=summary,
                    employees=sorted(
                        employee_details, key=lambda x: x.employee_name or ""
                    ),
                    data_generated_at=now,
                )
            )
            total_company_cost += summary.todays_total_labor_cost
            total_company_employees += summary.total_employees

        daily_reports.append(
            AllDealershipsComprehensiveLaborSpendResponse(
                analysis_date=analysis_date.isoformat(),
                analysis_timestamp=now,
                total_company_labor_cost=total_company_cost,
                total_company_employees=total_company_employees,
                dealerships=sorted(
                    dealership_results,
                    key=lambda x: x.summary.todays_total_labor_cost,
                    reverse=True,
                ),
            )
        )

        current_date += timedelta(days=1)

    return daily_reports


# ---------------------------------------------------------------------------
# DailyLaborBreakdown – per-dealership aggregate used in flexible labor views
# ---------------------------------------------------------------------------


class DailyLaborBreakdown(BaseModel):
    """Aggregated labor metrics for a single dealership day."""

    date: str  # YYYY-MM-DD

    # Hours
    daily_hours: float = 0.0
    daily_regular_hours: float = 0.0
    daily_overtime_hours: float = 0.0
    daily_vacation_hours: float = 0.0
    daily_total_hours: float = 0.0

    # Costs
    daily_regular_cost: float = 0.0
    daily_overtime_cost: float = 0.0
    daily_labor_cost: float = 0.0  # regular + overtime
    daily_vacation_cost: float = 0.0
    daily_total_cost: float = 0.0  # labor + vacation

    # Employee counts
    employees_worked: int = 0
    employees_on_vacation: int = 0
    total_employees_active: int = 0
