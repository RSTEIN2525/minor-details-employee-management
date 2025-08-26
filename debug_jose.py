#!/usr/bin/env python3
"""
Debug Jose's missing clock-out on Aug 19th
"""
from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional


class PunchType(str, Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"


class TimeLog:
    def __init__(self, id, timestamp_str, punch_type, dealership_id):
        self.id = id
        self.timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        self.punch_type = PunchType(punch_type)
        self.dealership_id = dealership_id
        self.employee_id = "jose"


# Jose's recent clocks (reversed to chronological order)
jose_punches = [
    TimeLog(8870, "2025-08-13T00:53:44.020713Z", "clock_out", "Toyota Ourisman"),
    TimeLog(8934, "2025-08-13T13:03:50.593260Z", "clock_in", "Toyota Ourisman"),
    TimeLog(9090, "2025-08-14T01:06:41.082135Z", "clock_out", "Toyota Ourisman"),
    TimeLog(9135, "2025-08-14T12:56:36.373981Z", "clock_in", "Toyota Ourisman"),
    TimeLog(9306, "2025-08-15T01:09:37.566018Z", "clock_out", "Toyota Ourisman"),
    TimeLog(9380, "2025-08-15T13:11:56.713027Z", "clock_in", "Toyota Ourisman"),
    TimeLog(9537, "2025-08-16T01:37:10.890306Z", "clock_out", "Toyota Ourisman"),
    TimeLog(9590, "2025-08-16T12:54:03.810788Z", "clock_in", "Toyota Ourisman"),
    TimeLog(9733, "2025-08-16T23:17:05.979585Z", "clock_out", "Toyota Ourisman"),
    TimeLog(
        10013, "2025-08-19T12:57:02.441500Z", "clock_in", "Toyota Ourisman"
    ),  # MISSING CLOCK OUT
    TimeLog(10210, "2025-08-20T13:01:17.514507Z", "clock_out", "Toyota Ourisman"),
    TimeLog(10211, "2025-08-20T13:01:20.514507Z", "clock_in", "Toyota Ourisman"),
    TimeLog(10348, "2025-08-21T00:51:03.714544Z", "clock_out", "Toyota Ourisman"),
    TimeLog(10419, "2025-08-21T12:58:19.782438Z", "clock_in", "Toyota Ourisman"),
    TimeLog(10558, "2025-08-22T00:53:54.156104Z", "clock_out", "Toyota Ourisman"),
    TimeLog(10626, "2025-08-22T12:56:47.993695Z", "clock_in", "Toyota Ourisman"),
    TimeLog(10767, "2025-08-23T01:07:16.991712Z", "clock_out", "Toyota Ourisman"),
    TimeLog(10839, "2025-08-23T13:03:47.749208Z", "clock_in", "Toyota Ourisman"),
    TimeLog(10946, "2025-08-23T23:25:49.043355Z", "clock_out", "Toyota Ourisman"),
    TimeLog(11018, "2025-08-25T12:55:21.488236Z", "clock_in", "Toyota Ourisman"),
    TimeLog(11191, "2025-08-26T01:21:31.001383Z", "clock_out", "Toyota Ourisman"),
    TimeLog(11250, "2025-08-26T13:02:26.385603Z", "clock_in", "Toyota Ourisman"),
]


def debug_missing_shifts_algorithm(punches, start_date, end_date):
    """Debug version of the missing shifts algorithm"""

    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    print(f"Analysis window: {start_dt} to {end_dt}")
    print(f"Looking for missing punches on {start_date}")

    # Filter punches
    in_window_punches = [p for p in punches if start_dt <= p.timestamp <= end_dt]
    carry_in_punches = [p for p in punches if p.timestamp < start_dt]

    print(f"\nCarry-in punches: {len(carry_in_punches)}")
    for p in carry_in_punches[-3:]:  # Last 3
        print(f"  {p.timestamp}: {p.punch_type}")

    print(f"\nIn-window punches: {len(in_window_punches)}")
    for p in in_window_punches:
        print(f"  {p.timestamp}: {p.punch_type}")

    # Get carry-in state (last punch before window)
    carry_in_state = None
    if carry_in_punches:
        carry_in_state = carry_in_punches[-1]  # Most recent
        print(
            f"\nCarry-in state: {carry_in_state.punch_type} at {carry_in_state.timestamp}"
        )

    # Build all punches list
    all_punches = []
    if carry_in_state:
        all_punches.append(carry_in_state)
    all_punches.extend(in_window_punches)

    print(f"\nProcessing {len(all_punches)} total punches:")
    for i, p in enumerate(all_punches):
        is_carry = p.timestamp < start_dt
        print(
            f"  {i+1}. {p.timestamp}: {p.punch_type} {'(carry-in)' if is_carry else '(in-window)'}"
        )

    # Apply the algorithm
    missing_in = 0
    missing_out = 0
    clock_in_time = None
    last_clock_in_time = None

    print(f"\nRunning algorithm:")

    for punch in all_punches:
        punch_ts = punch.timestamp
        is_in_window = start_dt <= punch_ts <= end_dt

        print(f"\nProcessing: {punch_ts} {punch.punch_type} (in_window={is_in_window})")
        print(f"  Current state: clock_in_time={clock_in_time}")

        if punch.punch_type == PunchType.CLOCK_IN:
            if clock_in_time is not None and is_in_window:
                print(f"  → MISSING CLOCK_OUT detected! (consecutive INs)")
                missing_out += 1
            clock_in_time = punch_ts
            if is_in_window:
                last_clock_in_time = punch_ts
                print(f"  → Set last_clock_in_time = {last_clock_in_time}")
        elif punch.punch_type == PunchType.CLOCK_OUT:
            if clock_in_time is None and is_in_window:
                print(f"  → MISSING CLOCK_IN detected! (orphan OUT)")
                missing_in += 1
            else:
                print(f"  → Normal pair, clearing clock_in_time")
                clock_in_time = None

    # Check if still clocked in at end of window (missing final clock-out)
    print(f"\nChecking for trailing open shift:")
    print(f"  clock_in_time: {clock_in_time}")
    print(f"  last_clock_in_time: {last_clock_in_time}")

    if clock_in_time is not None and last_clock_in_time is not None:
        print(f"  → MISSING FINAL CLOCK_OUT detected! (still clocked in)")
        missing_out += 1

    print(f"\nFinal results:")
    print(f"  Missing INs: {missing_in}")
    print(f"  Missing OUTs: {missing_out}")
    print(f"  Last clock-in: {last_clock_in_time}")

    return missing_in, missing_out, last_clock_in_time


if __name__ == "__main__":
    print("=== DEBUGGING JOSE'S MISSING CLOCK-OUT ON AUG 19 ===")

    # Test Aug 19 specifically
    missing_in, missing_out, last_in = debug_missing_shifts_algorithm(
        jose_punches, date(2025, 8, 19), date(2025, 8, 19)
    )

    print(f"\nShould detect 1 missing clock-out on Aug 19")
    print(f"Actual result: {missing_out} missing clock-outs")

    if missing_out == 0:
        print("\n❌ ALGORITHM FAILED - Should have detected missing clock-out!")
    else:
        print(f"\n✅ ALGORITHM WORKED - Detected {missing_out} missing clock-out(s)")
