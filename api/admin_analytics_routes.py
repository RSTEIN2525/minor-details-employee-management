from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func
from pydantic import BaseModel, field_serializer
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, date, timedelta, timezone
from db.session import get_session
from core.deps import require_admin_role, get_current_user
from core.firebase import db as firestore_db
from models.time_log import TimeLog, PunchType
from models.shop import Shop
from models.vacation_time import VacationTime
from collections import defaultdict
from utils.datetime_helpers import format_utc_datetime
from utils.breaks import apply_unpaid_break

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

    @field_serializer('shift_start_time')
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

    @field_serializer('timestamp')
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
    end_date: str    # YYYY-MM-DD
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
    
    @field_serializer('current_shift_start_time', 'todays_first_clock_in', 'todays_last_clock_out')
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
    
    @field_serializer('analysis_timestamp')
    def serialize_analysis_timestamp(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)

class ComprehensiveLaborSpendResponse(BaseModel):
    summary: DealershipLaborSpendSummary
    employees: List[EmployeeLaborDetail]
    
    # Additional insights
    top_earners_today: List[EmployeeLaborDetail] = []  # Top 5 by cost
    most_hours_today: List[EmployeeLaborDetail] = []   # Top 5 by hours
    
    # Data freshness
    data_generated_at: datetime
    
    @field_serializer('data_generated_at')
    def serialize_data_generated_at(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
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
    current_hourly_burn_rate: float = 0.0  # Sum of wages of currently clocked in employees
    
    # Quick stats
    average_cost_per_employee_today: float = 0.0
    projected_daily_cost: float = 0.0  # Based on current burn rate
    
    @field_serializer('current_time')
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
    
    @field_serializer('analysis_time')
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
            "hourly_wage": user_data.get("hourlyWage", 0.0)
        }
    return {
        "id": user_id,
        "name": "Unknown",
        "hourly_wage": 0.0
    }

def calculate_regular_and_overtime_hours(total_hours: float) -> Tuple[float, float]:
    """Calculate regular and overtime hours based on total hours worked."""
    if total_hours <= 40.0:
        return total_hours, 0.0
    else:
        return 40.0, total_hours - 40.0

def calculate_pay_with_overtime(regular_hours: float, overtime_hours: float, hourly_wage: float) -> float:
    """Calculate total pay including overtime rate (1.5x) for overtime hours."""
    regular_pay = regular_hours * hourly_wage
    overtime_pay = overtime_hours * hourly_wage * 1.5
    return regular_pay + overtime_pay

