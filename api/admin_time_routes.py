from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from core.deps import require_admin_role
from core.firebase import db as firestore_db
from db.session import get_session
from models.admin_time_change import AdminTimeChange, AdminTimeChangeAction
from models.time_log import PunchType, TimeLog
from utils.datetime_helpers import format_utc_datetime

router = APIRouter()

# --- Pydantic Models for Admin Direct Clock Actions ---


class AdminClockCreateRequestPayload(BaseModel):
    employee_id: str
    day_of_punch: date
    new_start_time: str  # HH:MM format
    new_end_time: str  # HH:MM format
    dealership_id: str
    reason: str


class AdminClockEditRequestPayload(BaseModel):
    employee_id: str
    original_clock_in_timelog_id: int
    original_clock_out_timelog_id: int
    day_of_punch: date
    new_start_time: str  # HH:MM format
    new_end_time: str  # HH:MM format
    dealership_id: str
    reason: str


class AdminClockDeleteRequestPayload(BaseModel):
    employee_id: str
    clock_in_timelog_id: int
    clock_out_timelog_id: int
    reason: str


# --- NEW: Single Clock Edit Payload ---
class AdminSingleClockEditRequestPayload(BaseModel):
    employee_id: str
    timelog_id: int  # ID of the clock punch (either clock-in or clock-out)
    day_of_punch: date  # Date of the punch
    new_time: str  # HH:MM format (Eastern)
    dealership_id: str  # Dealership ID for the punch (can stay the same or change)
    reason: str


# --- NEW: Single Clock Create Payload ---
class AdminSingleClockCreateRequestPayload(BaseModel):
    employee_id: str
    day_of_punch: date  # Date of the punch
    time: str  # HH:MM format (Eastern)
    punch_type: PunchType  # Either PunchType.CLOCK_IN or PunchType.CLOCK_OUT
    dealership_id: str
    reason: str


# --- NEW: Single Clock Delete Payload ---
class AdminSingleClockDeleteRequestPayload(BaseModel):
    employee_id: str
    timelog_id: int  # ID of the clock punch to delete
    reason: str


# --- NEW: Change Punch Dealership Payload ---
class AdminChangePunchDealershipRequestPayload(BaseModel):
    employee_id: str
    timelog_id: int
    new_dealership_id: str
    reason: str


# --- Helper function to combine date and time string ---
def combine_date_time_str(punch_date: date, time_str: str) -> datetime:
    """
    Combine date and time string (in EST/EDT) and convert to UTC for database storage.
    """
    try:
        parsed_time = time.fromisoformat(time_str)  # Expects HH:MM or HH:MM:SS

        # Create datetime object in Eastern timezone (handles EST/EDT).
        # Use canonical name; fall back to legacy alias if necessary.
        try:
            eastern = ZoneInfo("America/New_York")
        except ZoneInfoNotFoundError:
            eastern = ZoneInfo("US/Eastern")
        # Build aware datetime directly with Eastern tzinfo
        dt_eastern = datetime.combine(punch_date, parsed_time, tzinfo=eastern)

        # Convert to UTC for database storage
        dt_utc = dt_eastern.astimezone(timezone.utc)

        return dt_utc

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid time string format: {time_str}. Expected HH:MM or HH:MM:SS.",
        )


# --- Validation Functions ---


def validate_employee_permissions(admin: dict, employee_id: str) -> None:
    """
    Validate that the admin has permission to modify the specified employee's records.
    For now, this is a placeholder - you may want to add dealership-level checks.
    """
    # TODO: Add dealership-level permission checks if needed
    # For now, all admins can modify any employee's records
    pass


def validate_time_entry_data(
    new_start_time: str, new_end_time: str, day_of_punch: date
) -> tuple[datetime, datetime]:
    """
    Validate and convert time entry data to datetime objects.
    """
    # Parse times
    new_start_datetime = combine_date_time_str(day_of_punch, new_start_time)
    new_end_datetime = combine_date_time_str(day_of_punch, new_end_time)

    # Validate logical order
    if new_end_datetime <= new_start_datetime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time.",
        )

    # Validate reasonable date bounds (not too far in future/past)
    now = datetime.now(timezone.utc)
    max_past_days = 365  # 1 year
    max_future_days = 7  # 1 week

    if (now.date() - day_of_punch).days > max_past_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create/edit entries more than {max_past_days} days in the past.",
        )

    if (day_of_punch - now.date()).days > max_future_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create/edit entries more than {max_future_days} days in the future.",
        )

    return new_start_datetime, new_end_datetime


# --- Admin Endpoints ---


@router.post("/direct-clock-creation")
def admin_direct_clock_creation(
    payload: AdminClockCreateRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin direct clock creation - creates a new clock-in/out pair immediately without approval process.
    This bypasses the ClockRequestLog entirely and directly creates TimeLog entries.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, payload.employee_id)

    # Validate and parse time data
    new_start_datetime, new_end_datetime = validate_time_entry_data(
        payload.new_start_time, payload.new_end_time, payload.day_of_punch
    )

    admin_uid = admin.get("uid", "unknown_admin")

    try:
        # Create new CLOCK_IN entry
        new_clock_in = TimeLog(
            employee_id=payload.employee_id,
            dealership_id=payload.dealership_id,
            punch_type=PunchType.CLOCK_IN,
            timestamp=new_start_datetime,
            admin_notes=payload.reason,
            admin_modifier_id=admin_uid,
            # latitude/longitude are not part of admin requests
        )
        session.add(new_clock_in)
        session.flush()  # Get the ID without committing yet

        # Create new CLOCK_OUT entry
        new_clock_out = TimeLog(
            employee_id=payload.employee_id,
            dealership_id=payload.dealership_id,
            punch_type=PunchType.CLOCK_OUT,
            timestamp=new_end_datetime,
            admin_notes=payload.reason,
            admin_modifier_id=admin_uid,
        )
        session.add(new_clock_out)
        session.flush()  # Get the ID without committing yet

        session.commit()
        session.refresh(new_clock_in)
        session.refresh(new_clock_out)

        # Log the admin action
        admin_change = AdminTimeChange(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.CREATE,
            reason=payload.reason,
            clock_in_id=new_clock_in.id,
            clock_out_id=new_clock_out.id,
            dealership_id=payload.dealership_id,
            start_time=new_start_datetime,
            end_time=new_end_datetime,
            punch_date=payload.day_of_punch.isoformat(),
        )
        session.add(admin_change)
        session.commit()

        return {
            "success": True,
            "message": "Clock entry created successfully",
            "clock_in_id": new_clock_in.id,
            "clock_out_id": new_clock_out.id,
            "employee_id": payload.employee_id,
            "start_time": format_utc_datetime(new_start_datetime),
            "end_time": format_utc_datetime(new_end_datetime),
            "reason": payload.reason,
            "created_by_admin": admin_uid,
        }

    except Exception as e:
        session.rollback()
        print(f"Error during admin clock creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while creating clock entry: {str(e)}",
        )


