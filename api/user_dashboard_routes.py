from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel, ConfigDict, field_serializer
from typing import List, Optional
from datetime import datetime, timedelta, timezone, date, time
from db.session import get_session #
from core.deps import get_current_user #
from core.firebase import db as firestore_db #
from models.time_log import TimeLog, PunchType #
from models.vacation_time import VacationTime #
from utils.datetime_helpers import format_utc_datetime
from models.employee_schedule import EmployeeScheduledShift, ShiftStatus

router = APIRouter()

# --- Pydantic Models for Responses ---

class CurrentShiftDurationResponse(BaseModel):
    shift_duration_seconds: Optional[float] = None
    shift_start_time: Optional[datetime] = None
    message: str

    @field_serializer('shift_start_time')
    def serialize_shift_start_time(self, dt: Optional[datetime]) -> Optional[str]:
        """Ensure shift_start_time is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)

class UserWageResponse(BaseModel):
    hourly_wage: Optional[float] = None
    message: str

class CurrentShiftEarningsResponse(BaseModel):
    current_earnings: Optional[float] = None
    shift_duration_hours: Optional[float] = None
    hourly_wage: Optional[float] = None
    message: str

class WeeklyHoursResponse(BaseModel):
    total_hours_worked: float
    week_start_date: datetime
    week_end_date: datetime
    message: str

    @field_serializer('week_start_date', 'week_end_date')
    def serialize_dates(self, dt: datetime) -> str:
        """Ensure dates are formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)

class PunchLogResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    dealership_id: str
    timestamp: datetime
    punch_type: PunchType
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # New injury reporting fields (only present on clockout entries)
    injured_at_work: Optional[bool] = None
    safety_signature: Optional[str] = None

    @field_serializer('timestamp')
    def serialize_timestamp(self, dt: datetime) -> str:
        """Ensure timestamp is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)

class PastPunchesResponse(BaseModel):
    punches: List[PunchLogResponse]
    message: str

class WeeklyOvertimeHoursResponse(BaseModel):
    overtime_hours_worked: float
    total_hours_worked: float
    week_start_date: datetime
    week_end_date: datetime
    overtime_threshold: float = 40.0
    message: str

    @field_serializer('week_start_date', 'week_end_date')
    def serialize_dates(self, dt: datetime) -> str:
        """Ensure dates are formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)

class UserOvertimeWageResponse(BaseModel):
    regular_hourly_wage: Optional[float] = None
    overtime_hourly_wage: Optional[float] = None
    message: str

class UserBaseWageInfoResponse(BaseModel):
    regular_hourly_rate: Optional[float] = None
    overtime_multiplier: float = 1.5
    overtime_threshold_hours: float = 40.0 # Weekly threshold
    message: str

# Pydantic models for the new daily breakdown endpoint
class DailyHoursItem(BaseModel):
    date: str # YYYY-MM-DD
    total_hours: float
    regular_hours: float
    overtime_hours: float
    estimated_earnings: float

class WeeklyTotalItem(BaseModel):
    week_start_date: str # YYYY-MM-DD
    week_end_date: str # YYYY-MM-DD
    total_hours: float
    total_earnings: float

class CumulativeTotals(BaseModel):
    total_hours_past_N_weeks: float
    total_earnings_past_N_weeks: float

class DailyBreakdownResponse(BaseModel):
    daily_hours: List[DailyHoursItem]
    weekly_totals: List[WeeklyTotalItem]
    cumulative_totals: Optional[CumulativeTotals] = None

# --- Pydantic models for the new SINGLE WEEKLY breakdown endpoint ---
class SingleWeekDailySummary(BaseModel):
    date: str # YYYY-MM-DD
    day_name: str # e.g., Monday, Tuesday
    total_hours: float
    regular_hours: float
    overtime_hours: float # Calculated against a weekly threshold
    estimated_earnings: float

class SingleWeeklyTotal(BaseModel):
    week_start_date: str # YYYY-MM-DD
    week_end_date: str # YYYY-MM-DD
    total_hours: float
    total_regular_hours: float
    total_overtime_hours: float
    total_estimated_earnings: float

class WeeklyBreakdownResponse(BaseModel):
    daily_summaries: List[SingleWeekDailySummary]
    weekly_total: SingleWeeklyTotal
    message: Optional[str] = None

# --- Pydantic model for the new DAILY summary endpoint ---
class DailySummaryResponse(BaseModel):
    target_date: str # YYYY-MM-DD
    total_hours_today: float
    total_earnings_today: float
    message: Optional[str] = None

# --- Vacation Time Models ---

class VacationTimeEntry(BaseModel):
    id: int
    date: date
    hours: float
    vacation_type: str
    notes: Optional[str] = None
    created_at: datetime
    # Financial calculations
    hourly_wage: Optional[float] = None
    vacation_pay: Optional[float] = None

    @field_serializer('created_at')
    def serialize_created_at(self, dt: datetime) -> str:
        """Ensure created_at is formatted as UTC with Z suffix"""
        return format_utc_datetime(dt)

class UserVacationSummaryResponse(BaseModel):
    total_vacation_hours: float
    total_vacation_pay: float
    vacation_entries: List[VacationTimeEntry]
    message: str

class UpcomingShiftResponse(BaseModel):
    dealership_name: str
    shift_date: date
    start_time: time
    end_time: time
    status: ShiftStatus
    notes: Optional[str] = None

# --- Helper Functions ---

async def get_user_wage_from_firestore(user_id: str) -> Optional[float]:

    # Pulls Docx Location
    user_ref = firestore_db.collection("users").document(user_id)

    # Pulls Docx
    user_doc = await user_ref.get()

    # Pulls Wage Field If Exists; Else None
    if user_doc.exists:
        return user_doc.to_dict().get("hourlyWage")
    return None

# --- API Endpoints ---