async def calculate_todays_hours_and_status(session: Session, employee_id: str) -> Tuple[float, bool]:
    """Calculate hours worked today and current clock status for an employee."""
    now = datetime.now(timezone.utc)
    today = now.date()
    
    # Start and end of today in UTC
    start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
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
    start_of_week = (datetime.now(timezone.utc) - timedelta(days=today.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
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

async def is_employee_currently_active(session: Session, employee_id: str, dealership_id: Optional[str] = None) -> Tuple[bool, Optional[datetime]]:
    """
    Determine if an employee is currently active (clocked in) by checking their most recent clock action.
    If their last clock was a CLOCK_IN, they're active. If it was a CLOCK_OUT, they're not.
    
    Returns:
        Tuple[bool, Optional[datetime]]: (is_active, most_recent_clock_in_time)
    """
    # Get the most recent clock entry for this employee
    # Look back a reasonable amount to handle cross-day shifts
    lookback_date = datetime.now(timezone.utc) - timedelta(days=3)
    
    query = select(TimeLog).where(TimeLog.employee_id == employee_id).where(TimeLog.timestamp >= lookback_date)
    
    # Filter by dealership if provided
    if dealership_id:
        query = query.where(TimeLog.dealership_id == dealership_id)
        
    most_recent_clock = session.exec(
        query.order_by(TimeLog.timestamp.desc()).limit(1)
    ).first()
    
    if not most_recent_clock:
        return False, None
    
    # Ensure timestamp is timezone aware
    ts = most_recent_clock.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    
    # Simple logic: if last action was CLOCK_IN, they're active
    if most_recent_clock.punch_type == PunchType.CLOCK_IN:
        return True, ts
    else:
        return False, None

async def calculate_vacation_hours(session: Session, employee_id: str, start_date: date, end_date: date) -> float:
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
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get enhanced daily labor spend with detailed dealership breakdown including employee counts.
    Requires a specific target date.
    """
    # Start and end of the target day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all time logs for the day
    time_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_of_day)
        .where(TimeLog.timestamp <= end_of_day)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Group time logs by dealership and employee
    dealership_employee_logs = defaultdict(lambda: defaultdict(list))
    hourly_breakdown = defaultdict(lambda: {"spend": 0.0, "employees": set()})
    
    for log in time_logs:
        dealership_employee_logs[log.dealership_id][log.employee_id].append(log)
    
    # Calculate metrics for each dealership
    total_labor_spend = 0.0
    total_hours = 0.0
    dealership_breakdowns = []
    
    # Get dealership names from Firestore
    dealership_names = {}
    try:
        dealerships_ref = firestore_db.collection("dealerships").stream()
        for doc in dealerships_ref:
            dealership_data = doc.to_dict()
            dealership_names[doc.id] = dealership_data.get("name", doc.id)
    except Exception as e:
        print(f"Warning: Could not fetch dealership names: {e}")
    
    for dealership_id, employee_logs in dealership_employee_logs.items():
        dealership_labor_spend = 0.0
        dealership_hours = 0.0
        employees_with_activity = set()
        
        for employee_id, logs in employee_logs.items():
            # Get employee's hourly wage
            user_details = await get_user_details(employee_id)
            hourly_wage = user_details.get("hourly_wage", 0.0)
            
            # Sort logs by timestamp
            sorted_logs = sorted(logs, key=lambda x: x.timestamp)
            
            # Calculate hours worked and corresponding spend for this employee
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
                    raw_hours = (log_ts - clock_in_time).total_seconds() / 3600
                    paid_hours = apply_unpaid_break(raw_hours)
                    spend = paid_hours * hourly_wage
                    
                    # Add to dealership totals
                    dealership_labor_spend += spend
                    dealership_hours += paid_hours
                    
                    # Add to hourly breakdown
                    shift_start_hour = clock_in_time.hour
                    shift_end_hour = log_ts.hour
                    
                    if shift_start_hour == shift_end_hour:
                        # Shift within the same hour
                        hourly_breakdown[shift_start_hour]["spend"] += spend
                        hourly_breakdown[shift_start_hour]["employees"].add(employee_id)
                    else:
                        # Distribute across hours
                        for hour in range(shift_start_hour, shift_end_hour + 1):
                            hour_mod = hour % 24
                            hourly_breakdown[hour_mod]["employees"].add(employee_id)
                            # Simple proportional distribution
                            hour_fraction = 1.0 / (shift_end_hour - shift_start_hour + 1)
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
                    
                    # Add to dealership totals
                    dealership_labor_spend += spend
                    dealership_hours += paid_hours
                    
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

            # Count employee if they had any clock activity (including active shifts)
            if employee_had_activity:
                employees_with_activity.add(employee_id)
        
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
                    employee_count=len(employees_with_activity)
                )
            )
    
    # Format hourly breakdown for response
    formatted_hourly_breakdown = [
        HourlyLaborSpend(
            hour=hour,
            total_labor_spend=round(data["spend"], 2),
            total_employees=len(data["employees"])
        )
        for hour, data in sorted(hourly_breakdown.items())
    ]
    
    # Sort dealership breakdown by labor spend (highest first)
    dealership_breakdowns.sort(key=lambda x: x.total_labor_spend, reverse=True)
    
    return EnhancedDailyLaborSummary(
        target_date=target_date.isoformat(),
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2),
        dealership_breakdown=dealership_breakdowns,
        hourly_breakdown=formatted_hourly_breakdown
    )

@router.get("/labor/daily", response_model=DailyLaborSummary)
async def get_daily_labor_spend(
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get the total labor spend for a specific day, broken down by hour and dealership.
    If no date is provided, defaults to today.
    """
    # Default to today if no date provided
    if not target_date:
        target_date = datetime.now(timezone.utc).date()
    
    # Start and end of the target day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
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
    dealership_breakdown = defaultdict(lambda: {"spend": 0.0, "hours": 0.0, "employees": set()})
    
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
                    shift_start_hour = clock_in_time.hour # clock_in_time is UTC aware
                    shift_end_hour = log_ts.hour # log_ts is UTC aware
                    
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
                            hour_fraction = 1.0 / (shift_end_hour - shift_start_hour + 1)
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
            total_employees=len(data["employees"])
        )
        for hour, data in sorted(hourly_breakdown.items())
    ]
    
    # Format dealership breakdown for response
    formatted_dealership_breakdown = [
        DealershipLaborSpend(
            dealership_id=dealership_id,
            total_labor_spend=round(data["spend"], 2),
            total_hours=round(data["hours"], 2)
        )
        for dealership_id, data in dealership_breakdown.items()
    ]
    
    return DailyLaborSummary(
        date=target_date.isoformat(),
        total_labor_spend=round(total_labor_spend, 2),
        total_hours=round(total_hours, 2),
        hourly_breakdown=formatted_hourly_breakdown,
        dealership_breakdown=formatted_dealership_breakdown
    )

