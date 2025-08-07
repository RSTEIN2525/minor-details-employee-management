import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

from sqlmodel import Session, select

from db.session import get_session
from models.admin_time_change import AdminTimeChange, AdminTimeChangeAction
from models.time_log import PunchType, TimeLog


def _process_once(threshold_hours: float) -> None:
    """Blocking DB work for a single scan iteration (run off the event loop)."""
    session: Session | None = None
    try:
        now = datetime.now(timezone.utc)
        lookback_start = now - timedelta(days=3)

        session = next(get_session())

        # Find all employees with activity recently to limit scope
        employee_id_rows: List[tuple] = session.exec(
            select(TimeLog.employee_id)
            .where(TimeLog.timestamp >= lookback_start)
            .distinct()
        ).all()

        employee_ids = [row[0] for row in employee_id_rows]
        if not employee_ids:
            return

        for employee_id in employee_ids:
            # Most recent punch for this employee (any dealership)
            last_log: TimeLog | None = session.exec(
                select(TimeLog)
                .where(TimeLog.employee_id == employee_id)
                .order_by(TimeLog.timestamp.desc())
                .limit(1)
            ).first()

            if last_log is None or last_log.punch_type != PunchType.CLOCK_IN:
                continue

            # Ensure tz-aware
            last_in_ts = last_log.timestamp
            if last_in_ts.tzinfo is None:
                last_in_ts = last_in_ts.replace(tzinfo=timezone.utc)

            hours_open = (now - last_in_ts).total_seconds() / 3600.0
            if hours_open < threshold_hours:
                continue

            # Double-check no newer CLOCK_OUT exists (race protection)
            newer_log: TimeLog | None = session.exec(
                select(TimeLog)
                .where(TimeLog.employee_id == employee_id)
                .where(TimeLog.timestamp > last_log.timestamp)
                .order_by(TimeLog.timestamp.desc())
                .limit(1)
            ).first()
            if newer_log is not None and newer_log.punch_type == PunchType.CLOCK_OUT:
                continue

            # Create an auto CLOCK_OUT at exactly last_in_ts + threshold_hours
            stop_time = last_in_ts + timedelta(hours=threshold_hours)

            clock_out_entry = TimeLog(
                employee_id=employee_id,
                dealership_id=last_log.dealership_id,
                punch_type=PunchType.CLOCK_OUT,
                timestamp=stop_time,
                admin_notes=(
                    f"AUTO STOP SHIFT: exceeded {threshold_hours:.2f} hours."
                ),
                admin_modifier_id="system",
            )
            session.add(clock_out_entry)
            session.flush()

            # Audit trail
            audit = AdminTimeChange(
                admin_id="system",
                employee_id=employee_id,
                action=AdminTimeChangeAction.CREATE,
                reason=(
                    f"Auto stop shift after {threshold_hours:.2f} hours (system)."
                ),
                clock_out_id=clock_out_entry.id,
                dealership_id=last_log.dealership_id,
                end_time=stop_time,
                punch_date=stop_time.date().isoformat(),
            )
            session.add(audit)
            session.commit()

    except Exception as e:
        print(f"[SHIFT_GUARD] Error in iteration: {e}")
        if session is not None:
            try:
                session.rollback()
            except Exception:
                pass
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


async def run_shift_guard_once_async(threshold_hours: float = 15.0) -> None:
    """Async wrapper to run a single iteration off the event loop."""
    await asyncio.to_thread(_process_once, threshold_hours)


