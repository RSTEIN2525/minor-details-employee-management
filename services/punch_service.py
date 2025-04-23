from sqlmodel import Session, select
from datetime import datetime, timezone
from models.time_log import TimeLog, PunchType
from utils.geofence import is_within_radius
from models.shop import Shop


class PunchService:

    @staticmethod
    def validate_and_save(
        employee_id: str,
        user_dealerships: list[str],
        punch_type: PunchType,
        latitude: float,
        longitude: float,
        session: Session,
    ):

        # 0) Must supply location
        if latitude is None or longitude is None:
            return {"status": "error", "message": "Location required to punch."}

        # 1) Check each shop the user belongs to
        valid_shop = None
        for shop_id in user_dealerships:
            shop = session.get(Shop, shop_id)
            if not shop:
                continue  # unknown shop, skip
            if is_within_radius(
                latitude,
                longitude,
                shop.center_lat,
                shop.center_lng,
                shop.radius_meters,
            ):
                valid_shop = shop
                break

        if not valid_shop:
            return {
                "status": "error",
                "message": "You are not within any assigned dealership’s geofence.",
            }

        # Fetch Most Recent Log For Employee
        last_punch = session.exec(
            select(TimeLog)
            .where(TimeLog.employee_id == employee_id)
            .order_by(TimeLog.timestamp.desc())
        ).first()

        # Punch Order Validation
        if last_punch:

            # If you're last punch equals this attempted punch
            if last_punch.punch_type == punch_type:

                # Return Error Response Code
                return {
                    "status": "error",
                    "message": f"Cannot {punch_type.value.replace('_', ' ')} twice in a row.",
                }
        else:
            # No Previous Punch Exists; There Must CLOCK_IN First
            if punch_type == PunchType.CLOCK_OUT:

                # Return Error Response Code
                return {
                    "status": "error",
                    "message": "Cannot clock out before clocking in.",
                }

        # Creates a TimeLog Object w/ Data From Endpoint Defined In models/TimeLog
        punch = TimeLog(
            employee_id=employee_id,
            punch_type=punch_type,
            latitude=latitude,
            longitude=longitude,
            timestamp=datetime.now(timezone.utc),
        )

        # Append New Punch to List of Changes
        session.add(punch)

        # Commits Changse to DB
        session.commit()

        # Refereshes Object W/ Auto Generated Fields
        session.refresh(punch)

        # JSON Response back to Call
        return {"status": "success", "data": punch}
