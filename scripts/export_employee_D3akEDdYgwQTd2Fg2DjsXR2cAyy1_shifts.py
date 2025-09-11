import os
from sqlmodel import Session, select
from db.session import engine
from models.time_log import TimeLog
from datetime import timedelta

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
    md_lines = [
        "# Shift History for Employee: {}".format(employee_id),
        "",
        "| In Time (UTC)        | Out Time (UTC)       | Dealership         | Total Hours |",
        "|----------------------|----------------------|--------------------|-------------|",
    ]
    for clock_in, clock_out in pairs:
        in_time = clock_in.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        out_time = clock_out.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        dealership = clock_in.dealership_id
        total_hours = (clock_out.timestamp - clock_in.timestamp).total_seconds() / 3600
        md_lines.append(f"| {in_time} | {out_time} | {dealership} | {total_hours:.2f} |")
    md_content = "\n".join(md_lines)
    out_path = f"scripts/employee_{employee_id}_shifts.md"
    with open(out_path, "w") as f:
        f.write(md_content)
    print(f"Wrote shift history to {out_path}")

if __name__ == "__main__":
    main()