@router.get("/labor/dealership/{dealership_id}", response_model=DealershipLaborSpend)
async def get_dealership_labor_spend(
    dealership_id: str,
    target_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get the labor spend for a specific dealership on a specific day.
    If no date is provided, defaults to today.
    """
    # Default to today if no date provided
    if not target_date:
        target_date = datetime.now(timezone.utc).date()
    
    # Start and end of the target day in UTC
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
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
        total_hours=round(total_hours, 2)
    )

@router.get("/active/dealership/{dealership_id}", response_model=DealershipEmployeeStatus)
async def get_active_employees_by_dealership(
    dealership_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    print(f"\n--- Processing get_active_employees_by_dealership for dealership_id: {dealership_id} ---")
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
            print(f"Employee {employee_id} determined ACTIVE. Most recent clock-in: {most_recent_clock_in_ts}")
            
            # Get employee details
            user_details = await get_user_details(employee_id)
            print(f"User details for {employee_id}: {user_details}")
            hourly_wage = user_details.get("hourly_wage", 0.0)
            employee_name = user_details.get("name", "Unknown")
            
            # Calculate current shift duration
            now = datetime.now(timezone.utc)
            shift_duration_hours = (now - most_recent_clock_in_ts).total_seconds() / 3600
            
            # Calculate weekly hours
            weekly_hours = await calculate_weekly_hours(session, employee_id)
            print(f"Calculated shift_duration_hours for {employee_id}: {shift_duration_hours}")
            print(f"Calculated weekly_hours for {employee_id}: {weekly_hours}")
            
            # Check if in overtime
            is_overtime = weekly_hours > 40.0
            
            # Calculate today's labor spend for this employee
            today = datetime.now(timezone.utc).date()
            start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
            
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
                elif punch.punch_type == PunchType.CLOCK_OUT and current_shift_clock_in_time:
                    raw_hours = (punch_ts - current_shift_clock_in_time).total_seconds() / 3600
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
                    is_overtime=is_overtime
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
        total_labor_spend_today=round(total_labor_spend_today, 2)
    )
    print(f"Returning DealershipEmployeeStatus for {dealership_id}: {result}")
    return result

@router.get("/active/all", response_model=List[DealershipEmployeeStatus])
async def get_all_active_employees(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
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
            dealership_id=dealership_id,
            session=session,
            admin_user=admin_user
        )
        print(f"Status for dealership {dealership_id} (from get_active_employees_by_dealership): {dealership_status}")
        
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
    admin_user: dict = Depends(require_admin_role)
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
    start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
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
                    if employee_logs[employee_id].index(log) > 8:  # Rough approximation of 40 hours
                        total_labor_spend += paid_hours * hourly_wage * 1.5
                    else:
                        total_labor_spend += paid_hours * hourly_wage
                        
                    total_hours += paid_hours
                    clock_in_time = None
        
        dealership_labor_spend.append(
            DealershipLaborSpend(
                dealership_id=dealership_id,
                total_labor_spend=round(total_labor_spend, 2),
                total_hours=round(total_hours, 2)
            )
        )
    
    # Sort by total labor spend (highest first)
    dealership_labor_spend.sort(key=lambda x: x.total_labor_spend, reverse=True)
    
    return dealership_labor_spend

@router.get("/employee/{employee_id}/details", response_model=EmployeeDetailResponse)
async def get_employee_details(
    employee_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
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
    
    # Start date for fetching clocks (2 weeks ago)
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
            
        clock_entries.append(EmployeeClockEntry(
            id=clock.id,
            timestamp=ts,
            punch_type=clock.punch_type,
            dealership_id=clock.dealership_id
        ))
    
    print(f"DEBUG: Formatted {len(clock_entries)} clock entries for response")
    
    # Calculate hours and pay for current week
    current_week_hours = 0.0
    current_week_start_dt = datetime.combine(current_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    current_week_end_dt = datetime.combine(current_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    current_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= current_week_start_dt)
        .where(TimeLog.timestamp <= current_week_end_dt)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Calculate hours for current week
    clock_in_time = None
    for clock in current_week_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        if clock.punch_type == PunchType.CLOCK_IN:
            clock_in_time = ts
        elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            raw_hours = (ts - clock_in_time).total_seconds() / 3600
            paid_hours = apply_unpaid_break(raw_hours)
            current_week_hours += paid_hours
            clock_in_time = None
    
    # If still clocked in, add time until now
    if clock_in_time:
        raw_hours = (now - clock_in_time).total_seconds() / 3600
        paid_hours = apply_unpaid_break(raw_hours)
        current_week_hours += paid_hours
    
    current_week_pay = current_week_hours * hourly_wage
    
    # Calculate hours and pay for previous week
    prev_week_hours = 0.0
    prev_week_start_dt = datetime.combine(prev_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    prev_week_clocks = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .where(TimeLog.timestamp >= prev_week_start_dt)
        .where(TimeLog.timestamp <= prev_week_end_dt)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Calculate hours for previous week
    clock_in_time = None
    for clock in prev_week_clocks:
        ts = clock.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        if clock.punch_type == PunchType.CLOCK_IN:
            clock_in_time = ts
        elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            raw_hours = (ts - clock_in_time).total_seconds() / 3600
            paid_hours = apply_unpaid_break(raw_hours)
            prev_week_hours += paid_hours
            clock_in_time = None
    
    prev_week_pay = prev_week_hours * hourly_wage
    
    # Calculate regular and overtime hours for each week
    prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(prev_week_hours)
    prev_week_pay = calculate_pay_with_overtime(prev_week_regular, prev_week_overtime, hourly_wage)
    
    current_week_regular, current_week_overtime = calculate_regular_and_overtime_hours(current_week_hours)
    current_week_pay = calculate_pay_with_overtime(current_week_regular, current_week_overtime, hourly_wage)
    
    # Calculate today's hours and clock status
    todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(session, employee_id)
    todays_regular, todays_overtime = calculate_regular_and_overtime_hours(todays_hours)
    todays_pay = calculate_pay_with_overtime(todays_regular, todays_overtime, hourly_wage)

    # Calculate vacation hours for each period
    prev_week_vacation_hours = await calculate_vacation_hours(session, employee_id, prev_week_start, prev_week_end)
    current_week_vacation_hours = await calculate_vacation_hours(session, employee_id, current_week_start, current_week_end)
    todays_vacation_hours = await calculate_vacation_hours(session, employee_id, today, today)

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
            is_current_week=False
        ),
        WeekSummary(
            week_start_date=current_week_start.isoformat(),
            week_end_date=current_week_end.isoformat(),
            total_hours=round(current_week_hours, 2),
            regular_hours=round(current_week_regular, 2),
            overtime_hours=round(current_week_overtime, 2),
            total_pay=round(current_week_pay, 2),
            vacation_hours=round(current_week_vacation_hours, 2),
            is_current_week=True
        )
    ]
    
    # Calculate total pay for both weeks
    two_week_total_pay = prev_week_pay + current_week_pay
    
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
            is_currently_clocked_in=is_currently_clocked_in
        ),
        two_week_total_pay=round(two_week_total_pay, 2)
    )

@router.get("/employees/details", response_model=List[EmployeeDetailResponse])
async def get_all_employees_details(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
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
    current_week_start_dt = datetime.combine(current_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    current_week_end_dt = datetime.combine(current_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    prev_week_start_dt = datetime.combine(prev_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    prev_week_end_dt = datetime.combine(prev_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all employees from Firestore
    users_ref = firestore_db.collection("users").where("role", "==", "employee").stream()
    employees_data = {}
    employee_ids = []
    
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        employee_ids.append(employee_id)
        employees_data[employee_id] = {
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": user_data.get("hourlyWage", 0.0)
        }
    
    # Apply pagination to employee list
    total_employees = len(employee_ids)
    paginated_employee_ids = sorted(employee_ids)[offset:offset+limit]
    
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
        for clock in sorted(employee_clock_list, key=lambda x: x.timestamp, reverse=True):
            # Ensure timestamp is timezone aware
            ts = clock.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
                
            clock_entries.append(EmployeeClockEntry(
                id=clock.id,
                timestamp=ts,
                punch_type=clock.punch_type,
                dealership_id=clock.dealership_id
            ))
        
        # Calculate hours and pay
        current_week_hours = 0.0
        prev_week_hours = 0.0
        
        # Process all clocks chronologically for accurate pairing
        sorted_clocks = sorted(employee_clock_list, key=lambda x: x.timestamp)
        clock_in_time = None
        
        for clock in sorted_clocks:
            ts = clock.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
                
            if clock.punch_type == PunchType.CLOCK_IN:
                clock_in_time = ts
            elif clock.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                raw_hours = (ts - clock_in_time).total_seconds() / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                
                # Determine which week this duration belongs to
                if current_week_start_dt <= ts <= current_week_end_dt:
                    current_week_hours += paid_hours
                elif prev_week_start_dt <= ts <= prev_week_end_dt:
                    prev_week_hours += paid_hours
                
                clock_in_time = None
        
        # If still clocked in during current week
        if clock_in_time and current_week_start_dt <= clock_in_time <= current_week_end_dt:
            raw_hours = (now - clock_in_time).total_seconds() / 3600
            paid_hours = apply_unpaid_break(raw_hours)
            current_week_hours += paid_hours
        
        current_week_pay = current_week_hours * hourly_wage
        prev_week_pay = prev_week_hours * hourly_wage
        
        # Calculate regular and overtime hours for each week
        prev_week_regular, prev_week_overtime = calculate_regular_and_overtime_hours(prev_week_hours)
        prev_week_pay = calculate_pay_with_overtime(prev_week_regular, prev_week_overtime, hourly_wage)
        
        current_week_regular, current_week_overtime = calculate_regular_and_overtime_hours(current_week_hours)
        current_week_pay = calculate_pay_with_overtime(current_week_regular, current_week_overtime, hourly_wage)
        
        # Calculate today's hours and clock status
        todays_hours, is_currently_clocked_in = await calculate_todays_hours_and_status(session, employee_id)
        todays_regular, todays_overtime = calculate_regular_and_overtime_hours(todays_hours)
        todays_pay = calculate_pay_with_overtime(todays_regular, todays_overtime, hourly_wage)

        # Create week summaries
        week_summaries = [
            WeekSummary(
                week_start_date=prev_week_start.isoformat(),
                week_end_date=prev_week_end.isoformat(),
                total_hours=round(prev_week_hours, 2),
                regular_hours=round(prev_week_regular, 2),
                overtime_hours=round(prev_week_overtime, 2),
                total_pay=round(prev_week_pay, 2),
                is_current_week=False
            ),
            WeekSummary(
                week_start_date=current_week_start.isoformat(),
                week_end_date=current_week_end.isoformat(),
                total_hours=round(current_week_hours, 2),
                regular_hours=round(current_week_regular, 2),
                overtime_hours=round(current_week_overtime, 2),
                total_pay=round(current_week_pay, 2),
                is_current_week=True
            )
        ]
        
        # Calculate total pay for both weeks
        two_week_total_pay = prev_week_pay + current_week_pay
        
        all_employee_details.append(EmployeeDetailResponse(
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
                is_currently_clocked_in=is_currently_clocked_in
            ),
            two_week_total_pay=round(two_week_total_pay, 2)
        ))
    
    # Sort by name
    all_employee_details.sort(key=lambda x: x.employee_name or "")
    
    return all_employee_details

@router.get("/dealership/{dealership_id}/employee-hours", response_model=DealershipEmployeeHoursResponse)
async def get_dealership_employee_hours_breakdown(
    dealership_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
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
    start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
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
        is_currently_active, _ = await is_employee_currently_active(session, employee_id, dealership_id)
        
        # Calculate total hours worked by this employee
        logs = employee_logs[employee_id]
        sorted_logs = sorted(logs, key=lambda x: x.timestamp)
        
        total_hours_worked = 0.0
        clock_in_time: Optional[datetime] = None
        
        for log in sorted_logs:
            log_ts = log.timestamp
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=timezone.utc)

            if log.punch_type == PunchType.CLOCK_IN:
                clock_in_time = log_ts
            elif log.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                raw_hours = (log_ts - clock_in_time).total_seconds() / 3600
                paid_hours = apply_unpaid_break(raw_hours)
                total_hours_worked += paid_hours
                clock_in_time = None
        
        # If still clocked in within our date range
        if clock_in_time and clock_in_time <= end_datetime:
            # Calculate duration until end of period or current time (whichever is earlier)
            end_time = min(now, end_datetime)
            raw_hours = (end_time - clock_in_time).total_seconds() / 3600
            paid_hours = apply_unpaid_break(raw_hours)
            total_hours_worked += paid_hours
        
        # Calculate regular vs overtime hours
        regular_hours, overtime_hours = calculate_regular_and_overtime_hours(total_hours_worked)
        
        # Calculate estimated pay with overtime
        estimated_pay = calculate_pay_with_overtime(regular_hours, overtime_hours, hourly_wage)
        
        # Add to summary totals
        summary_total_hours += total_hours_worked
        summary_regular_hours += regular_hours
        summary_overtime_hours += overtime_hours
        summary_estimated_pay += estimated_pay
        
        employee_breakdown_list.append(EmployeeHoursBreakdown(
            employee_id=employee_id,
            employee_name=employee_name,
            hourly_wage=hourly_wage,
            total_hours=round(total_hours_worked, 2),
            regular_hours=round(regular_hours, 2),
            overtime_hours=round(overtime_hours, 2),
            estimated_pay=round(estimated_pay, 2),
            is_currently_active=is_currently_active
        ))
    
    # Sort by total hours (highest first) for better overview
    employee_breakdown_list.sort(key=lambda x: x.total_hours, reverse=True)
    
    # Create summary dictionary
    summary = {
        "total_hours": round(summary_total_hours, 2),
        "regular_hours": round(summary_regular_hours, 2),
        "overtime_hours": round(summary_overtime_hours, 2),
        "estimated_total_pay": round(summary_estimated_pay, 2),
        "employee_count": len(employee_breakdown_list),
        "average_hours_per_employee": round(summary_total_hours / len(employee_breakdown_list) if employee_breakdown_list else 0, 2)
    }
    
    return DealershipEmployeeHoursResponse(
        dealership_id=dealership_id,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        employees=employee_breakdown_list,
        summary=summary
    )

@router.get("/dealership/{dealership_id}/comprehensive-labor-spend", response_model=ComprehensiveLaborSpendResponse)
async def get_comprehensive_labor_spend(
    dealership_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
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
    print(f"\n--- Starting comprehensive labor spend analysis for dealership: {dealership_id} ---")
    
    # Current time and date setup
    now = datetime.now(timezone.utc)
    today = now.date()
    
    # Date boundaries for today
    start_of_today = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_today = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Current week boundaries (Monday to Sunday)
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    start_of_week = datetime.combine(current_week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_week = datetime.combine(current_week_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    print(f"Analysis period - Today: {start_of_today} to {end_of_today}")
    print(f"Analysis period - Week: {start_of_week} to {end_of_week}")
    
    # Get ALL employees from Firestore (not just those who clocked in)
    users_ref = firestore_db.collection("users").where("role", "==", "employee").stream()
    all_employees = {}
    for doc in users_ref:
        user_data = doc.to_dict()
        # --- Dealership assignment check ---
        # Parse "dealerships" field
        raw_dealerships = user_data.get("dealerships", "")
        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [s.strip() for s in str(raw_dealerships).split(",") if s.strip()]

        # Parse optional "timeClockDealerships" field (same format)
        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()]

        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)

        # Skip employees not assigned to this dealership
        if dealership_id not in combined_dealerships:
            continue

        employee_id = doc.id
        all_employees[employee_id] = {
            "name": user_data.get("displayName", "Unknown"),
            "hourly_wage": float(user_data.get("hourlyWage", 0.0)) if user_data.get("hourlyWage") else 0.0
        }
    
    print(f"Found {len(all_employees)} total employees in system")
    
    # Get ALL time logs for this dealership for today and this week
    today_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_of_today)
        .where(TimeLog.timestamp <= end_of_today)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    week_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.dealership_id == dealership_id)
        .where(TimeLog.timestamp >= start_of_week)
        .where(TimeLog.timestamp <= end_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    print(f"Found {len(today_logs)} time logs for today, {len(week_logs)} for this week")
    
    # Get vacation time for today
    vacation_today = session.exec(
        select(VacationTime)
        .where(VacationTime.dealership_id == dealership_id)
        .where(VacationTime.date == today)
    ).all()
    
    vacation_this_week = session.exec(
        select(VacationTime)
        .where(VacationTime.dealership_id == dealership_id)
        .where(VacationTime.date >= current_week_start)
        .where(VacationTime.date <= current_week_end)
    ).all()
    
    print(f"Found {len(vacation_today)} vacation entries for today, {len(vacation_this_week)} for this week")
    
    # Initialize summary
    summary = DealershipLaborSpendSummary(
        dealership_id=dealership_id,
        analysis_date=today.isoformat(),
        analysis_timestamp=now
    )
    
    employee_details = []
    employees_who_worked_today = set()
    employees_currently_active = set()
    
    # Process each employee
    for employee_id, employee_data in all_employees.items():
        employee_name = employee_data["name"]
        hourly_wage = employee_data["hourly_wage"]
        
        print(f"Processing employee: {employee_id} ({employee_name}) @ ${hourly_wage}/hr")
        
        # Initialize employee detail
        detail = EmployeeLaborDetail(
            employee_id=employee_id,
            employee_name=employee_name,
            hourly_wage=hourly_wage
        )
        
        # Check if currently active
        is_active, most_recent_clock_in_ts = await is_employee_currently_active(
            session, employee_id, dealership_id
        )
        detail.is_currently_active = is_active
        if is_active and most_recent_clock_in_ts:
            detail.current_shift_start_time = most_recent_clock_in_ts
            detail.current_shift_duration_hours = (now - most_recent_clock_in_ts).total_seconds() / 3600
            employees_currently_active.add(employee_id)
        
        # Process today's time logs for this employee
        employee_today_logs = [log for log in today_logs if log.employee_id == employee_id]
        
        if employee_today_logs:
            employees_who_worked_today.add(employee_id)
            
            # Count clock-ins and find first/last
            clock_ins = [log for log in employee_today_logs if log.punch_type == PunchType.CLOCK_IN]
            clock_outs = [log for log in employee_today_logs if log.punch_type == PunchType.CLOCK_OUT]
            
            detail.todays_clock_in_count = len(clock_ins)
            if clock_ins:
                detail.todays_first_clock_in = min(clock_ins, key=lambda x: x.timestamp).timestamp
            if clock_outs:
                detail.todays_last_clock_out = max(clock_outs, key=lambda x: x.timestamp).timestamp
            
            # Calculate today's hours
            detail.todays_total_hours = calculate_hours_from_logs(employee_today_logs, now)
            detail.todays_regular_hours, detail.todays_overtime_hours = calculate_regular_and_overtime_hours(detail.todays_total_hours)
            detail.todays_labor_cost = calculate_pay_with_overtime(detail.todays_regular_hours, detail.todays_overtime_hours, hourly_wage)
        
        # Process this week's time logs for this employee
        employee_week_logs = [log for log in week_logs if log.employee_id == employee_id]
        if employee_week_logs:
            detail.weekly_total_hours = calculate_hours_from_logs(employee_week_logs, now)
            detail.weekly_regular_hours, detail.weekly_overtime_hours = calculate_regular_and_overtime_hours(detail.weekly_total_hours)
            detail.weekly_labor_cost = calculate_pay_with_overtime(detail.weekly_regular_hours, detail.weekly_overtime_hours, hourly_wage)
        
        # Process vacation for today
        employee_vacation_today = [v for v in vacation_today if v.employee_id == employee_id]
        if employee_vacation_today:
            detail.todays_vacation_hours = sum(v.hours for v in employee_vacation_today)
            detail.todays_vacation_cost = detail.todays_vacation_hours * hourly_wage
        
        # Calculate total cost for today (work + vacation)
        detail.todays_total_cost = detail.todays_labor_cost + detail.todays_vacation_cost
        
        employee_details.append(detail)
        
        # Add to summary totals
        summary.todays_total_work_hours += detail.todays_total_hours
        summary.todays_total_vacation_hours += detail.todays_vacation_hours
        summary.todays_total_work_cost += detail.todays_labor_cost
        summary.todays_total_vacation_cost += detail.todays_vacation_cost
        summary.todays_regular_hours += detail.todays_regular_hours
        summary.todays_overtime_hours += detail.todays_overtime_hours
        summary.weekly_total_hours += detail.weekly_total_hours
        summary.weekly_regular_hours += detail.weekly_regular_hours
        summary.weekly_overtime_hours += detail.weekly_overtime_hours
        summary.weekly_total_cost += detail.weekly_labor_cost
        
        if is_active:
            summary.current_hourly_labor_rate += hourly_wage
    
    # Calculate summary metrics
    summary.total_employees = len(all_employees)
    summary.active_employees_today = len(employees_who_worked_today | employees_currently_active)
    summary.employees_who_clocked_in_today = len(employees_who_worked_today)
    summary.employees_currently_clocked_in = len(employees_currently_active)
    
    summary.todays_total_combined_hours = summary.todays_total_work_hours + summary.todays_total_vacation_hours
    summary.todays_total_labor_cost = summary.todays_total_work_cost + summary.todays_total_vacation_cost
    
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
            total_overtime_cost += detail.todays_overtime_hours * detail.hourly_wage * 1.5
    
    summary.todays_regular_cost = total_regular_cost
    summary.todays_overtime_cost = total_overtime_cost
    
    # Calculate averages
    if summary.total_employees > 0:
        summary.average_hourly_wage = total_wages / summary.total_employees
        summary.cost_per_employee_today = summary.todays_total_labor_cost / summary.total_employees
        summary.hours_per_employee_today = summary.todays_total_combined_hours / summary.total_employees
    
    if summary.todays_total_combined_hours > 0:
        summary.weighted_average_hourly_rate = total_weighted_hours / summary.todays_total_combined_hours
    
    # Count clock activities
    summary.total_clock_ins_today = len([log for log in today_logs if log.punch_type == PunchType.CLOCK_IN])
    summary.total_clock_outs_today = len([log for log in today_logs if log.punch_type == PunchType.CLOCK_OUT])
    
    # Sort employees for insights
    employee_details.sort(key=lambda x: x.employee_name or "")
    
    # Top performers
    top_earners = sorted(employee_details, key=lambda x: x.todays_total_cost, reverse=True)[:5]
    most_hours = sorted(employee_details, key=lambda x: x.todays_total_hours, reverse=True)[:5]
    
    print(f"Analysis complete. Summary: {summary.total_employees} employees, ${summary.todays_total_labor_cost:.2f} total cost today")
    
    return ComprehensiveLaborSpendResponse(
        summary=summary,
        employees=employee_details,
        top_earners_today=top_earners,
        most_hours_today=most_hours,
        data_generated_at=now
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

@router.get("/dealership/{dealership_id}/labor-preview", response_model=QuickLaborPreview)
async def get_labor_preview(
    dealership_id: str,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
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
    start_of_today = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_today = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all employees with their wages
    users_ref = firestore_db.collection("users").where("role", "==", "employee").stream()
    employee_wages = {}
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        hourly_wage = float(user_data.get("hourlyWage", 0.0)) if user_data.get("hourlyWage") else 0.0
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
    
    print(f"Found {len(today_logs)} time logs and {len(vacation_today)} vacation entries for today")
    
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
        regular_hours, overtime_hours = calculate_regular_and_overtime_hours(hours_worked)
        cost = calculate_pay_with_overtime(regular_hours, overtime_hours, hourly_wage)
        total_work_cost += cost
        
        # Check if currently active
        is_active, _ = await is_employee_currently_active(session, employee_id, dealership_id)
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
    hours_into_workday = (now.hour - 8) if now.hour >= 8 else 0  # Assume workday starts at 8 AM
    hours_remaining_in_workday = max(0, 8 - hours_into_workday)  # Assume 8-hour workday
    projected_additional_cost = current_burn_rate * hours_remaining_in_workday
    projected_daily_cost = total_work_cost + projected_additional_cost
    
    # Calculate averages
    total_employees_today = len(employees_who_worked)
    average_cost_per_employee = (total_work_cost + total_vacation_cost) / total_employees_today if total_employees_today > 0 else 0.0
    
    print(f"Preview calculated: ${total_work_cost + total_vacation_cost:.2f} total cost, {len(employees_currently_active)} currently active")
    
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
        projected_daily_cost=projected_daily_cost
    )

@router.get("/all-dealerships/labor-costs-today", response_model=AllDealershipsLaborCostResponse)
async def get_all_dealerships_labor_costs_today(
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role)
):
    """
    Get today's total labor costs for ALL dealerships.
    
    Super lightweight endpoint that returns just the money spent on labor today
    for each dealership. Perfect for company-wide dashboard overview.
    
    Returns:
    - Each dealership's total labor cost today (work + vacation)
    - Company-wide total
    - Current timestamp
    """
    print(f"\n--- Getting labor costs for all dealerships ---")
    
    now = datetime.now(timezone.utc)
    today = now.date()
    start_of_today = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_today = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Get all dealerships
    dealerships_ref = firestore_db.collection("dealerships").stream()
    dealership_ids = [doc.id for doc in dealerships_ref]
    
    print(f"Found {len(dealership_ids)} dealerships to analyze")
    
    # Get all employees with their wages (do this once)
    users_ref = firestore_db.collection("users").where("role", "==", "employee").stream()
    employee_wages = {}
    for doc in users_ref:
        user_data = doc.to_dict()
        employee_id = doc.id
        hourly_wage = float(user_data.get("hourlyWage", 0.0)) if user_data.get("hourlyWage") else 0.0
        employee_wages[employee_id] = hourly_wage
    
    # Get all time logs for today (all dealerships)
    all_today_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_of_today)
        .where(TimeLog.timestamp <= end_of_today)
        .order_by(TimeLog.timestamp.asc())
    ).all()
    
    # Get all vacation for today (all dealerships)
    all_vacation_today = session.exec(
        select(VacationTime)
        .where(VacationTime.date == today)
    ).all()
    
    print(f"Found {len(all_today_logs)} total time logs and {len(all_vacation_today)} vacation entries for today")
    
    # Group data by dealership
    dealership_logs = {}
    dealership_vacation = {}
    
    for log in all_today_logs:
        if log.dealership_id not in dealership_logs:
            dealership_logs[log.dealership_id] = []
        dealership_logs[log.dealership_id].append(log)
    
    for vacation in all_vacation_today:
        if vacation.dealership_id not in dealership_vacation:
            dealership_vacation[vacation.dealership_id] = []
        dealership_vacation[vacation.dealership_id].append(vacation)
    
    # Calculate costs for each dealership
    dealership_costs = []
    total_company_cost = 0.0
    
    for dealership_id in dealership_ids:
        dealership_total_cost = 0.0
        
        # Calculate work costs
        logs = dealership_logs.get(dealership_id, [])
        if logs:
            # Group by employee
            employee_logs = {}
            for log in logs:
                if log.employee_id not in employee_logs:
                    employee_logs[log.employee_id] = []
                employee_logs[log.employee_id].append(log)
            
            # Calculate cost for each employee
            for employee_id, emp_logs in employee_logs.items():
                hourly_wage = employee_wages.get(employee_id, 0.0)
                hours_worked = calculate_hours_from_logs(emp_logs, now)
                regular_hours, overtime_hours = calculate_regular_and_overtime_hours(hours_worked)
                cost = calculate_pay_with_overtime(regular_hours, overtime_hours, hourly_wage)
                dealership_total_cost += cost
        
        # Calculate vacation costs
        vacations = dealership_vacation.get(dealership_id, [])
        for vacation in vacations:
            hourly_wage = employee_wages.get(vacation.employee_id, 0.0)
            vacation_cost = vacation.hours * hourly_wage
            dealership_total_cost += vacation_cost
        
        dealership_costs.append(DealershipLaborCost(
            dealership_id=dealership_id,
            total_labor_cost_today=dealership_total_cost
        ))
        total_company_cost += dealership_total_cost
        
        print(f"Dealership {dealership_id}: ${dealership_total_cost:.2f}")
    
    # Sort by cost (highest first)
    dealership_costs.sort(key=lambda x: x.total_labor_cost_today, reverse=True)
    
    print(f"Total company labor cost today: ${total_company_cost:.2f}")
    
    return AllDealershipsLaborCostResponse(
        analysis_date=today.isoformat(),
        total_company_labor_cost=total_company_cost,
        dealerships=dealership_costs,
        analysis_time=now
    )