@router.post("/direct-clock-edit")
def admin_direct_clock_edit(
    payload: AdminClockEditRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin direct clock edit - edits existing clock-in/out pair immediately without approval process.
    This bypasses the ClockRequestLog entirely and directly modifies TimeLog entries.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, payload.employee_id)

    # Validate and parse time data
    new_start_datetime, new_end_datetime = validate_time_entry_data(
        payload.new_start_time, payload.new_end_time, payload.day_of_punch
    )

    admin_uid = admin.get("uid", "unknown_admin")

    try:
        # Validate original clock-in punch
        original_clock_in = session.get(TimeLog, payload.original_clock_in_timelog_id)
        if not original_clock_in:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original clock-in punch with ID {payload.original_clock_in_timelog_id} not found.",
            )
        if original_clock_in.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Clock-in punch ID {payload.original_clock_in_timelog_id} does not belong to employee {payload.employee_id}.",
            )
        if original_clock_in.punch_type != PunchType.CLOCK_IN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Punch ID {payload.original_clock_in_timelog_id} is not a clock-in punch.",
            )

        # Validate original clock-out punch
        original_clock_out = session.get(TimeLog, payload.original_clock_out_timelog_id)
        if not original_clock_out:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original clock-out punch with ID {payload.original_clock_out_timelog_id} not found.",
            )
        if original_clock_out.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Clock-out punch ID {payload.original_clock_out_timelog_id} does not belong to employee {payload.employee_id}.",
            )
        if original_clock_out.punch_type != PunchType.CLOCK_OUT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Punch ID {payload.original_clock_out_timelog_id} is not a clock-out punch.",
            )

        # Store original values for response
        original_start_time = original_clock_in.timestamp
        original_end_time = original_clock_out.timestamp

        # Update the punch records
        original_clock_in.timestamp = new_start_datetime
        original_clock_in.dealership_id = payload.dealership_id
        original_clock_in.admin_notes = payload.reason
        original_clock_in.admin_modifier_id = admin_uid
        session.add(original_clock_in)

        original_clock_out.timestamp = new_end_datetime
        original_clock_out.dealership_id = payload.dealership_id
        original_clock_out.admin_notes = payload.reason
        original_clock_out.admin_modifier_id = admin_uid
        session.add(original_clock_out)

        session.commit()
        session.refresh(original_clock_in)
        session.refresh(original_clock_out)

        # Log the admin action
        admin_change = AdminTimeChange(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.EDIT,
            reason=payload.reason,
            clock_in_id=original_clock_in.id,
            clock_out_id=original_clock_out.id,
            dealership_id=payload.dealership_id,
            start_time=new_start_datetime,
            end_time=new_end_datetime,
            original_start_time=original_start_time,
            original_end_time=original_end_time,
            punch_date=payload.day_of_punch.isoformat(),
        )
        session.add(admin_change)
        session.commit()

        return {
            "success": True,
            "message": "Clock entry edited successfully",
            "clock_in_id": original_clock_in.id,
            "clock_out_id": original_clock_out.id,
            "employee_id": payload.employee_id,
            "original_start_time": format_utc_datetime(original_start_time),
            "original_end_time": format_utc_datetime(original_end_time),
            "new_start_time": format_utc_datetime(new_start_datetime),
            "new_end_time": format_utc_datetime(new_end_datetime),
            "reason": payload.reason,
            "edited_by_admin": admin_uid,
        }

    except HTTPException as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        print(f"Error during admin clock edit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while editing clock entry: {str(e)}",
        )


