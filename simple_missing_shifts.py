#!/usr/bin/env python3
"""
Simple working missing shifts endpoint replacement
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, func, select

from core.deps import require_admin_role
from core.firebase import db as firestore_db
from db.session import get_session
from models.time_log import PunchType, TimeLog


class MissingShiftEmployeeSummary(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    missing_clock_ins: int = 0
    missing_clock_outs: int = 0
    has_long_running_shift_over_12h: bool = False
    long_running_duration_hours: Optional[float] = None
    last_known_clock_in_at: Optional[str] = None
    was_auto_stopped_recently: bool = False
    auto_stop_count: int = 0


def get_missing_shifts_summary_simple(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: Session = None,
):
    """Simple missing shifts detection without complex overnight logic"""

    if start_date and end_date:
        start_dt = datetime.combine(
            start_date, datetime.min.time(), tzinfo=timezone.utc
        )
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    else:
        today = datetime.now(timezone.utc).date()
        end_dt = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
        start_dt = datetime.combine(
            today - timedelta(days=27), datetime.min.time(), tzinfo=timezone.utc
        )

    # Get all punches in the window
    main_logs = session.exec(
        select(TimeLog)
        .where(TimeLog.timestamp >= start_dt)
        .where(TimeLog.timestamp <= end_dt)
        .order_by(TimeLog.timestamp)
    ).all()

    # Group by employee
    punches_by_employee: Dict[str, List[TimeLog]] = {}
    for log in main_logs:
        punches_by_employee.setdefault(log.employee_id, []).append(log)

    employee_ids = list(punches_by_employee.keys())

    # Get carry-in state
    carry_in_state: Dict[str, TimeLog] = {}
    if employee_ids:
        subquery = (
            select(
                TimeLog.employee_id,
                func.max(TimeLog.timestamp).label("max_ts"),
            )
            .where(TimeLog.employee_id.in_(employee_ids))
            .where(TimeLog.timestamp < start_dt)
            .group_by(TimeLog.employee_id)
            .subquery()
        )
        carry_in_logs = session.exec(
            select(TimeLog).join(
                subquery,
                (TimeLog.employee_id == subquery.c.employee_id)
                & (TimeLog.timestamp == subquery.c.max_ts),
            )
        ).all()
        for log in carry_in_logs:
            carry_in_state[log.employee_id] = log

    # Process each employee
    anomalies: List[MissingShiftEmployeeSummary] = []
    for emp_id in employee_ids:
        # Get all punches for this employee
        all_employee_punches = []

        # Add carry-in punch if exists
        if emp_id in carry_in_state:
            all_employee_punches.append(carry_in_state[emp_id])

        # Add in-window punches
        all_employee_punches.extend(punches_by_employee.get(emp_id, []))

        # Sort by timestamp
        sorted_punches = sorted(all_employee_punches, key=lambda x: x.timestamp)

        # Simple pairing logic
        missing_in = 0
        missing_out = 0
        clock_in_time = None
        last_clock_in_time = None

        for punch in sorted_punches:
            punch_ts = punch.timestamp
            if punch_ts.tzinfo is None:
                punch_ts = punch_ts.replace(tzinfo=timezone.utc)

            is_in_window = start_dt <= punch_ts <= end_dt

            if punch.punch_type == PunchType.CLOCK_IN:
                if clock_in_time is not None and is_in_window:
                    missing_out += 1  # Consecutive INs
                clock_in_time = punch_ts
                if is_in_window:
                    last_clock_in_time = punch_ts
            elif punch.punch_type == PunchType.CLOCK_OUT:
                if clock_in_time is None and is_in_window:
                    missing_in += 1  # Orphan OUT
                else:
                    clock_in_time = None  # Normal pair

        # SIMPLIFIED: Don't flag trailing open shifts (too many false positives)
        # Only flag clear consecutive INs and orphan OUTs

        if missing_in > 0 or missing_out > 0:
            anomalies.append(
                MissingShiftEmployeeSummary(
                    employee_id=emp_id,
                    missing_clock_ins=missing_in,
                    missing_clock_outs=missing_out,
                    last_known_clock_in_at=(
                        last_clock_in_time.isoformat() if last_clock_in_time else None
                    ),
                )
            )

    # Hydrate names
    if anomalies:
        emp_ids_with_anomalies = [a.employee_id for a in anomalies]
        names: Dict[str, str] = {}
        for emp_id in emp_ids_with_anomalies:
            try:
                doc = firestore_db.collection("users").document(emp_id).get()
                if getattr(doc, "exists", False):
                    data = doc.to_dict() or {}
                    names[emp_id] = data.get("displayName", "Unknown")
            except Exception:
                continue
        for anomaly in anomalies:
            anomaly.employee_name = names.get(anomaly.employee_id)

    return anomalies


if __name__ == "__main__":
    print("Simple missing shifts algorithm - no trailing open shift detection")