@router.get("/shift/current_duration", response_model=CurrentShiftDurationResponse)
async def get_current_shift_duration(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
   
   # Pull UID
    user_id = current_user["uid"]

    # Get Last Punch From DB
    last_punch = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .order_by(TimeLog.timestamp.desc())
    ).first()

    # If They Haven't Previously Punched Or Last Punch was OUt
    if not last_punch or last_punch.punch_type == PunchType.CLOCK_OUT:
        return CurrentShiftDurationResponse(message="User is not currently clocked in.")

    # Store Start time
    shift_start_time = last_punch.timestamp
   
   # Conv to UTC Universally
    if shift_start_time.tzinfo is None:
        shift_start_time = shift_start_time.replace(tzinfo=timezone.utc)
    
    # Compare To Current Second
    now_utc = datetime.now(timezone.utc)
    duration = now_utc - shift_start_time
    
    # Return Durration
    return CurrentShiftDurationResponse(
        shift_duration_seconds=duration.total_seconds(),
        shift_start_time=shift_start_time,
        message="Current shift duration calculated."
    )

@router.get("/wage", response_model=UserWageResponse)
async def get_user_wage_endpoint(
    current_user: dict = Depends(get_current_user),
):
    
    # Pulls User ID
    user_id = current_user["uid"]
 
    try:

        # Finds Specific Users Docx
        user_ref = firestore_db.collection("users").document(user_id)

        # Pulls User Docx
        user_doc = user_ref.get() 

        # Makes Sure It Exists
        if user_doc.exists:

            # Extract Hourly Wage Key
            hourly_wage = user_doc.to_dict().get("hourlyWage")

            # Ensure Key Exists
            if hourly_wage is not None:
                return UserWageResponse(hourly_wage=hourly_wage, message="User wage retrieved.")
            else:
                return UserWageResponse(message="Hourly wage not set for this user.")
        else:
           
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found.")
    except Exception as e:
       
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not retrieve user wage: {str(e)}")


@router.get("/shift/current_earnings", response_model=CurrentShiftEarningsResponse)
async def get_current_shift_earnings(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    # Pull User ID
    user_id = current_user["uid"]

    # Get current shift's last punch (which should be a CLOCK_IN)
    current_shift_start_punch = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .order_by(TimeLog.timestamp.desc())
    ).first()

    # Make Sure Clocked In Currently
    if not current_shift_start_punch or current_shift_start_punch.punch_type == PunchType.CLOCK_OUT:
        return CurrentShiftEarningsResponse(message="User is not currently clocked in. No earnings to calculate.")

    # Current shift start time, ensure timezone aware (UTC)
    current_shift_start_time = current_shift_start_punch.timestamp
    if current_shift_start_time.tzinfo is None: # Assuming UTC if naive
        current_shift_start_time = current_shift_start_time.replace(tzinfo=timezone.utc)
    
    # Calculate current shift duration so far
    now_utc = datetime.now(timezone.utc)
    current_shift_duration_seconds = (now_utc - current_shift_start_time).total_seconds()
    current_shift_duration_hours = current_shift_duration_seconds / 3600

    # Get user's hourly wage from Firestore
    hourly_wage: Optional[float] = None
    try:
        user_ref = firestore_db.collection("users").document(user_id)
        user_doc = user_ref.get() # Removed await here
        if user_doc.exists:
            hourly_wage = user_doc.to_dict().get("hourlyWage")
    except Exception as e:
        # Log the exception e if you have logging setup
        print(f"Error fetching wage for {user_id}: {e}") # Basic print for now
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not retrieve user wage for earnings calculation: {str(e)}")

    if hourly_wage is None or not isinstance(hourly_wage, (int, float)) or hourly_wage <=0: # also check for valid wage
        return CurrentShiftEarningsResponse(
            shift_duration_hours=round(current_shift_duration_hours, 2),
            message="Hourly wage not set or invalid. Cannot calculate earnings."
        )

    # --- Overtime Calculation ---
    # Determine start of the current week (Monday)
    today = now_utc.date()
    start_of_week_dt = now_utc - timedelta(days=today.weekday())
    start_of_week_dt = start_of_week_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    # Fetch punches for this week *before* the current shift started
    past_punches_this_week = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= start_of_week_dt)
        .where(TimeLog.timestamp < current_shift_start_time) # Exclude current shift's start punch
        .order_by(TimeLog.timestamp.asc())
    ).all()

    hours_this_week_before_current_shift = 0.0
    previous_clock_in_time: Optional[datetime] = None

    for punch in past_punches_this_week:
        punch_ts = punch.timestamp
        if punch_ts.tzinfo is None:
            punch_ts = punch_ts.replace(tzinfo=timezone.utc)

        if punch.punch_type == PunchType.CLOCK_IN:
            previous_clock_in_time = punch_ts
        elif punch.punch_type == PunchType.CLOCK_OUT and previous_clock_in_time:
            duration = (punch_ts - previous_clock_in_time).total_seconds()
            hours_this_week_before_current_shift += duration / 3600
            previous_clock_in_time = None
    
    # If there was a clock_in without a clock_out before current shift within this week (unlikely but handle)
    # This part might be complex if a shift spans across the start_of_week_dt or current_shift_start_time.
    # For simplicity, assuming complete pairs for past shifts.

    # Calculate regular and overtime hours for the current shift
    overtime_threshold = 40.0
    regular_rate = hourly_wage
    overtime_rate = hourly_wage * 1.5

    regular_hours_this_shift = 0.0
    overtime_hours_this_shift = 0.0

    if hours_this_week_before_current_shift >= overtime_threshold:
        overtime_hours_this_shift = current_shift_duration_hours
    else:
        potential_regular_hours = overtime_threshold - hours_this_week_before_current_shift
        regular_hours_this_shift = min(current_shift_duration_hours, potential_regular_hours)
        overtime_hours_this_shift = current_shift_duration_hours - regular_hours_this_shift
    
    current_earnings = (regular_hours_this_shift * regular_rate) + \
                       (overtime_hours_this_shift * overtime_rate)

    return CurrentShiftEarningsResponse(
        current_earnings=round(current_earnings, 2),
        shift_duration_hours=round(current_shift_duration_hours, 2),
        hourly_wage=hourly_wage, # Could also return effective_rate or breakdown
        message="Current shift earnings calculated, including overtime."
    )