@router.post("/direct-single-clock-edit")
def admin_direct_single_clock_edit(
    payload: AdminSingleClockEditRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin endpoint to edit a **single** existing clock punch (either CLOCK_IN or CLOCK_OUT).

    Example use-cases:
    • Change an 8:23 AM CLOCK_IN to 8:45 AM.
    • Change a 9:00 PM CLOCK_OUT to 8:15 PM.
    """
    # Validate admin permissions
    validate_employee_permissions(admin, payload.employee_id)

    # Parse new timestamp
    new_timestamp = combine_date_time_str(payload.day_of_punch, payload.new_time)

    admin_uid = admin.get("uid", "unknown_admin")

    # Fetch the punch to edit
    punch = session.get(TimeLog, payload.timelog_id)
    if not punch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TimeLog ID {payload.timelog_id} not found",
        )

    if punch.employee_id != payload.employee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TimeLog does not belong to specified employee",
        )

    # Store originals for response/logging
    original_timestamp = punch.timestamp
    original_dealership = punch.dealership_id

    try:
        # Update punch
        punch.timestamp = new_timestamp
        punch.dealership_id = payload.dealership_id
        punch.admin_notes = payload.reason
        punch.admin_modifier_id = admin_uid
        session.add(punch)
        session.commit()
        session.refresh(punch)

        # Log admin change
        change_kwargs = dict(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.EDIT,
            reason=payload.reason,
            dealership_id=payload.dealership_id,
            punch_date=payload.day_of_punch.isoformat(),
        )

        if punch.punch_type == PunchType.CLOCK_IN:
            change_kwargs.update(
                clock_in_id=punch.id,
                start_time=new_timestamp,
                original_start_time=original_timestamp,
            )
        else:
            change_kwargs.update(
                clock_out_id=punch.id,
                end_time=new_timestamp,
                original_end_time=original_timestamp,
            )

        admin_change = AdminTimeChange(**change_kwargs)
        session.add(admin_change)
        session.commit()

        return {
            "success": True,
            "message": "Punch updated successfully",
            "timelog_id": punch.id,
            "employee_id": payload.employee_id,
            "punch_type": punch.punch_type,
            "original_timestamp": format_utc_datetime(original_timestamp),
            "new_timestamp": format_utc_datetime(new_timestamp),
            "original_dealership": original_dealership,
            "new_dealership": payload.dealership_id,
            "reason": payload.reason,
            "edited_by_admin": admin_uid,
        }

    except HTTPException as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        print(f"Error during single clock edit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while editing punch",
        )


@router.post("/direct-single-clock-creation")
def admin_direct_single_clock_creation(
    payload: AdminSingleClockCreateRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin endpoint to create a **single** clock punch (either CLOCK_IN or CLOCK_OUT).

    The admin must specify the punch_type so the system knows whether this is a clock-in or clock-out.
    """
    # Validate admin permissions
    validate_employee_permissions(admin, payload.employee_id)

    # Parse timestamp
    new_timestamp = combine_date_time_str(payload.day_of_punch, payload.time)

    admin_uid = admin.get("uid", "unknown_admin")

    # Check for existing punch at the same timestamp with same type and dealership
    existing_punch = session.exec(
        select(TimeLog)
        .where(TimeLog.employee_id == payload.employee_id)
        .where(TimeLog.timestamp == new_timestamp)
        .where(TimeLog.punch_type == payload.punch_type)
        .where(TimeLog.dealership_id == payload.dealership_id)
    ).first()

    if existing_punch:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {payload.punch_type.value} punch already exists for {payload.employee_id} at {format_utc_datetime(new_timestamp)} at {payload.dealership_id}",
        )

    try:
        # Create the punch
        new_punch = TimeLog(
            employee_id=payload.employee_id,
            dealership_id=payload.dealership_id,
            punch_type=payload.punch_type,
            timestamp=new_timestamp,
            admin_notes=payload.reason,
            admin_modifier_id=admin_uid,
        )
        session.add(new_punch)
        session.commit()
        session.refresh(new_punch)

        # Log admin action
        change_kwargs = dict(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.CREATE,
            reason=payload.reason,
            dealership_id=payload.dealership_id,
            punch_date=payload.day_of_punch.isoformat(),
        )
        if payload.punch_type == PunchType.CLOCK_IN:
            change_kwargs.update(clock_in_id=new_punch.id, start_time=new_timestamp)
        else:
            change_kwargs.update(clock_out_id=new_punch.id, end_time=new_timestamp)

        admin_change = AdminTimeChange(**change_kwargs)
        session.add(admin_change)
        session.commit()

        return {
            "success": True,
            "message": "Punch created successfully",
            "timelog_id": new_punch.id,
            "employee_id": payload.employee_id,
            "punch_type": payload.punch_type,
            "timestamp": format_utc_datetime(new_timestamp),
            "dealership_id": payload.dealership_id,
            "reason": payload.reason,
            "created_by_admin": admin_uid,
        }

    except Exception as e:
        session.rollback()
        print(f"Error during single clock creation: {e}")
        print(f"Error type: {type(e)}")
        import traceback

        print(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error while creating punch: {str(e)}",
        )


@router.post("/direct-single-clock-delete")
def admin_direct_single_clock_delete(
    payload: AdminSingleClockDeleteRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin endpoint to delete a **single** clock punch (either CLOCK_IN or CLOCK_OUT).
    """
    import logging
    import traceback

    logger = logging.getLogger(__name__)

    try:
        logger.info(
            f"Starting single clock delete - Admin: {admin.get('uid', 'unknown')}, Employee: {payload.employee_id}, TimeLog: {payload.timelog_id}"
        )
        logger.info(f"Payload: {payload.model_dump()}")

        # Validate admin permissions
        logger.info("Validating admin permissions...")
        validate_employee_permissions(admin, payload.employee_id)
        logger.info("Admin permissions validated successfully")

        admin_uid = admin.get("uid", "unknown_admin")

        # Fetch the punch
        logger.info(f"Fetching TimeLog ID {payload.timelog_id}...")
        punch = session.get(TimeLog, payload.timelog_id)
        if not punch:
            logger.warning(f"TimeLog ID {payload.timelog_id} not found in database")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"TimeLog ID {payload.timelog_id} not found",
            )

        logger.info(
            f"Found punch: ID={punch.id}, Employee={punch.employee_id}, Type={punch.punch_type}, Timestamp={punch.timestamp}, Dealership={punch.dealership_id}"
        )

        if punch.employee_id != payload.employee_id:
            logger.warning(
                f"TimeLog belongs to employee {punch.employee_id}, but requested for employee {payload.employee_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TimeLog does not belong to specified employee",
            )

        punch_type = punch.punch_type
        punch_timestamp = punch.timestamp
        dealership_id = punch.dealership_id
        punch_date = punch.timestamp.date().isoformat()

        logger.info(
            f"Punch details extracted - Type: {punch_type}, Timestamp: {punch_timestamp}, Dealership: {dealership_id}, Date: {punch_date}"
        )

        # Check for linked signature photos and handle them
        logger.info("Checking for linked signature photos...")
        from models.signature_photo import SignaturePhoto

        linked_signatures = session.exec(
            select(SignaturePhoto).where(SignaturePhoto.time_log_id == punch.id)
        ).all()

        if linked_signatures:
            logger.info(
                f"Found {len(linked_signatures)} signature photos linked to this TimeLog"
            )
            logger.info(f"Signature photo IDs: {[sig.id for sig in linked_signatures]}")

            # Unlink signature photos (set time_log_id to NULL) to preserve them for records
            for signature in linked_signatures:
                logger.info(
                    f"Unlinking signature photo ID {signature.id} from TimeLog {punch.id}"
                )
                signature.time_log_id = None
                session.add(signature)
            logger.info("All signature photos unlinked successfully")
        else:
            logger.info("No signature photos found linked to this TimeLog")

        # Log admin action BEFORE deletion
        logger.info("Creating AdminTimeChange record...")
        change_kwargs = dict(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.DELETE,
            reason=payload.reason,
            dealership_id=dealership_id,
            punch_date=punch_date,
        )
        if punch_type == PunchType.CLOCK_IN:
            change_kwargs.update(clock_in_id=punch.id, start_time=punch_timestamp)
        else:
            change_kwargs.update(clock_out_id=punch.id, end_time=punch_timestamp)

        logger.info(f"AdminTimeChange kwargs: {change_kwargs}")

        admin_change = AdminTimeChange(**change_kwargs)
        logger.info("AdminTimeChange object created successfully")

        session.add(admin_change)
        logger.info("AdminTimeChange added to session")

        # Delete the punch
        logger.info(f"Deleting TimeLog ID {punch.id}...")
        session.delete(punch)
        logger.info("TimeLog marked for deletion")

        logger.info("Committing transaction...")
        session.commit()
        logger.info("Transaction committed successfully")

        result = {
            "success": True,
            "message": "Punch deleted successfully",
            "deleted_timelog_id": payload.timelog_id,
            "employee_id": payload.employee_id,
            "punch_type": punch_type,
            "timestamp": format_utc_datetime(punch_timestamp),
            "dealership_id": dealership_id,
            "reason": payload.reason,
            "deleted_by_admin": admin_uid,
        }

        logger.info(f"Delete operation completed successfully: {result}")
        return result

    except HTTPException as e:
        logger.error(
            f"HTTPException in single clock delete: {e.status_code} - {e.detail}"
        )
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error during single clock delete: {e}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        logger.error(f"Payload that caused error: {payload.model_dump()}")
        logger.error(f"Admin info: {admin}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error while deleting punch: {str(e)}",
        )


@router.post("/direct-change-punch-dealership")
def admin_direct_change_punch_dealership(
    payload: AdminChangePunchDealershipRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin endpoint to change the dealership for a single existing clock punch.
    """
    # Validate admin permissions
    validate_employee_permissions(admin, payload.employee_id)

    admin_uid = admin.get("uid", "unknown_admin")

    # Fetch the punch
    punch = session.get(TimeLog, payload.timelog_id)
    if not punch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"TimeLog ID {payload.timelog_id} not found",
        )

    if punch.employee_id != payload.employee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TimeLog does not belong to specified employee",
        )

    original_dealership_id = punch.dealership_id

    # Avoid unnecessary updates
    if original_dealership_id == payload.new_dealership_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New dealership is the same as the current one.",
        )

    try:
        # Update the punch
        punch.dealership_id = payload.new_dealership_id
        punch.admin_notes = payload.reason
        punch.admin_modifier_id = admin_uid
        session.add(punch)

        # Log the admin action
        change_kwargs = dict(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.EDIT,
            reason=payload.reason,
            dealership_id=payload.new_dealership_id,
            original_dealership_id=original_dealership_id,
            punch_date=punch.timestamp.date().isoformat(),
        )
        if punch.punch_type == PunchType.CLOCK_IN:
            change_kwargs.update(clock_in_id=punch.id, start_time=punch.timestamp)
        else:
            change_kwargs.update(clock_out_id=punch.id, end_time=punch.timestamp)

        admin_change = AdminTimeChange(**change_kwargs)
        session.add(admin_change)

        session.commit()
        session.refresh(punch)

        return {
            "success": True,
            "message": "Punch dealership updated successfully",
            "timelog_id": punch.id,
            "employee_id": punch.employee_id,
            "original_dealership_id": original_dealership_id,
            "new_dealership_id": punch.dealership_id,
            "reason": payload.reason,
            "edited_by_admin": admin_uid,
        }

    except HTTPException as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        print(f"Error during punch dealership change: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while changing punch dealership",
        )


