UNPAID_BREAK_MINUTES = 30  # default 30-minute unpaid lunch
THRESHOLD_HOURS = 5.0       # only apply break if shift >= 5 hours


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