@router.get("/work_hours/current_week", response_model=WeeklyHoursResponse)
async def get_weekly_hours(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    # Pull User ID
    user_id = current_user["uid"]

    # Get Current Time
    now = datetime.now(timezone.utc)
    
    # Determine Start & End of Week
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)

    # Pull All the Punches THis Week
    punches_this_week = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= start_of_week)
        .where(TimeLog.timestamp <= end_of_week)
        .order_by(TimeLog.timestamp.asc())
    ).all()


    # Accumulate Time Worked
    total_seconds_worked = 0
    clock_in_time: Optional[datetime] = None

    # Loop Through All punches
    for punch in punches_this_week:

        # Store Time Stamp of Unknown Action (IN/OUT)
        punch_timestamp = punch.timestamp

        # Ensure timezone aware for comparison
        if punch_timestamp.tzinfo is None: 
            punch_timestamp = punch_timestamp.replace(tzinfo=timezone.utc)

        # Specificy based on Punch Type
        if punch.punch_type == PunchType.CLOCK_IN:
            clock_in_time = punch_timestamp
        elif punch.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            duration = punch_timestamp - clock_in_time
            total_seconds_worked += duration.total_seconds()
            clock_in_time = None # Reset for the next pair

    # Convert to Useful Metric
    total_hours_worked = total_seconds_worked / 3600

    # Return Object
    return WeeklyHoursResponse(
        total_hours_worked=round(total_hours_worked, 2),
        week_start_date=start_of_week,
        week_end_date=end_of_week,
        message="Total hours worked this week calculated."
    )

@router.get("/work_hours/current_week_overtime", response_model=WeeklyOvertimeHoursResponse)
async def get_weekly_overtime_hours(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["uid"]
    now = datetime.now(timezone.utc)
    
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week_boundary_for_query = start_of_week + timedelta(days=7) # Query up to end of Sunday

    # Display end_of_week for response (Sunday 23:59:59...)
    actual_end_of_week_display = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)

    punches_this_week = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= start_of_week)
        .where(TimeLog.timestamp < end_of_week_boundary_for_query) # Use < for end of day
        .order_by(TimeLog.timestamp.asc())
    ).all()

    total_seconds_worked = 0
    clock_in_time: Optional[datetime] = None

    for punch in punches_this_week:
        punch_timestamp = punch.timestamp
        if punch_timestamp.tzinfo is None:
            punch_timestamp = punch_timestamp.replace(tzinfo=timezone.utc)

        if punch.punch_type == PunchType.CLOCK_IN:
            # If there's a lingering clock_in_time, it means a missed clock_out, ignore previous.
            clock_in_time = punch_timestamp
        elif punch.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            # Ensure clock_out is after clock_in to avoid negative duration if data is messy
            if punch_timestamp > clock_in_time:
                duration = punch_timestamp - clock_in_time
                total_seconds_worked += duration.total_seconds()
            clock_in_time = None # Reset for the next pair
    
    # If the user is currently clocked in (last punch in sequence was CLOCK_IN and within the week)
    if clock_in_time is not None and clock_in_time < now : # Make sure clock_in_time is in the past
        # Ensure this clock_in_time is within the current week before adding duration to now
        # This check is implicitly handled by the query, but explicit thought is good.
        duration_of_current_shift = now - clock_in_time
        total_seconds_worked += duration_of_current_shift.total_seconds()

    total_hours_worked = total_seconds_worked / 3600
    overtime_threshold = 40.0
    overtime_hours_worked = max(0, total_hours_worked - overtime_threshold)

    return WeeklyOvertimeHoursResponse(
        total_hours_worked=round(total_hours_worked, 2),
        overtime_hours_worked=round(overtime_hours_worked, 2),
        week_start_date=start_of_week,
        week_end_date=actual_end_of_week_display,
        overtime_threshold=overtime_threshold,
        message="Weekly overtime hours calculated."
    )