# --- Helper endpoint for frontend to get employee's recent punches ---


@router.get("/employee/{employee_id}/recent-punches")
def get_employee_recent_punches(
    employee_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: Optional[int] = 20,  # Changed to Optional, default 20
):
    """
    Get punch entries for a specific employee.
    If limit is 0 or None, all entries are returned.
    Otherwise, returns the specified number of recent entries.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, employee_id)

    # Base query
    query = (
        select(TimeLog)
        .where(TimeLog.employee_id == employee_id)
        .order_by(TimeLog.timestamp.desc())
    )

    # Apply limit if provided and greater than 0
    if limit and limit > 0:
        query = query.limit(limit)

    recent_punches = session.exec(query).all()

    # Format for frontend
    formatted_punches = []
    for punch in recent_punches:
        formatted_punches.append(
            {
                "id": punch.id,
                "timestamp": format_utc_datetime(punch.timestamp),
                "punch_type": punch.punch_type.value,
                "dealership_id": punch.dealership_id,
                "date": punch.timestamp.date().isoformat(),
                "time": punch.timestamp.time().strftime("%H:%M"),
            }
        )

    return {"employee_id": employee_id, "recent_punches": formatted_punches}


async def get_user_name(user_id: str) -> Optional[str]:
    """Get user's display name from Firestore"""
    try:
        user_ref = firestore_db.collection("users").document(user_id)
        user_doc = user_ref.get()
        if user_doc.exists:
            return user_doc.to_dict().get("displayName", "Unknown")
    except Exception as e:
        print(f"Error fetching user name for {user_id}: {e}")
    return None


@router.get("/recent-entries")
async def get_recent_global_entries(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: int = 50,  # Default to 50 most recent entries
):
    """
    Get the most recent admin time changes across all employees.
    """
    query = select(AdminTimeChange).order_by(AdminTimeChange.created_at.desc())

    if limit and limit > 0:
        query = query.limit(limit)

    recent_changes = session.exec(query).all()

    # Format for frontend
    formatted_changes = []
    for change in recent_changes:
        employee_name = await get_user_name(change.employee_id)
        admin_name = await get_user_name(change.admin_id)

        formatted_changes.append(
            {
                "id": change.id,
                "employee_id": change.employee_id,
                "employee_name": employee_name,
                "admin_id": change.admin_id,
                "admin_name": admin_name,
                "action": change.action.value,
                "reason": change.reason,
                "created_at": format_utc_datetime(change.created_at),
                "clock_in_id": change.clock_in_id,
                "clock_out_id": change.clock_out_id,
                "dealership_id": change.dealership_id,
                "start_time": format_utc_datetime(change.start_time),
                "end_time": format_utc_datetime(change.end_time),
                "original_start_time": format_utc_datetime(change.original_start_time),
                "original_end_time": format_utc_datetime(change.original_end_time),
                "punch_date": change.punch_date,
                "date": change.created_at.date().isoformat(),
                "time": change.created_at.time().strftime("%H:%M"),
            }
        )

    return {"recent_changes": formatted_changes}


