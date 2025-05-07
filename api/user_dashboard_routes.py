from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from db.session import get_session #
from core.deps import get_current_user #
from core.firebase import db as firestore_db #
from models.time_log import TimeLog, PunchType #

router = APIRouter()

# --- Pydantic Models for Responses ---

class CurrentShiftDurationResponse(BaseModel):
    shift_duration_seconds: Optional[float] = None
    shift_start_time: Optional[datetime] = None
    message: str

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

class PunchLogResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    dealership_id: str
    timestamp: datetime
    punch_type: PunchType
    latitude: Optional[float] = None
    longitude: Optional[float] = None

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

class UserOvertimeWageResponse(BaseModel):
    regular_hourly_wage: Optional[float] = None
    overtime_hourly_wage: Optional[float] = None
    message: str

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

    # Return All Punches Exists
    return PastPunchesResponse(
        punches=response_punches,
        message="Punch history for the past three weeks retrieved."
    )