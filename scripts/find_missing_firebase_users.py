import os
from sqlmodel import Session, select
from db.session import engine
from models.time_log import TimeLog
from core.firebase import db as firebase_db

# 1. Get all unique employee IDs from time_log
def get_all_employee_ids():
    with Session(engine) as session:
        result = session.exec(select(TimeLog.employee_id).distinct())
        return result.all()

# 2. Check if user doc exists in Firebase

def firebase_user_exists(employee_id):
    doc_ref = firebase_db.collection("users").document(employee_id)
    doc = doc_ref.get()
    return doc.exists

# 3. Get last clock-in and clock-out for a user

def get_last_clock_events(employee_id):
    with Session(engine) as session:
        # Last clock-in
        clock_in = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id == employee_id)
            .where(TimeLog.punch_type == "clock_in")
            .order_by(TimeLog.timestamp.desc())
        ).first()
        # Last clock-out
        clock_out = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id == employee_id)
            .where(TimeLog.punch_type == "clock_out")
            .order_by(TimeLog.timestamp.desc())
        ).first()
        return clock_in, clock_out

def main():
    print("Finding users missing from Firebase...")
    all_ids = get_all_employee_ids()
    missing = []
    for eid in all_ids:
        if not firebase_user_exists(eid):
            clock_in, clock_out = get_last_clock_events(eid)
            dealership = clock_in.dealership_id if clock_in else (clock_out.dealership_id if clock_out else None)
            missing.append({
                "employee_id": eid,
                "last_clock_in": clock_in.timestamp.isoformat() if clock_in else None,
                "last_clock_out": clock_out.timestamp.isoformat() if clock_out else None,
                "dealership_id": dealership
            })
    print("\nUsers not found in Firebase:")
    for entry in missing:
        print(entry)

if __name__ == "__main__":
    main()