@router.get("/employee/{employee_id}/changes")
async def get_employee_admin_changes(
    employee_id: str,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
    limit: Optional[int] = 20,
):
    """
    Get all admin time changes for a specific employee.
    If limit is 0 or None, all changes are returned.
    Otherwise, returns the specified number of recent changes.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, employee_id)

    # Base query
    query = (
        select(AdminTimeChange)
        .where(AdminTimeChange.employee_id == employee_id)
        .order_by(AdminTimeChange.created_at.desc())
    )

    # Apply limit if provided and greater than 0
    if limit and limit > 0:
        query = query.limit(limit)

    employee_changes = session.exec(query).all()

    # Format for frontend
    formatted_changes = []
    for change in employee_changes:
        employee_name = await get_user_name(change.employee_id)
        admin_name = await get_user_name(change.admin_id)

        formatted_changes.append(
            {
                "id": change.id,
                "employee_id": change.employee_id,
                "employee_name": employee_name,
                "admin_id": change.admin_id,
                "admin_name": admin_name,
                "action": change.action.value,
                "reason": change.reason,
                "created_at": format_utc_datetime(change.created_at),
                "clock_in_id": change.clock_in_id,
                "clock_out_id": change.clock_out_id,
                "dealership_id": change.dealership_id,
                "start_time": format_utc_datetime(change.start_time),
                "end_time": format_utc_datetime(change.end_time),
                "original_start_time": format_utc_datetime(change.original_start_time),
                "original_end_time": format_utc_datetime(change.original_end_time),
                "punch_date": change.punch_date,
                "date": change.created_at.date().isoformat(),
                "time": change.created_at.time().strftime("%H:%M"),
            }
        )

    return {"employee_id": employee_id, "admin_changes": formatted_changes}


@router.post("/direct-clock-delete")
def admin_direct_clock_delete(
    payload: AdminClockDeleteRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin direct clock delete - deletes an existing clock-in/out pair immediately.
    This directly removes TimeLog entries from the database.
    """
    # Validate admin permissions for this employee
    validate_employee_permissions(admin, payload.employee_id)

    admin_uid = admin.get("uid", "unknown_admin")

    try:
        # Validate clock-in punch
        clock_in = session.get(TimeLog, payload.clock_in_timelog_id)
        if not clock_in:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clock-in punch with ID {payload.clock_in_timelog_id} not found.",
            )
        if clock_in.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Clock-in punch ID {payload.clock_in_timelog_id} does not belong to employee {payload.employee_id}.",
            )
        if clock_in.punch_type != PunchType.CLOCK_IN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Punch ID {payload.clock_in_timelog_id} is not a clock-in punch.",
            )

        # Validate clock-out punch
        clock_out = session.get(TimeLog, payload.clock_out_timelog_id)
        if not clock_out:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Clock-out punch with ID {payload.clock_out_timelog_id} not found.",
            )
        if clock_out.employee_id != payload.employee_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Clock-out punch ID {payload.clock_out_timelog_id} does not belong to employee {payload.employee_id}.",
            )
        if clock_out.punch_type != PunchType.CLOCK_OUT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Punch ID {payload.clock_out_timelog_id} is not a clock-out punch.",
            )

        # Store info for response before deletion
        deleted_start_time = clock_in.timestamp
        deleted_end_time = clock_out.timestamp
        dealership_id = clock_in.dealership_id
        punch_date = clock_in.timestamp.date().isoformat()

        # Log the admin action BEFORE deleting
        admin_change = AdminTimeChange(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.DELETE,
            reason=payload.reason,
            clock_in_id=payload.clock_in_timelog_id,
            clock_out_id=payload.clock_out_timelog_id,
            dealership_id=dealership_id,
            start_time=deleted_start_time,
            end_time=deleted_end_time,
            punch_date=punch_date,
        )
        session.add(admin_change)

        # Delete both punch records
        session.delete(clock_in)
        session.delete(clock_out)

        session.commit()

        return {
            "success": True,
            "message": "Clock entry deleted successfully",
            "deleted_clock_in_id": payload.clock_in_timelog_id,
            "deleted_clock_out_id": payload.clock_out_timelog_id,
            "employee_id": payload.employee_id,
            "deleted_start_time": format_utc_datetime(deleted_start_time),
            "deleted_end_time": format_utc_datetime(deleted_end_time),
            "dealership_id": dealership_id,
            "reason": payload.reason,
            "deleted_by_admin": admin_uid,
        }

    except HTTPException as e:
        session.rollback()
        raise e
    except Exception as e:
        session.rollback()
        print(f"Error during admin clock delete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while deleting clock entry: {str(e)}",
        )


# --- Admin Stop Shift Models ---


class AdminStopShiftRequestPayload(BaseModel):
    employee_id: str
    reason: str
    stop_time: Optional[datetime] = None  # Optional: If not provided, defaults to now
    dealership_id: Optional[str] = (
        None  # Optional - if provided, only stop shift at this dealership
    )


class AdminStopShiftResponse(BaseModel):
    success: bool
    message: str
    employee_id: str
    dealership_id: Optional[str] = None
    shift_end_time: Optional[str] = None  # UTC timestamp of when shift was ended
    shift_duration_hours: Optional[float] = None  # How long the shift was
    created_timelog_id: Optional[int] = None  # ID of the created CLOCK_OUT entry
    reason: str
    admin_id: str


# --- Admin Stop Shift Endpoint ---


