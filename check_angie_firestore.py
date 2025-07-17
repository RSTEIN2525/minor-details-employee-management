import asyncio

from core.firebase import db as firestore_db


async def check_angie_dealership_assignments():
    """Check Angie's dealership assignments in Firestore"""

    employee_id = "9GTj6B35LBYCMk6T58itF6Rzjvr2"

    try:
        # Get user document from Firestore
        user_ref = firestore_db.collection("users").document(employee_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            print(f"❌ User document not found for employee ID: {employee_id}")
            return

        user_data = user_doc.to_dict()
        print(f"✅ Found user document for: {user_data.get('displayName', 'Unknown')}")
        print(f"📧 Email: {user_data.get('email', 'N/A')}")
        print(f"👤 Role: {user_data.get('role', 'N/A')}")
        print(f"💰 Hourly Wage: {user_data.get('hourlyWage', 'N/A')}")

        # Check dealership assignments
        raw_dealerships = user_data.get("dealerships", "")
        print(
            f"🏢 Raw dealerships field: '{raw_dealerships}' (type: {type(raw_dealerships)})"
        )

        if isinstance(raw_dealerships, list):
            employee_dealerships = [str(d).strip() for d in raw_dealerships]
        else:
            employee_dealerships = [
                s.strip() for s in str(raw_dealerships).split(",") if s.strip()
            ]

        print(f"🏢 Parsed dealerships: {employee_dealerships}")

        # Check timeClockDealerships
        raw_tc_dealers = user_data.get("timeClockDealerships", "")
        print(
            f"⏰ Raw timeClockDealerships field: '{raw_tc_dealers}' (type: {type(raw_tc_dealers)})"
        )

        if isinstance(raw_tc_dealers, list):
            time_clock_dealerships = [str(d).strip() for d in raw_tc_dealers]
        else:
            time_clock_dealerships = [
                s.strip() for s in str(raw_tc_dealers).split(",") if s.strip()
            ]

        print(f"⏰ Parsed timeClockDealerships: {time_clock_dealerships}")

        # Combined dealerships
        combined_dealerships = set(employee_dealerships) | set(time_clock_dealerships)
        print(f"🔗 Combined dealerships: {combined_dealerships}")

        # Check if assigned to any specific dealership
        target_dealership = "Len Stoler Lexus"
        is_assigned = target_dealership in combined_dealerships
        print(f"🎯 Is assigned to '{target_dealership}': {is_assigned}")

        # Show all fields for debugging
        print("\n📋 All user fields:")
        for key, value in user_data.items():
            print(f"  {key}: {value} (type: {type(value)})")

    except Exception as e:
        print(f"❌ Error checking user document: {e}")


if __name__ == "__main__":
    asyncio.run(check_angie_dealership_assignments())
