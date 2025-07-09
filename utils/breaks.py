UNPAID_BREAK_MINUTES = 30  # default 30-minute unpaid lunch
THRESHOLD_HOURS = 5.0  # only apply break if shift >= 5 hours


def apply_unpaid_break(raw_hours: float) -> float:
    """Return paid hours after auto-deducting the standard unpaid break.

    Args:
        raw_hours: Hours between clock-in and clock-out (float).

    Returns:
        float: Paid hours after deduction (never below zero).
    """
    if raw_hours >= THRESHOLD_HOURS:
        paid = raw_hours - UNPAID_BREAK_MINUTES / 60.0
        return paid if paid > 0 else 0.0
    return raw_hours


def apply_daily_break(daily_raw_hours: float) -> float:
    """Return paid hours after auto-deducting ONE unpaid break per day.

    Business rule: One 30-minute lunch break per day if total daily hours >= 5 hours,
    regardless of how many shifts or dealerships the employee worked.

    Args:
        daily_raw_hours: Total raw hours worked in a single day (float).

    Returns:
        float: Paid hours after deduction (never below zero).
    """
    if daily_raw_hours >= THRESHOLD_HOURS:
        paid = daily_raw_hours - UNPAID_BREAK_MINUTES / 60.0
        return paid if paid > 0 else 0.0
    return daily_raw_hours


def calculate_daily_hours_with_breaks(shifts_by_day: dict) -> float:
    """Calculate total paid hours across multiple days with daily break deductions.

    Args:
        shifts_by_day: Dictionary where keys are date objects and values are lists
                      of (raw_hours, dealership_id) tuples for that day.

    Returns:
        float: Total paid hours across all days with daily break deductions applied.
    """
    total_paid_hours = 0.0

    for day_date, day_shifts in shifts_by_day.items():
        # Sum up all raw hours for this day across all shifts/dealerships
        daily_raw_hours = sum(shift_hours for shift_hours, _ in day_shifts)

        # Apply ONE break per day if daily total >= 5 hours
        daily_paid_hours = apply_daily_break(daily_raw_hours)
        total_paid_hours += daily_paid_hours

    return total_paid_hours