@router.get("/wage/overtime", response_model=UserOvertimeWageResponse)
async def get_user_overtime_wage(
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["uid"]
    regular_wage: Optional[float] = None
    overtime_wage: Optional[float] = None
    message: str

    try:
        user_ref = firestore_db.collection("users").document(user_id)
        user_doc = user_ref.get() # Removed await here

        if user_doc.exists:
            user_data = user_doc.to_dict()
            regular_wage = user_data.get("hourlyWage")

            if regular_wage is not None and isinstance(regular_wage, (int, float)) and regular_wage > 0:
                overtime_wage = round(regular_wage * 1.5, 2)
                message = "Overtime wage calculated."
            elif regular_wage is not None: # Wage is present but invalid (e.g. 0 or negative)
                 message = "Regular hourly wage is set to an invalid value. Cannot calculate overtime wage."
            else: # Wage is None
                message = "Regular hourly wage not set. Cannot calculate overtime wage."
        else:
            message = "User profile not found. Cannot determine wage."
            # Consider raising HTTPException 404 here if preferred
            # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found.")

    except Exception as e:
        # Log error e
        print(f"Error fetching overtime wage for {user_id}: {e}")
        # Avoid raising HTTPException here to still return a response model if desired,
        # or raise it if that's preferred behavior.
        # For now, return message within the model.
        message = f"An error occurred while retrieving wage information: {str(e)}"
        # Optionally:
        # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not retrieve user overtime wage: {str(e)}")


    return UserOvertimeWageResponse(
        regular_hourly_wage=regular_wage if isinstance(regular_wage, (int, float)) else None,
        overtime_hourly_wage=overtime_wage,
        message=message
    )

@router.get("/wage/base_rate", response_model=UserBaseWageInfoResponse)
async def get_user_base_wage_info(
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["uid"]
    regular_wage: Optional[float] = None
    message: str
    overtime_multiplier = 1.5  # Standard value
    overtime_threshold_hours = 40.0  # Standard value

    try:
        user_ref = firestore_db.collection("users").document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            regular_wage = user_data.get("hourlyWage")

            if regular_wage is not None and isinstance(regular_wage, (int, float)) and regular_wage > 0:
                message = "User base wage information retrieved."
            elif regular_wage is not None:
                message = "Regular hourly wage is set to an invalid value."
            else:
                message = "Regular hourly wage not set for this user."
        else:
            message = "User profile not found."
            # Consider raising HTTPException 404 here if preferred
            # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found.")
            return UserBaseWageInfoResponse(message=message, regular_hourly_rate=None)


    except Exception as e:
        print(f"Error fetching base wage info for {user_id}: {e}")
        message = f"An error occurred while retrieving user base wage information: {str(e)}"
        # Optionally:
        # raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
        return UserBaseWageInfoResponse(message=message, regular_hourly_rate=None)

    return UserBaseWageInfoResponse(
        regular_hourly_rate=regular_wage if isinstance(regular_wage, (int, float)) else None,
        overtime_multiplier=overtime_multiplier,
        overtime_threshold_hours=overtime_threshold_hours,
        message=message
    )

@router.get("/work_hours/daily_breakdown", response_model=DailyBreakdownResponse)
async def get_daily_work_hours_breakdown(
    weeks: int,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["uid"]
    weekly_overtime_threshold_hours = 40.0 # For weekly overtime calculation

    # Fetch user's wage info
    regular_hourly_rate: Optional[float] = None
    overtime_multiplier: float = 1.5 # Default
    
    try:
        user_ref = firestore_db.collection("users").document(user_id)
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            regular_hourly_rate = user_data.get("hourlyWage")
            # Potentially fetch overtime_multiplier and weekly_overtime_threshold_hours if stored per user
            # For now, using defaults set above.
            if not (regular_hourly_rate and isinstance(regular_hourly_rate, (int, float)) and regular_hourly_rate > 0):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User hourly wage not set or invalid.")
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found.")
    except Exception as e:
        # Log error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not retrieve user wage information: {str(e)}")

    overtime_rate = regular_hourly_rate * overtime_multiplier

    # Determine date range
    now_utc = datetime.now(timezone.utc)
    # Go back to the start of the week for 'weeks-1' ago, then include the current partial week.
    # Example: if weeks=1, we want current week's data up to today.
    # if weeks=3, we want last 2 full weeks + current partial week.
    # So, start_date is (weeks-1) weeks before the start of the current week.
    
    # Start of the current week (Monday)
    start_of_current_week = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_utc.weekday())
    
    # Calculate the very first day to fetch punches from
    # If weeks = 1, start_date_for_query is start_of_current_week
    # If weeks = N, start_date_for_query is (N-1) weeks before start_of_current_week
    start_date_for_query = start_of_current_week - timedelta(weeks=weeks -1)
    
    # Fetch all punches in the date range
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= start_date_for_query)
        .where(TimeLog.timestamp <= now_utc) # Up to current moment
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Process punches into daily summaries
    daily_data_map = {} # Key: "YYYY-MM-DD", Value: total_seconds_worked

    last_clock_in_time: Optional[datetime] = None
    for punch in punches:
        punch_time_utc = punch.timestamp.replace(tzinfo=timezone.utc) if punch.timestamp.tzinfo is None else punch.timestamp

        if punch.punch_type == PunchType.CLOCK_IN:
            last_clock_in_time = punch_time_utc
        elif punch.punch_type == PunchType.CLOCK_OUT and last_clock_in_time:
            if punch_time_utc > last_clock_in_time: # Ensure clock out is after clock in
                
                # Distribute hours across days if a shift spans midnight
                current_process_time = last_clock_in_time
                while current_process_time < punch_time_utc:
                    day_str = current_process_time.strftime("%Y-%m-%d")
                    
                    # End of the current day for current_process_time
                    end_of_day_for_current_process_time = (current_process_time + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    # Segment end is either the actual punch_out_time or the end of the current_process_time's day
                    segment_end_time = min(punch_time_utc, end_of_day_for_current_process_time)
                    
                    duration_seconds_on_day = (segment_end_time - current_process_time).total_seconds()
                    
                    if day_str not in daily_data_map:
                        daily_data_map[day_str] = 0.0
                    daily_data_map[day_str] += duration_seconds_on_day
                    
                    current_process_time = segment_end_time # Move to the start of the next segment/day

            last_clock_in_time = None # Reset for next pair

    # Handle currently active shift (if any)
    if last_clock_in_time and last_clock_in_time < now_utc : # It's an open shift
        current_process_time = last_clock_in_time
        while current_process_time < now_utc:
            day_str = current_process_time.strftime("%Y-%m-%d")
            end_of_day_for_current_process_time = (current_process_time + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            segment_end_time = min(now_utc, end_of_day_for_current_process_time)
            duration_seconds_on_day = (segment_end_time - current_process_time).total_seconds()
            if day_str not in daily_data_map:
                daily_data_map[day_str] = 0.0
            daily_data_map[day_str] += duration_seconds_on_day
            current_process_time = segment_end_time


    # Create DailyHoursItem list
    daily_hours_list: List[DailyHoursItem] = []
    
    # Ensure all days in the range are present, even if no hours worked
    # Iterate from start_date_for_query up to today
    current_day_iterator = start_date_for_query
    while current_day_iterator.date() <= now_utc.date():
        day_str_iter = current_day_iterator.strftime("%Y-%m-%d")
        if day_str_iter not in daily_data_map:
            daily_data_map[day_str_iter] = 0.0 # Add day with 0 hours if not present
        current_day_iterator += timedelta(days=1)
    
    all_dates_sorted = sorted(daily_data_map.keys())

    # Process each day with sophisticated weekly overtime calculation
    for date_str in all_dates_sorted:
        current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        total_seconds = daily_data_map.get(date_str, 0.0)
        total_hours_day = round(total_seconds / 3600, 2)

        # Find the start of the week for this day (Monday)
        days_since_monday = current_date.weekday()
        week_start_date = current_date - timedelta(days=days_since_monday)
        
        # Calculate hours worked earlier in this week (before current day)
        hours_worked_earlier_this_week = 0.0
        for i in range(days_since_monday):
            earlier_date = week_start_date + timedelta(days=i)
            earlier_date_str = earlier_date.strftime("%Y-%m-%d")
            if earlier_date_str in daily_data_map:
                hours_worked_earlier_this_week += daily_data_map[earlier_date_str] / 3600
        
        # Calculate how many of today's hours are regular vs overtime
        hours_remaining_before_overtime = max(0, weekly_overtime_threshold_hours - hours_worked_earlier_this_week)
        
        if hours_remaining_before_overtime >= total_hours_day:
            # All of today's hours are regular
            daily_reg_hours = total_hours_day
            daily_ot_hours = 0.0
        else:
            # Some or all of today's hours are overtime
            daily_reg_hours = hours_remaining_before_overtime
            daily_ot_hours = total_hours_day - hours_remaining_before_overtime
        
        # Round for consistency
        daily_reg_hours = round(daily_reg_hours, 2)
        daily_ot_hours = round(daily_ot_hours, 2)

        # Calculate accurate daily earnings
        daily_earnings = (daily_reg_hours * regular_hourly_rate) + (daily_ot_hours * overtime_rate)
        
        daily_hours_list.append(DailyHoursItem(
            date=date_str,
            total_hours=total_hours_day,
            regular_hours=daily_reg_hours,
            overtime_hours=daily_ot_hours,
            estimated_earnings=round(daily_earnings, 2)
        ))

    # Calculate Weekly Totals
    weekly_totals_list: List[WeeklyTotalItem] = []
    
    # Group daily hours by week
    weeks_map = {}  # Key: week_start_date_str, Value: list of daily items for that week
    
    for daily_item in daily_hours_list:
        daily_date = datetime.strptime(daily_item.date, "%Y-%m-%d").date()
        week_start = daily_date - timedelta(days=daily_date.weekday())
        week_start_str = week_start.strftime("%Y-%m-%d")
        
        if week_start_str not in weeks_map:
            weeks_map[week_start_str] = []
        weeks_map[week_start_str].append(daily_item)
    
    # Calculate totals for each week
    for week_start_str in sorted(weeks_map.keys()):
        week_days = weeks_map[week_start_str]
        week_start_date = datetime.strptime(week_start_str, "%Y-%m-%d").date()
        week_end_date = min(week_start_date + timedelta(days=6), now_utc.date())
        
        total_hours_week = sum(day.total_hours for day in week_days)
        total_earnings_week = sum(day.estimated_earnings for day in week_days)
        
        weekly_totals_list.append(WeeklyTotalItem(
            week_start_date=week_start_str,
            week_end_date=week_end_date.strftime("%Y-%m-%d"),
            total_hours=round(total_hours_week, 2),
            total_earnings=round(total_earnings_week, 2)
        ))

    # Cumulative Totals
    cumulative_total_hours = sum(item.total_hours for item in daily_hours_list)
    cumulative_total_earnings = sum(item.estimated_earnings for item in daily_hours_list)

    cumulative_totals_obj = CumulativeTotals(
        total_hours_past_N_weeks=round(cumulative_total_hours, 2),
        total_earnings_past_N_weeks=round(cumulative_total_earnings, 2)
    )

    return DailyBreakdownResponse(
        daily_hours=daily_hours_list,
        weekly_totals=weekly_totals_list,
        cumulative_totals=cumulative_totals_obj
    )

@router.get("/punch_history/past_three_weeks", response_model=PastPunchesResponse)
async def get_punch_history_past_three_weeks(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    # Pull ID
    user_id = current_user["uid"]

    # Figure Out What Day It was three weeks ago
    now = datetime.now(timezone.utc)
    three_weeks_ago = now - timedelta(weeks=3)


    # Start @ 12:00am First Day
    three_weeks_ago = three_weeks_ago.replace(hour=0, minute=0, second=0, microsecond=0)

    # Pull all the punches
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= three_weeks_ago)
        .order_by(TimeLog.timestamp.desc()) # Typically newest first is preferred for history
    ).all()
    
    # Convert to PunchLogResponse model
    response_punches = [PunchLogResponse.model_validate(punch) for punch in punches]

    # Make Sure Exists
    if not response_punches:
        return PastPunchesResponse(punches=[], message="No punch history found for the past three weeks.")

    print(PastPunchesResponse(
        punches=response_punches,
        message="Punch history for the past three weeks retrieved."
    ))

    # Return All Punches Exists
    return PastPunchesResponse(
        punches=response_punches,
        message="Punch history for the past three weeks retrieved."
    )

@router.get("/debug/user-info")
async def debug_user_info(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    Debug endpoint to help identify employee_id format issues.
    Shows user's UID and recent TimeLog entries.
    """
    user_id = current_user["uid"]
    
    # Get all TimeLog entries for this user (last 10)
    recent_punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .order_by(TimeLog.timestamp.desc())
        .limit(10)
    ).all()
    
    # Get all TimeLog entries with admin_modifier_id set (last 10)
    admin_created_punches = session.exec(
        select(TimeLog)
        .where(TimeLog.admin_modifier_id.is_not(None))
        .order_by(TimeLog.timestamp.desc())
        .limit(10)
    ).all()
    
    return {
        "user_firebase_uid": user_id,
        "user_firebase_uid_length": len(user_id),
        "recent_punches_for_this_user": [
            {
                "id": punch.id,
                "employee_id": punch.employee_id,
                "timestamp": format_utc_datetime(punch.timestamp),
                "punch_type": punch.punch_type,
                "admin_created": punch.admin_modifier_id is not None,
                "admin_notes": punch.admin_notes
            }
            for punch in recent_punches
        ],
        "recent_admin_created_punches_all_users": [
            {
                "id": punch.id,
                "employee_id": punch.employee_id,
                "employee_id_length": len(punch.employee_id),
                "timestamp": format_utc_datetime(punch.timestamp),
                "punch_type": punch.punch_type,
                "admin_modifier_id": punch.admin_modifier_id,
                "admin_notes": punch.admin_notes
            }
            for punch in admin_created_punches
        ]
    }

@router.get("/debug/system-time")
async def debug_system_time():
    """
    Debug endpoint to check system time and timezone settings.
    """
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now()
    
    return {
        "system_time_utc": format_utc_datetime(now_utc),
        "system_time_local": now_local.isoformat(),
        "current_date_utc": now_utc.date().isoformat(),
        "current_date_local": now_local.date().isoformat(),
        "timezone_info": {
            "utc_offset_hours": (now_local - now_utc).total_seconds() / 3600,
            "local_timezone": str(now_local.tzinfo) if now_local.tzinfo else "None (naive)"
        }
    }

@router.get("/work_hours/weekly_breakdown", response_model=WeeklyBreakdownResponse)
async def get_weekly_breakdown(
    week_start_date: date, # Expects YYYY-MM-DD from query
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["uid"]

    # Get user wage info (similar to daily_breakdown)
    user_profile_ref = firestore_db.collection("users").document(user_id)
    user_profile_doc = user_profile_ref.get() # Removed await here
    if not user_profile_doc.exists:
        raise HTTPException(status_code=404, detail="User profile not found for wage information.")
    
    user_data = user_profile_doc.to_dict()
    hourly_wage = user_data.get("hourlyWage")
    overtime_multiplier = user_data.get("overtimeMultiplier", 1.5) # Default to 1.5 if not set
    overtime_threshold_hours = user_data.get("overtimeThresholdHours", 40.0) # Default to 40 if not set

    if hourly_wage is None or not isinstance(hourly_wage, (int, float)) or hourly_wage <= 0:
        raise HTTPException(status_code=400, detail="User hourly wage not set or invalid. Cannot calculate earnings.")

    overtime_wage = hourly_wage * overtime_multiplier

    # Calculate week_end_date
    week_end_date = week_start_date + timedelta(days=6)

    # Convert to datetime for DB query (start of day to end of day)
    start_datetime_utc = datetime.combine(week_start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime_utc = datetime.combine(week_end_date, datetime.max.time(), tzinfo=timezone.utc)

    # Fetch punches for the specified week
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= start_datetime_utc)
        .where(TimeLog.timestamp <= end_datetime_utc)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    daily_hours_map = { (week_start_date + timedelta(days=i)): {"total": 0.0, "punches": []} for i in range(7) }

    for punch in punches:
        punch_date = punch.timestamp.astimezone(timezone.utc).date()
        if punch_date in daily_hours_map:
            daily_hours_map[punch_date]["punches"].append(punch)

    daily_summaries: List[SingleWeekDailySummary] = []
    week_total_hours = 0.0
    week_total_regular_hours = 0.0
    week_total_overtime_hours = 0.0
    week_total_earnings = 0.0

    # Calculate hours per day using consistent admin logic
    for day_offset in range(7):
        current_date = week_start_date + timedelta(days=day_offset)
        day_data = daily_hours_map.get(current_date)
        day_total_hours = 0.0

        if day_data:
            day_punches = sorted(day_data["punches"], key=lambda p: p.timestamp)
            clock_in_time: Optional[datetime] = None
            
            # Use the same logic as admin analytics for consistency
            for punch in day_punches:
                punch_ts = punch.timestamp
                if punch_ts.tzinfo is None:
                    punch_ts = punch_ts.replace(tzinfo=timezone.utc)
                    
                if punch.punch_type == PunchType.CLOCK_IN:
                    clock_in_time = punch_ts
                elif punch.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                    duration_hours = (punch_ts - clock_in_time).total_seconds() / 3600
                    day_total_hours += duration_hours
                    clock_in_time = None

            # Handle currently active shift if it exists at end of day's punches
            if clock_in_time is not None:
                # If the current date is today and user is still clocked in, add time until now
                now_utc = datetime.now(timezone.utc)
                if current_date == now_utc.date():
                    duration_hours = (now_utc - clock_in_time).total_seconds() / 3600
                    day_total_hours += duration_hours

        week_total_hours += day_total_hours
        
        # Calculate regular/overtime for this day based on weekly total so far
        # For daily display, we need to show how much of each day is regular vs overtime
        # But overtime is calculated on weekly basis
        daily_summaries.append(
            SingleWeekDailySummary(
                date=current_date.isoformat(),
                day_name=current_date.strftime("%A"),
                total_hours=round(day_total_hours, 2),
                regular_hours=0, # Will be calculated after we have weekly totals
                overtime_hours=0, # Will be calculated after we have weekly totals
                estimated_earnings=0 # Will be calculated after we have weekly totals
            )
        )
    
    # Use the same overtime calculation logic as admin analytics
    if week_total_hours <= overtime_threshold_hours:
        week_total_regular_hours = week_total_hours
        week_total_overtime_hours = 0.0
    else:
        week_total_regular_hours = overtime_threshold_hours
        week_total_overtime_hours = week_total_hours - overtime_threshold_hours
    
    # Calculate daily regular/overtime hours properly
    # For weekly overtime, we need to determine which hours count as overtime
    # Standard approach: first 40 hours are regular, rest are overtime
    remaining_regular_hours = week_total_regular_hours
    total_earnings = 0.0

    for ds in daily_summaries:
        if remaining_regular_hours >= ds.total_hours:
            # All hours for this day are regular
            ds.regular_hours = round(ds.total_hours, 2)
            ds.overtime_hours = 0.0
            remaining_regular_hours -= ds.total_hours
        elif remaining_regular_hours > 0:
            # Some hours are regular, some are overtime
            ds.regular_hours = round(remaining_regular_hours, 2)
            ds.overtime_hours = round(ds.total_hours - remaining_regular_hours, 2)
            remaining_regular_hours = 0.0
        else:
            # All hours for this day are overtime
            ds.regular_hours = 0.0
            ds.overtime_hours = round(ds.total_hours, 2)
        
        # Calculate earnings using same logic as admin analytics
        ds.estimated_earnings = round((ds.regular_hours * hourly_wage) + (ds.overtime_hours * overtime_wage), 2)
        total_earnings += ds.estimated_earnings

    weekly_total_summary = SingleWeeklyTotal(
        week_start_date=week_start_date.isoformat(),
        week_end_date=week_end_date.isoformat(),
        total_hours=round(week_total_hours, 2),
        total_regular_hours=round(week_total_regular_hours, 2),
        total_overtime_hours=round(week_total_overtime_hours, 2),
        total_estimated_earnings=round(total_earnings, 2)
    )

    return WeeklyBreakdownResponse(
        daily_summaries=daily_summaries,
        weekly_total=weekly_total_summary,
        message="Weekly breakdown retrieved successfully."
    )

@router.get("/work_hours/daily_summary", response_model=DailySummaryResponse)
async def get_daily_summary(
    target_date: date, # Expects YYYY-MM-DD from query
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["uid"]

    # Get user wage info
    user_profile_ref = firestore_db.collection("users").document(user_id)
    user_profile_doc = user_profile_ref.get()
    if not user_profile_doc.exists:
        raise HTTPException(status_code=404, detail="User profile not found for wage information.")
    
    user_data = user_profile_doc.to_dict()
    hourly_wage = user_data.get("hourlyWage")
    # Overtime typically calculated weekly, but fetch if needed for complex daily rules not implemented here yet
    # overtime_multiplier = user_data.get("overtimeMultiplier", 1.5)
    # overtime_threshold_hours = user_data.get("overtimeThresholdHours", 40.0) 

    if hourly_wage is None or not isinstance(hourly_wage, (int, float)) or hourly_wage <= 0:
        # Return 0 hours/earnings if wage isn't set, rather than erroring, for a smoother card display
        return DailySummaryResponse(
            target_date=target_date.isoformat(),
            total_hours_today=0.0,
            total_earnings_today=0.0,
            message="User hourly wage not set or invalid. Cannot calculate earnings."
        )

    # Define the time range for the target_date (full day)
    start_datetime_utc = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime_utc = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc)

    # Fetch punches for the target date
    punches_today = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= start_datetime_utc)
        .where(TimeLog.timestamp <= end_datetime_utc)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    total_seconds_worked_today = 0
    clock_in_time: Optional[datetime] = None

    for punch in punches_today:
        punch_timestamp = punch.timestamp.replace(tzinfo=timezone.utc) if punch.timestamp.tzinfo is None else punch.timestamp
        if punch.punch_type == PunchType.CLOCK_IN:
            # Use same logic as current_week_overtime - always update clock_in_time
            clock_in_time = punch_timestamp
        elif punch.punch_type == PunchType.CLOCK_OUT and clock_in_time:
            # Ensure clock_out is after clock_in for this segment
            if punch_timestamp > clock_in_time:
                duration = (punch_timestamp - clock_in_time).total_seconds()
                total_seconds_worked_today += duration
            clock_in_time = None # Reset for the next pair
    
    # If user is currently clocked in (last punch on target_date was CLOCK_IN and it's the target_date still)
    # For a specific target_date in the past, this part might not be relevant
    # If target_date is today, and they are still clocked in:
    if clock_in_time is not None and target_date == datetime.now(timezone.utc).date():
        now_utc_for_calc = datetime.now(timezone.utc)
        # Ensure current time is after the last clock in, and within the same day
        if now_utc_for_calc > clock_in_time:
            duration_current_shift = (now_utc_for_calc - clock_in_time).total_seconds()
            total_seconds_worked_today += duration_current_shift

    total_hours_today = round(total_seconds_worked_today / 3600, 2)
    # For a single day summary, we'll use the regular hourly wage.
    # More complex daily overtime (e.g., after 8 hours/day) is not implemented here.
    total_earnings_today = round(total_hours_today * hourly_wage, 2)

    return DailySummaryResponse(
        target_date=target_date.isoformat(),
        total_hours_today=total_hours_today,
        total_earnings_today=total_earnings_today,
        message="Daily summary retrieved successfully."
    )

@router.get("/debug/weekly_breakdown_punches")
async def debug_weekly_breakdown_punches(
    week_start_date: date, # Expects YYYY-MM-DD from query
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """Debug endpoint to see exactly what punches are fetched and how they're calculated."""
    user_id = current_user["uid"]
    
    # Calculate week_end_date
    week_end_date = week_start_date + timedelta(days=6)

    # Convert to datetime for DB query (start of day to end of day)
    start_datetime_utc = datetime.combine(week_start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_datetime_utc = datetime.combine(week_end_date, datetime.max.time(), tzinfo=timezone.utc)

    # Fetch punches for the specified week - SAME QUERY AS WEEKLY_BREAKDOWN
    punches = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == user_id)
        .where(TimeLog.timestamp >= start_datetime_utc)
        .where(TimeLog.timestamp <= end_datetime_utc)
        .order_by(TimeLog.timestamp.asc())
    ).all()

    # Format punches for display
    punch_data = []
    for punch in punches:
        punch_data.append({
            "id": punch.id,
            "timestamp": punch.timestamp.isoformat() + "Z" if punch.timestamp.tzinfo else punch.timestamp.isoformat(),
            "punch_type": punch.punch_type.value,
            "dealership_id": punch.dealership_id,
            "date": punch.timestamp.astimezone(timezone.utc).date().isoformat()
        })

    # Calculate total hours using SAME LOGIC as weekly_breakdown
    daily_hours_map = { (week_start_date + timedelta(days=i)): {"total": 0.0, "punches": []} for i in range(7) }

    for punch in punches:
        punch_date = punch.timestamp.astimezone(timezone.utc).date()
        if punch_date in daily_hours_map:
            daily_hours_map[punch_date]["punches"].append(punch)

    daily_calculations = []
    week_total_hours = 0.0

    # Calculate hours per day using same logic as weekly_breakdown
    for day_offset in range(7):
        current_date = week_start_date + timedelta(days=day_offset)
        day_data = daily_hours_map.get(current_date)
        day_total_hours = 0.0
        day_punch_details = []

        if day_data:
            day_punches = sorted(day_data["punches"], key=lambda p: p.timestamp)
            clock_in_time = None
            
            for punch in day_punches:
                punch_ts = punch.timestamp
                if punch_ts.tzinfo is None:
                    punch_ts = punch_ts.replace(tzinfo=timezone.utc)
                    
                if punch.punch_type == PunchType.CLOCK_IN:
                    clock_in_time = punch_ts
                    day_punch_details.append({
                        "action": "clock_in",
                        "timestamp": punch_ts.isoformat(),
                        "punch_id": punch.id
                    })
                elif punch.punch_type == PunchType.CLOCK_OUT and clock_in_time:
                    duration_hours = (punch_ts - clock_in_time).total_seconds() / 3600
                    day_total_hours += duration_hours
                    day_punch_details.append({
                        "action": "clock_out",
                        "timestamp": punch_ts.isoformat(),
                        "punch_id": punch.id,
                        "paired_with_clock_in": clock_in_time.isoformat(),
                        "duration_hours": duration_hours
                    })
                    clock_in_time = None

            # Handle currently active shift if it exists at end of day's punches
            if clock_in_time is not None:
                now_utc = datetime.now(timezone.utc)
                if current_date == now_utc.date():
                    duration_hours = (now_utc - clock_in_time).total_seconds() / 3600
                    day_total_hours += duration_hours
                    day_punch_details.append({
                        "action": "active_shift",
                        "clock_in_time": clock_in_time.isoformat(),
                        "duration_until_now": duration_hours
                    })

        week_total_hours += day_total_hours
        
        daily_calculations.append({
            "date": current_date.isoformat(),
            "day_name": current_date.strftime("%A"),
            "total_hours": round(day_total_hours, 2),
            "punch_details": day_punch_details
        })

    return {
        "week_start_date": week_start_date.isoformat(),
        "week_end_date": week_end_date.isoformat(),
        "query_start": start_datetime_utc.isoformat(),
        "query_end": end_datetime_utc.isoformat(),
        "total_punches_found": len(punches),
        "total_week_hours": round(week_total_hours, 2),
        "punches": punch_data,
        "daily_calculations": daily_calculations
    }

@router.get("/vacation", response_model=UserVacationSummaryResponse)
async def get_user_vacation_time(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """Get user's vacation time entries with optional date filtering"""
    user_id = current_user["uid"]
    
    # Build query
    query = select(VacationTime).where(VacationTime.employee_id == user_id)
    
    # Apply date filters if provided
    if start_date:
        query = query.where(VacationTime.date >= start_date)
    
    if end_date:
        query = query.where(VacationTime.date <= end_date)
    
    # Execute query
    vacation_entries = session.exec(
        query.order_by(VacationTime.date.desc())
    ).all()
    
    # Get user's hourly wage from Firebase
    user_profile_ref = firestore_db.collection("users").document(user_id)
    user_profile_doc = user_profile_ref.get()
    hourly_wage = 0.0
    
    if user_profile_doc.exists:
        user_data = user_profile_doc.to_dict()
        hourly_wage = user_data.get("hourlyWage", 0.0)
        hourly_wage = float(hourly_wage) if hourly_wage else 0.0
    
    # Calculate totals and format entries
    total_hours = 0.0
    total_pay = 0.0
    formatted_entries = []
    
    for entry in vacation_entries:
        vacation_pay = entry.hours * hourly_wage
        total_hours += entry.hours
        total_pay += vacation_pay
        
        formatted_entries.append(VacationTimeEntry(
            id=entry.id,
            date=entry.date,
            hours=entry.hours,
            vacation_type=entry.vacation_type.value,
            notes=entry.notes,
            created_at=entry.created_at,
            hourly_wage=hourly_wage,
            vacation_pay=round(vacation_pay, 2)
        ))
    
    return UserVacationSummaryResponse(
        total_vacation_hours=total_hours,
        total_vacation_pay=round(total_pay, 2),
        vacation_entries=formatted_entries,
        message=f"Found {len(formatted_entries)} vacation entries."
    )

@router.get("/user/upcoming-shifts", response_model=List[UpcomingShiftResponse])
async def get_upcoming_shifts(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all future scheduled shifts for the logged-in employee.
    """
    user_id = current_user["uid"]
    today = date.today()

    try:
        # Query for shifts that are on or after today and are not cancelled
        upcoming_shifts_stmt = (
            select(EmployeeScheduledShift)
            .where(EmployeeScheduledShift.employee_id == user_id)
            .where(EmployeeScheduledShift.shift_date >= today)
            .where(EmployeeScheduledShift.status.in_([ShiftStatus.SCHEDULED, ShiftStatus.CONFIRMED]))
            .order_by(EmployeeScheduledShift.shift_date.asc(), EmployeeScheduledShift.start_time.asc())
        )
        
        shift_records = session.exec(upcoming_shifts_stmt).all()
        
        # Format the response
        response = [
            UpcomingShiftResponse(
                dealership_name=shift.dealership_name,
                shift_date=shift.shift_date,
                start_time=shift.start_time,
                end_time=shift.end_time,
                status=shift.status,
                notes=shift.notes,
            )
            for shift in shift_records
        ]
        
        return response
        
    except Exception as e:
        print(f"Error fetching upcoming shifts for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve upcoming shifts.",
        )