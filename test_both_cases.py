#!/usr/bin/env python3
"""
Test both Adan (should NOT be flagged) and Jose (should be flagged)
"""
from datetime import date, datetime, timezone
from enum import Enum


class PunchType(str, Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"


class TimeLog:
    def __init__(self, id, timestamp_str, punch_type, dealership_id):
        self.id = id
        self.timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        self.punch_type = PunchType(punch_type)
        self.dealership_id = dealership_id
        self.employee_id = "test"


# Adan's punches - should NOT be flagged (overnight shifts are normal)
adan_punches = [
    TimeLog(9311, "2025-08-15T01:36:08.509569Z", "clock_out", "Bob Bell Ford"),
    TimeLog(9171, "2025-08-14T13:23:27.607527Z", "clock_in", "Bob Bell Ford"),
    TimeLog(9386, "2025-08-15T13:14:03.458062Z", "clock_in", "Bob Bell Ford"),
    TimeLog(9528, "2025-08-16T01:05:57.783165Z", "clock_out", "Bob Bell Ford"),
    TimeLog(9636, "2025-08-16T13:27:07.575813Z", "clock_in", "Bob Bell Ford"),
    TimeLog(9764, "2025-08-17T00:14:00Z", "clock_out", "Bob Bell Ford"),
    TimeLog(9830, "2025-08-18T13:17:15.535651Z", "clock_in", "Bob Bell Ford"),
    TimeLog(9958, "2025-08-19T00:42:25.862902Z", "clock_out", "Bob Bell Ford"),
    TimeLog(
        10044, "2025-08-19T13:25:18.921892Z", "clock_in", "Bob Bell Ford"
    ),  # Should NOT be flagged
    TimeLog(
        10176, "2025-08-20T01:18:56.853376Z", "clock_out", "Bob Bell Ford"
    ),  # Clocks out next day (normal)
]

# Jose's punches - should be flagged (missing clock-out on Aug 19)
jose_punches = [
    TimeLog(9733, "2025-08-16T23:17:05.979585Z", "clock_out", "Toyota Ourisman"),
    TimeLog(
        10013, "2025-08-19T12:57:02.441500Z", "clock_in", "Toyota Ourisman"
    ),  # MISSING CLOCK OUT
    TimeLog(
        10210, "2025-08-20T13:01:17.514507Z", "clock_out", "Toyota Ourisman"
    ),  # This is 24+ hours later
]


def test_missing_shifts_algorithm(punches, employee_name, start_date, end_date):
    """Test the missing shifts algorithm"""

    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    print(f"\n=== Testing {employee_name} on {start_date} ===")

    # Filter punches
    in_window_punches = [p for p in punches if start_dt <= p.timestamp <= end_dt]
    carry_in_punches = [p for p in punches if p.timestamp < start_dt]

    print(f"In-window: {len(in_window_punches)}, Carry-in: {len(carry_in_punches)}")

    # Get carry-in state
    carry_in_state = None
    if carry_in_punches:
        carry_in_state = carry_in_punches[-1]
        print(
            f"Carry-in state: {carry_in_state.punch_type} at {carry_in_state.timestamp}"
        )

    # Build all punches
    all_punches = []
    if carry_in_state:
        all_punches.append(carry_in_state)
    all_punches.extend(in_window_punches)

    # Process algorithm
    missing_in = 0
    missing_out = 0
    clock_in_time = None
    last_clock_in_time = None

    for punch in all_punches:
        punch_ts = punch.timestamp
        is_in_window = start_dt <= punch_ts <= end_dt

        if punch.punch_type == PunchType.CLOCK_IN:
            if clock_in_time is not None and is_in_window:
                missing_out += 1
            clock_in_time = punch_ts
            if is_in_window:
                last_clock_in_time = punch_ts
        elif punch.punch_type == PunchType.CLOCK_OUT:
            if clock_in_time is None and is_in_window:
                missing_in += 1
            else:
                clock_in_time = None

    # Check for trailing open shift with 24-hour grace period
    if clock_in_time is not None and last_clock_in_time is not None:
        print(f"Checking trailing shift: last clock-in at {last_clock_in_time}")

        # Get future punches (after analysis window)
        future_punches = [p for p in punches if p.timestamp > end_dt]

        found_close_out = False
        if future_punches:
            for future_punch in sorted(future_punches, key=lambda x: x.timestamp):
                if future_punch.punch_type == PunchType.CLOCK_OUT:
                    hours_diff = (
                        future_punch.timestamp - last_clock_in_time
                    ).total_seconds() / 3600
                    print(
                        f"  Found clock-out {hours_diff:.1f}h later at {future_punch.timestamp}"
                    )
                    if hours_diff <= 24:
                        found_close_out = True
                        print(f"  → Within 24h grace period, NOT flagging")
                    else:
                        print(f"  → Beyond 24h grace period, FLAGGING")
                    break

        if not found_close_out:
            missing_out += 1
            print(f"  → No close clock-out found, FLAGGING")

    print(f"Result: {missing_in} missing INs, {missing_out} missing OUTs")
    return missing_in, missing_out


if __name__ == "__main__":
    # Test Adan on Aug 19 (should NOT be flagged - clocks out next day)
    adan_in, adan_out = test_missing_shifts_algorithm(
        adan_punches, "Adan", date(2025, 8, 19), date(2025, 8, 19)
    )

    # Test Jose on Aug 19 (should be flagged - no close clock-out)
    jose_in, jose_out = test_missing_shifts_algorithm(
        jose_punches, "Jose", date(2025, 8, 19), date(2025, 8, 19)
    )

    print(f"\n=== SUMMARY ===")
    print(
        f"Adan (should be 0): {adan_out} missing clock-outs {'✅' if adan_out == 0 else '❌'}"
    )
    print(
        f"Jose (should be 1): {jose_out} missing clock-outs {'✅' if jose_out == 1 else '❌'}"
    )