@router.post("/stop-shift", response_model=AdminStopShiftResponse)
async def admin_stop_employee_shift(
    payload: AdminStopShiftRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """
    Admin endpoint to stop/end a specific employee's current shift.

    This endpoint:
    1. Checks if the employee is currently clocked in
    2. Creates a CLOCK_OUT entry with the timestamp provided, or the current time if not
    3. Logs the admin action for audit trail
    4. Returns details about the stopped shift

    Parameters:
    - employee_id: The ID of the employee whose shift to stop
    - reason: Admin reason for stopping the shift (required for audit trail)
    - stop_time: Optional datetime to set as the clock-out time. Defaults to now.
    - dealership_id: Optional - if provided, only stops shift at this specific dealership

    Returns:
    - Success/failure status
    - Details about the stopped shift
    - Created CLOCK_OUT entry ID for reference
    """
    print(f"\n=== Admin Stop Shift Request ===")
    print(f"Admin: {admin.get('uid', 'Unknown')}")
    print(f"Employee: {payload.employee_id}")
    print(f"Dealership filter: {payload.dealership_id or 'Any'}")
    print(f"Stop time: {payload.stop_time or 'Now'}")
    print(f"Reason: {payload.reason}")

    admin_uid = admin.get("uid")
    if not admin_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin user ID not found"
        )

    # Validate that reason is provided
    if not payload.reason or payload.reason.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reason is required for stopping an employee's shift",
        )

    try:
        # Import here to avoid circular imports
        from api.admin_analytics_routes import is_employee_currently_active

        # Determine the time to use for stopping the shift
        stop_time = payload.stop_time or datetime.now(timezone.utc)

        # Check if employee is currently active
        is_active, most_recent_clock_in_ts = await is_employee_currently_active(
            session, payload.employee_id, payload.dealership_id
        )

        if not is_active or not most_recent_clock_in_ts:
            # Employee is not currently clocked in
            dealership_msg = (
                f" at dealership {payload.dealership_id}"
                if payload.dealership_id
                else ""
            )
            return AdminStopShiftResponse(
                success=False,
                message=f"Employee {payload.employee_id} is not currently clocked in{dealership_msg}",
                employee_id=payload.employee_id,
                dealership_id=payload.dealership_id,
                reason=payload.reason,
                admin_id=admin_uid,
            )

        # Get the dealership ID from the most recent clock-in if not specified
        if not payload.dealership_id:
            # Find the most recent clock-in to get the dealership
            most_recent_clock_in = session.exec(
                select(TimeLog)
                .where(TimeLog.employee_id == payload.employee_id)
                .where(TimeLog.punch_type == PunchType.CLOCK_IN)
                .order_by(TimeLog.timestamp.desc())
                .limit(1)
            ).first()

            if most_recent_clock_in:
                active_dealership_id = most_recent_clock_in.dealership_id
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not determine active dealership for employee",
                )
        else:
            active_dealership_id = payload.dealership_id

        # Calculate shift duration
        shift_duration_seconds = (stop_time - most_recent_clock_in_ts).total_seconds()
        shift_duration_hours = shift_duration_seconds / 3600

        # Create CLOCK_OUT entry
        clock_out_entry = TimeLog(
            employee_id=payload.employee_id,
            dealership_id=active_dealership_id,
            punch_type=PunchType.CLOCK_OUT,
            timestamp=stop_time,
            admin_notes=f"ADMIN STOP SHIFT: {payload.reason}",
            admin_modifier_id=admin_uid,
            # No latitude/longitude for admin actions
        )

        session.add(clock_out_entry)
        session.flush()  # Get the ID without committing yet

        # Log the admin action
        admin_change = AdminTimeChange(
            admin_id=admin_uid,
            employee_id=payload.employee_id,
            action=AdminTimeChangeAction.CREATE,  # We're creating a clock-out entry
            reason=f"Admin stopped shift: {payload.reason}",
            clock_out_id=clock_out_entry.id,
            dealership_id=active_dealership_id,
            end_time=stop_time,
            punch_date=stop_time.date().isoformat(),
        )

        session.add(admin_change)
        session.commit()
        session.refresh(clock_out_entry)

        print(f"✅ Successfully stopped shift for employee {payload.employee_id}")
        print(f"   Dealership: {active_dealership_id}")
        print(f"   Shift duration: {shift_duration_hours:.2f} hours")
        print(f"   CLOCK_OUT ID: {clock_out_entry.id}")

        return AdminStopShiftResponse(
            success=True,
            message=f"Successfully stopped shift for employee {payload.employee_id} at dealership {active_dealership_id}",
            employee_id=payload.employee_id,
            dealership_id=active_dealership_id,
            shift_end_time=format_utc_datetime(stop_time),
            shift_duration_hours=round(shift_duration_hours, 2),
            created_timelog_id=clock_out_entry.id,
            reason=payload.reason,
            admin_id=admin_uid,
        )

    except Exception as e:
        session.rollback()
        print(f"❌ Error during admin stop shift: {e}")
        import traceback

        print(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while stopping employee shift: {str(e)}",
        )


# --- Auto-stop Overlong Shift (15h+) ---


class AutoStopShiftRequestPayload(BaseModel):
    employee_id: str
    threshold_hours: float = 15.0
    dealership_id: Optional[str] = None
    reason: Optional[str] = None


class AutoStopShiftResponse(BaseModel):
    success: bool
    message: str
    employee_id: str
    threshold_hours: float
    is_over_threshold: bool
    was_clock_out_created: bool
    shift_start_time: Optional[str] = None
    shift_end_time: Optional[str] = None
    shift_duration_hours: Optional[float] = None
    dealership_id: Optional[str] = None
    created_timelog_id: Optional[int] = None
    admin_id: str


# @router.post("/auto-stop-overlong-shift", response_model=AutoStopShiftResponse)
# async def auto_stop_overlong_shift(
#     payload: AutoStopShiftRequestPayload,
#     session: Session = Depends(get_session),
#     admin: dict = Depends(require_admin_role),
# ):
#     """
#     If the employee is currently clocked in and their ongoing shift exceeds `threshold_hours`
#     (default 15h), automatically create a CLOCK_OUT entry at the current time.

#     - Optional `dealership_id` limits the check to a specific store when employees work across locations.
#     - Optional `reason` is appended to the auto-stop admin notes.
#     """
#     admin_uid = admin.get("uid")
#     if not admin_uid:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin user ID not found"
#         )

#     try:
#         # Import here to avoid circular imports
#         from api.admin_analytics_routes import is_employee_currently_active

#         now_utc = datetime.now(timezone.utc)

#         # Determine current active status and the most recent CLOCK_IN timestamp
#         is_active, clock_in_ts = await is_employee_currently_active(
#             session=session,
#             employee_id=payload.employee_id,
#             dealership_id=payload.dealership_id,
#         )

#         if not is_active or not clock_in_ts:
#             return AutoStopShiftResponse(
#                 success=True,
#                 message=f"Employee {payload.employee_id} is not currently clocked in",
#                 employee_id=payload.employee_id,
#                 threshold_hours=payload.threshold_hours,
#                 is_over_threshold=False,
#                 was_clock_out_created=False,
#                 shift_start_time=None,
#                 shift_end_time=None,
#                 shift_duration_hours=None,
#                 dealership_id=payload.dealership_id,
#                 created_timelog_id=None,
#                 admin_id=admin_uid,
#             )

#         # Compute current shift duration
#         duration_hours = (now_utc - clock_in_ts).total_seconds() / 3600.0
#         over = duration_hours > payload.threshold_hours

#         if not over:
#             return AutoStopShiftResponse(
#                 success=True,
#                 message=(
#                     f"Shift duration {duration_hours:.2f}h is below threshold {payload.threshold_hours:.2f}h"
#                 ),
#                 employee_id=payload.employee_id,
#                 threshold_hours=payload.threshold_hours,
#                 is_over_threshold=False,
#                 was_clock_out_created=False,
#                 shift_start_time=format_utc_datetime(clock_in_ts),
#                 shift_end_time=format_utc_datetime(now_utc),
#                 shift_duration_hours=round(duration_hours, 2),
#                 dealership_id=payload.dealership_id,
#                 created_timelog_id=None,
#                 admin_id=admin_uid,
#             )

