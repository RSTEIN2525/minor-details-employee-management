import os
from sqlmodel import Session, select
from db.session import engine
from models.time_log import TimeLog
from datetime import timedelta
from zoneinfo import ZoneInfo

def get_all_shifts_for_employee(employee_id):
    with Session(engine) as session:
        # Get all clock events for this employee, ordered by timestamp
        events = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id == employee_id)
            .order_by(TimeLog.timestamp.asc())
        ).all()
        return events

def pair_shifts(events):
    pairs = []
    in_event = None
    for event in events:
        if event.punch_type == "clock_in":
            in_event = event
        elif event.punch_type == "clock_out" and in_event:
            # Only pair if dealership matches (optional, can be removed)
            pairs.append((in_event, event))
            in_event = None
    return pairs

def main():
    employee_id = "D3akEDdYgwQTd2Fg2DjsXR2cAyy1"
    events = get_all_shifts_for_employee(employee_id)
    pairs = pair_shifts(events)
    tz = ZoneInfo("America/New_York")
    md_lines = [
        f"# Shift History for Employee: {employee_id}",
        "",
        "_Times shown in America/New_York (automatically reflects EST/EDT daylight savings)._",
        "",
        "| Date | In | Out | Dealership | Total Hours |",
        "|------|----|-----|------------|-------------|",
    ]
    for clock_in, clock_out in pairs:
        # Convert from stored UTC timestamps to America/New_York
        in_dt_local = clock_in.timestamp.astimezone(tz)
        out_dt_local = clock_out.timestamp.astimezone(tz)
        # Build date and 12-hour times like 9:00am, 1:30pm
        date_str = in_dt_local.strftime("%Y-%m-%d")
        def fmt(dt):
            return dt.strftime("%I:%M%p").lstrip('0').lower()
        in_time = fmt(in_dt_local)
        out_time = fmt(out_dt_local)
        dealership = clock_in.dealership_id
        total_hours = (clock_out.timestamp - clock_in.timestamp).total_seconds() / 3600
        md_lines.append(f"| {date_str} | {in_time} | {out_time} | {dealership} | {total_hours:.2f} |")
    md_content = "\n".join(md_lines)
    out_path = f"scripts/employee_{employee_id}_shifts.md"
    with open(out_path, "w") as f:
        f.write(md_content)
    print(f"Wrote shift history to {out_path}")

if __name__ == "__main__":
    main()
