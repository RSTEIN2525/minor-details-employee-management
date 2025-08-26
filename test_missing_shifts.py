#!/usr/bin/env python3
"""
Test script to debug the missing-shifts algorithm locally.
Run with: python test_missing_shifts.py
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional


class PunchType(str, Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"


@dataclass
class TestPunch:
    employee_id: str
    timestamp: datetime
    punch_type: PunchType

    def __str__(self):
        return f"{self.employee_id}: {self.punch_type.value} at {self.timestamp.strftime('%m/%d %H:%M')}"


@dataclass
class MissingShiftResult:
    employee_id: str
    employee_name: str
    has_unmatched_punches: bool
    count_unmatched_punches: int
    has_long_running_shift_over_12h: bool
    long_running_duration_hours: Optional[float]
    last_clock_in_at: Optional[str]


def analyze_missing_shifts(
    punches: List[TestPunch],
    start_date: date,
    end_date: date,
    grace_hours: float = 12.0,
) -> List[MissingShiftResult]:
    """
    Test version of the missing shifts algorithm
    """
    now = datetime.now(timezone.utc)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    print(f"\n=== ANALYSIS WINDOW ===")
    print(f"Start: {start_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"End: {end_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"Grace period: {grace_hours}h")
    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M')}")

    # Separate in-window punches from carry-in punches
    main_punches = [p for p in punches if start_dt <= p.timestamp <= end_dt]
    carry_in_punches = [p for p in punches if p.timestamp < start_dt]

    print(f"\n=== PUNCH BREAKDOWN ===")
    print(f"Carry-in punches (before window): {len(carry_in_punches)}")
    print(f"In-window punches: {len(main_punches)}")

    # Get employee IDs from main punches
    employee_ids = list(set(p.employee_id for p in main_punches))

    # Get carry-in STATE per employee (not just last punch)
    # We need to determine if they were "clocked in" or "clocked out" at start of window
    carry_in_state = {}  # employee_id -> ("IN" | "OUT" | None, timestamp)

    for emp_id in employee_ids:
        emp_carry_punches = [p for p in carry_in_punches if p.employee_id == emp_id]
        if emp_carry_punches:
            # Process punches to determine state at window start
            state = None
            last_timestamp = None
            for punch in sorted(emp_carry_punches, key=lambda p: p.timestamp):
                if punch.punch_type == PunchType.CLOCK_IN:
                    state = "IN"
                else:
                    state = "OUT"
                last_timestamp = punch.timestamp
            carry_in_state[emp_id] = (state, last_timestamp)
            print(
                f"  Carry-in state for {emp_id}: {state} at {last_timestamp.strftime('%m/%d %H:%M') if last_timestamp else 'None'}"
            )

    print(f"Carry-in states: {carry_in_state}")

    # Only process in-window punches (carry-in state is used for initialization)
    all_punches = sorted(main_punches, key=lambda p: (p.employee_id, p.timestamp))

    results = {}

    # Process each employee
    for emp_id in employee_ids:
        emp_punches = [p for p in all_punches if p.employee_id == emp_id]

        print(f"\n=== EMPLOYEE {emp_id} ===")
        for punch in emp_punches:
            in_window = start_dt <= punch.timestamp <= end_dt
            print(f"  {punch} {'(in window)' if in_window else '(carry-in)'}")

        # Initialize state from carry-in
        state, carry_timestamp = carry_in_state.get(emp_id, (None, None))
        if state == "IN":
            open_in_time = carry_timestamp
            print(
                f"    → Initialized: already clocked in from {carry_timestamp.strftime('%m/%d %H:%M')}"
            )
        else:
            open_in_time = None
            print(f"    → Initialized: clocked out (state={state})")

        missing_in = 0
        missing_out = 0

        for punch in emp_punches:
            if punch.punch_type == PunchType.CLOCK_IN:
                if open_in_time is not None:
                    print(f"    → Missing CLOCK_OUT (consecutive INs)")
                    missing_out += 1
                open_in_time = punch.timestamp
                print(
                    f"    → Open shift started at {punch.timestamp.strftime('%m/%d %H:%M')}"
                )
            else:  # CLOCK_OUT
                if open_in_time is None:
                    print(f"    → Missing CLOCK_IN (orphan OUT)")
                    missing_in += 1
                else:
                    duration = (punch.timestamp - open_in_time).total_seconds() / 3600.0
                    print(f"    → Closed shift ({duration:.1f}h)")
                    open_in_time = None

        # Handle trailing open shift
        long_running_flag = False
        long_running_hours = None
        if open_in_time is not None:
            duration = (now - open_in_time).total_seconds() / 3600.0
            print(f"    → Still open: {duration:.1f}h")
            if duration > grace_hours:
                long_running_flag = True
                long_running_hours = round(duration, 2)
                print(f"    → LONG RUNNING (>{grace_hours}h)")
            else:
                print(f"    → Normal work (within {grace_hours}h grace)")

        total_unmatched = missing_in + missing_out
        print(
            f"  SUMMARY: {missing_in} missing INs, {missing_out} missing OUTs, long_running={long_running_flag}"
        )

        if total_unmatched > 0 or long_running_flag:
            results[emp_id] = MissingShiftResult(
                employee_id=emp_id,
                employee_name=emp_id,  # simplified for test
                has_unmatched_punches=total_unmatched > 0,
                count_unmatched_punches=total_unmatched,
                has_long_running_shift_over_12h=long_running_flag,
                long_running_duration_hours=long_running_hours,
                last_clock_in_at=open_in_time.isoformat() if open_in_time else None,
            )

    return list(results.values())


def test_scenarios():
    """Test various scenarios"""

    # Test data
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)
    two_days_ago = today - timedelta(days=2)

    # Analysis window: yesterday only
    start_date = yesterday
    end_date = yesterday

    print("=" * 60)
    print("MISSING SHIFTS ALGORITHM TEST")
    print("=" * 60)

    # Scenario 1: Jose's case - missing clock out from Aug 19
    print("\n" + "=" * 40)
    print("SCENARIO 1: Jose's Missing Clock-Out")
    print("=" * 40)

    jose_punches = [
        # Aug 19: Clock in but no clock out (MISSING)
        TestPunch(
            "jose",
            datetime(2025, 8, 19, 8, 57, tzinfo=timezone.utc),
            PunchType.CLOCK_IN,
        ),
        # Aug 20: Normal shift
        TestPunch(
            "jose", datetime(2025, 8, 20, 9, 1, tzinfo=timezone.utc), PunchType.CLOCK_IN
        ),
        TestPunch(
            "jose",
            datetime(2025, 8, 20, 20, 51, tzinfo=timezone.utc),
            PunchType.CLOCK_OUT,
        ),
        # Aug 21: Currently working
        TestPunch(
            "jose",
            datetime(2025, 8, 21, 12, 58, tzinfo=timezone.utc),
            PunchType.CLOCK_IN,
        ),
    ]

    # Test with Aug 19-21 window
    results = analyze_missing_shifts(jose_punches, date(2025, 8, 19), date(2025, 8, 21))
    print(f"\nRESULT: {len(results)} employees with issues")
    for r in results:
        print(
            f"  {r.employee_id}: {r.count_unmatched_punches} unmatched, long_running={r.has_long_running_shift_over_12h}"
        )

    # Scenario 2: Normal worker (should NOT be flagged)
    print("\n" + "=" * 40)
    print("SCENARIO 2: Normal Worker (Today)")
    print("=" * 40)

    normal_punches = [
        # Yesterday: complete shift
        TestPunch(
            "adan",
            datetime.combine(
                yesterday, datetime.min.time().replace(hour=8), tzinfo=timezone.utc
            ),
            PunchType.CLOCK_IN,
        ),
        TestPunch(
            "adan",
            datetime.combine(
                yesterday, datetime.min.time().replace(hour=17), tzinfo=timezone.utc
            ),
            PunchType.CLOCK_OUT,
        ),
        # Today: currently working (should NOT be flagged)
        TestPunch(
            "adan",
            datetime.combine(
                today, datetime.min.time().replace(hour=8), tzinfo=timezone.utc
            ),
            PunchType.CLOCK_IN,
        ),
    ]

    results = analyze_missing_shifts(normal_punches, today, today)
    print(f"\nRESULT: {len(results)} employees with issues")
    for r in results:
        print(
            f"  {r.employee_id}: {r.count_unmatched_punches} unmatched, long_running={r.has_long_running_shift_over_12h}"
        )

    # Scenario 3: Actually problematic cases
    print("\n" + "=" * 40)
    print("SCENARIO 3: Real Problems")
    print("=" * 40)

    problem_punches = [
        # Missing clock out yesterday
        TestPunch(
            "problem1",
            datetime.combine(
                yesterday, datetime.min.time().replace(hour=8), tzinfo=timezone.utc
            ),
            PunchType.CLOCK_IN,
        ),
        # Missing clock in yesterday
        TestPunch(
            "problem2",
            datetime.combine(
                yesterday, datetime.min.time().replace(hour=17), tzinfo=timezone.utc
            ),
            PunchType.CLOCK_OUT,
        ),
        # Long running shift (>12h)
        TestPunch("problem3", (now - timedelta(hours=15)), PunchType.CLOCK_IN),
    ]

    results = analyze_missing_shifts(problem_punches, yesterday, today)
    print(f"\nRESULT: {len(results)} employees with issues")
    for r in results:
        print(
            f"  {r.employee_id}: {r.count_unmatched_punches} unmatched, long_running={r.has_long_running_shift_over_12h}"
        )
        if r.long_running_duration_hours:
            print(f"    Long running: {r.long_running_duration_hours}h")


if __name__ == "__main__":
    test_scenarios()