#         # Determine dealership if not provided: use most recent CLOCK_IN's dealership
#         if not payload.dealership_id:
#             most_recent_clock_in = session.exec(
#                 select(TimeLog)
#                 .where(TimeLog.employee_id == payload.employee_id)
#                 .where(TimeLog.punch_type == PunchType.CLOCK_IN)
#                 .order_by(TimeLog.timestamp.desc())
#                 .limit(1)
#             ).first()

#             if not most_recent_clock_in:
#                 raise HTTPException(
#                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                     detail="Could not determine active dealership for employee",
#                 )
#             active_dealership_id = most_recent_clock_in.dealership_id
#         else:
#             active_dealership_id = payload.dealership_id

#         # Create CLOCK_OUT entry at shift_start + threshold_hours (not current time)
#         cutoff_time = clock_in_ts + timedelta(hours=payload.threshold_hours)
#         reason_suffix = f" | {payload.reason}" if payload.reason else ""
#         admin_note = f"AUTO STOP SHIFT: Exceeded threshold {payload.threshold_hours:.2f}h (actual {duration_hours:.2f}h){reason_suffix}"

#         clock_out_entry = TimeLog(
#             employee_id=payload.employee_id,
#             dealership_id=active_dealership_id,
#             punch_type=PunchType.CLOCK_OUT,
#             timestamp=cutoff_time,
#             admin_notes=admin_note,
#             admin_modifier_id=admin_uid,
#         )
#         session.add(clock_out_entry)
#         session.flush()

#         # Log the admin action
#         admin_change = AdminTimeChange(
#             admin_id=admin_uid,
#             employee_id=payload.employee_id,
#             action=AdminTimeChangeAction.CREATE,
#             reason=admin_note,
#             clock_out_id=clock_out_entry.id,
#             dealership_id=active_dealership_id,
#             end_time=cutoff_time,
#             punch_date=cutoff_time.date().isoformat(),
#         )
#         session.add(admin_change)
#         session.commit()
#         session.refresh(clock_out_entry)

#         return AutoStopShiftResponse(
#             success=True,
#             message=(
#                 f"Auto-stopped shift for employee {payload.employee_id} at {active_dealership_id} after {duration_hours:.2f}h"
#             ),
#             employee_id=payload.employee_id,
#             threshold_hours=payload.threshold_hours,
#             is_over_threshold=True,
#             was_clock_out_created=True,
#             shift_start_time=format_utc_datetime(clock_in_ts),
#             shift_end_time=format_utc_datetime(cutoff_time),
#             shift_duration_hours=round(duration_hours, 2),
#             dealership_id=active_dealership_id,
#             created_timelog_id=clock_out_entry.id,
#             admin_id=admin_uid,
#         )

#     except HTTPException:
#         raise
#     except Exception as e:
#         session.rollback()
#         print(f"❌ Error during auto-stop overlong shift: {e}")
#         import traceback

#         print(f"Full traceback: {traceback.format_exc()}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Unexpected error in auto-stop endpoint: {str(e)}",
#         )


# --- REPORT: Recent Auto-Stop Events ---


class AutoStopEvent(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    admin_id: str
    dealership_id: str
    reason: str
    created_at: str
    threshold_hours: Optional[float] = None
    shift_start_time: Optional[str] = None
    shift_end_time: Optional[str] = None
    shift_duration_hours: Optional[float] = None
    clock_in_id: Optional[int] = None
    clock_out_id: Optional[int] = None


class AutoStopEventsResponse(BaseModel):
    events: List[AutoStopEvent]


@router.get("/auto-stop-events", response_model=AutoStopEventsResponse)
async def list_auto_stop_events(
    limit: int = 100,
    since_iso: Optional[str] = None,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """Return recent auto-stop events (auto-created clock-out due to overlong shift).

    - Filtered by AdminTimeChange.reason prefix "AUTO STOP SHIFT".
    - Returns employee, times, dealership, and referenced clock pair if available.
    - Optional since_iso filters events since a UTC ISO timestamp.
    - limit caps the number of results (default 100).
    """
    # Build base query on AdminTimeChange entries that our auto-stop endpoint created
    query = select(AdminTimeChange).where(
        AdminTimeChange.action == AdminTimeChangeAction.CREATE
    )
    # Use reason prefix to distinguish these auto-stops
    # We saved admin_change.reason = admin_note which starts with "AUTO STOP SHIFT:"
    # SQLModel doesn't have startswith across backends; fetch a recent window and filter in Python.

    # Pull recent entries ordered by created_at desc
    q = query.order_by(AdminTimeChange.created_at.desc())
    entries = session.exec(q).all()

    events: List[AutoStopEvent] = []

    # Optional since filter
    since_dt: Optional[datetime] = None
    if since_iso:
        try:
            since_dt = datetime.fromisoformat(since_iso)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid since_iso timestamp; must be ISO 8601",
            )

    for change in entries:
        if not change.reason or not change.reason.startswith("AUTO STOP SHIFT:"):
            continue
        if since_dt and change.created_at < since_dt:
            break  # entries are desc; we can stop

        # Try to parse threshold and duration from reason string
        # Format example: "AUTO STOP SHIFT: Exceeded threshold 15.00h (actual 16.25h) | extra"
        threshold_val: Optional[float] = None
        duration_val: Optional[float] = None
        try:
            import re

            m1 = re.search(r"threshold\s+([0-9]+(?:\.[0-9]+)?)h", change.reason)
            if m1:
                threshold_val = float(m1.group(1))
            m2 = re.search(r"actual\s+([0-9]+(?:\.[0-9]+)?)h", change.reason)
            if m2:
                duration_val = float(m2.group(1))
        except Exception:
            pass

        # Attempt to find the associated clock-in (the last CLOCK_IN before end_time)
        clock_in_id: Optional[int] = None
        shift_start_iso: Optional[str] = None
        if change.end_time:
            last_clock_in = session.exec(
                select(TimeLog)
                .where(TimeLog.employee_id == change.employee_id)
                .where(TimeLog.punch_type == PunchType.CLOCK_IN)
                .where(TimeLog.timestamp <= change.end_time)
                .order_by(TimeLog.timestamp.desc())
                .limit(1)
            ).first()
            if last_clock_in:
                clock_in_id = last_clock_in.id
                # Ensure tz-aware ISO
                ts = last_clock_in.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                shift_start_iso = ts.isoformat()

        # Derived end time ISO
        shift_end_iso: Optional[str] = None
        if change.end_time:
            ts_end = (
                change.end_time
                if change.end_time.tzinfo
                else change.end_time.replace(tzinfo=timezone.utc)
            )
            shift_end_iso = ts_end.isoformat()

        # Enrich employee name (best-effort)
        employee_name: Optional[str] = None
        try:
            doc = firestore_db.collection("users").document(change.employee_id).get()
            if doc and doc.exists:
                data = doc.to_dict()
                employee_name = data.get("displayName")
        except Exception:
            pass

        events.append(
            AutoStopEvent(
                employee_id=change.employee_id,
                employee_name=employee_name,
                admin_id=change.admin_id,
                dealership_id=change.dealership_id,
                reason=change.reason,
                created_at=change.created_at.isoformat(),
                threshold_hours=threshold_val,
                shift_start_time=shift_start_iso,
                shift_end_time=shift_end_iso,
                shift_duration_hours=duration_val,
                clock_in_id=clock_in_id,
                clock_out_id=change.clock_out_id,
            )
        )

        if len(events) >= limit:
            break

    return AutoStopEventsResponse(events=events)


# --- BULK AUTO-STOP: scan all employees and stop overlong active shifts ---


class AutoStopBulkRequestPayload(BaseModel):
    threshold_hours: float = 15.0
    dealership_id: Optional[str] = None
    reason: Optional[str] = None


class AutoStopBulkResultItem(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    dealership_id: Optional[str] = None
    was_clock_out_created: bool
    shift_start_time: Optional[str] = None
    shift_end_time: Optional[str] = None
    shift_duration_hours: Optional[float] = None
    created_timelog_id: Optional[int] = None
    message: str


class AutoStopBulkResponse(BaseModel):
    success: bool
    total_candidates: int
    total_stopped: int
    results: List[AutoStopBulkResultItem]


@router.post("/auto-stop-overlong-shifts", response_model=AutoStopBulkResponse)
async def auto_stop_overlong_shifts(
    payload: AutoStopBulkRequestPayload,
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role),
):
    """Scan all employees for active shifts over threshold and auto-stop them.

    - Without requiring employee_id. Optionally filter by dealership_id.
    - Uses last CLOCK_IN within a short lookback window (3d) to determine active shifts.
    - Creates CLOCK_OUT entries and logs AdminTimeChange for each stopped shift.
    """
    admin_uid = admin.get("uid")
    if not admin_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin user ID not found"
        )

    now_utc = datetime.now(timezone.utc)
    lookback_date = now_utc - timedelta(days=3)

    # One pass to get each employee's most recent punch in the lookback window
    recent_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= lookback_date)
        .order_by(TimeLog.employee_id.asc(), TimeLog.timestamp.desc())
    ).all()

    last_by_employee: dict[str, TimeLog] = {}
    for log in recent_logs:
        if log.employee_id not in last_by_employee:
            last_by_employee[log.employee_id] = log

    results: List[AutoStopBulkResultItem] = []
    total_candidates = 0
    total_stopped = 0

    for employee_id, last_log in last_by_employee.items():
        # Consider only those whose most recent punch is a CLOCK_IN (currently active)
        if last_log.punch_type != PunchType.CLOCK_IN:
            continue

        # Dealership filter (if provided)
        if payload.dealership_id and last_log.dealership_id != payload.dealership_id:
            continue

        # Compute duration since last CLOCK_IN
        ts = (
            last_log.timestamp
            if last_log.timestamp.tzinfo
            else last_log.timestamp.replace(tzinfo=timezone.utc)
        )
        duration_hours = (now_utc - ts).total_seconds() / 3600.0

        if duration_hours <= payload.threshold_hours:
            continue

        total_candidates += 1

        # Determine dealership for clock-out
        active_dealership_id = payload.dealership_id or last_log.dealership_id

        # Compose admin note consistent with single endpoint
        cutoff_time = ts + timedelta(hours=payload.threshold_hours)
        reason_suffix = f" | {payload.reason}" if payload.reason else ""
        admin_note = f"AUTO STOP SHIFT: Exceeded threshold {payload.threshold_hours:.2f}h (actual {duration_hours:.2f}h){reason_suffix}"

        try:
            # Create CLOCK_OUT entry at shift_start + threshold_hours
            clock_out_entry = TimeLog(
                employee_id=employee_id,
                dealership_id=active_dealership_id,
                punch_type=PunchType.CLOCK_OUT,
                timestamp=cutoff_time,
                admin_notes=admin_note,
                admin_modifier_id=admin_uid,
            )
            session.add(clock_out_entry)
            session.flush()

            # Log the admin action
            admin_change = AdminTimeChange(
                admin_id=admin_uid,
                employee_id=employee_id,
                action=AdminTimeChangeAction.CREATE,
                reason=admin_note,
                clock_out_id=clock_out_entry.id,
                dealership_id=active_dealership_id,
                end_time=cutoff_time,
                punch_date=cutoff_time.date().isoformat(),
            )
            session.add(admin_change)
            session.commit()

            # Hydrate employee name (best-effort)
            employee_name: Optional[str] = None
            try:
                doc = firestore_db.collection("users").document(employee_id).get()
                if doc and doc.exists:
                    data = doc.to_dict()
                    employee_name = data.get("displayName")
            except Exception:
                pass

            total_stopped += 1
            results.append(
                AutoStopBulkResultItem(
                    employee_id=employee_id,
                    employee_name=employee_name,
                    dealership_id=active_dealership_id,
                    was_clock_out_created=True,
                    shift_start_time=ts.isoformat(),
                    shift_end_time=cutoff_time.isoformat(),
                    shift_duration_hours=round(duration_hours, 2),
                    created_timelog_id=clock_out_entry.id,
                    message="Auto-stopped overlong shift",
                )
            )
        except Exception as e:
            session.rollback()
            results.append(
                AutoStopBulkResultItem(
                    employee_id=employee_id,
                    employee_name=None,
                    dealership_id=active_dealership_id,
                    was_clock_out_created=False,
                    shift_start_time=ts.isoformat(),
                    shift_end_time=None,
                    shift_duration_hours=round(duration_hours, 2),
                    created_timelog_id=None,
                    message=f"Failed to auto-stop: {str(e)}",
                )
            )

    return AutoStopBulkResponse(
        success=True,
        total_candidates=total_candidates,
        total_stopped=total_stopped,
        results=results,
    )
