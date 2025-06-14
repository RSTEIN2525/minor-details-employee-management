from sqlmodel import Session, select
from datetime import datetime, timezone
from models.time_log import TimeLog, PunchType
from utils.geofence import is_within_radius
from models.shop import Shop
from pydantic import TypeAdapter
from fastapi import HTTPException, status
from typing import Optional


class PunchService:

    @staticmethod
    def validate_and_save(
        employee_id: str,
        dealership_id: list[str],
        punch_type: PunchType,
        latitude: float,
        longitude: float,
        session: Session,
        injured_at_work: Optional[bool] = None,
        safety_signature: Optional[str] = None,
    ):

        # 0) Must supply location
        if latitude is None or longitude is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Location required to punch.",
            )

        # Validate injury reporting fields for clockout
        if punch_type == PunchType.CLOCK_OUT:
            if injured_at_work is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Injury status is required for clock out.",
                )
            if safety_signature is None or safety_signature.strip() == "":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Safety signature (initials) is required for clock out.",
                )
            if len(safety_signature.strip()) > 10:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Safety signature must be 10 characters or less.",
                )

        # 1) Check each shop the user belongs to
        valid_shop = None
        for shop_id in dealership_id:
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You must be within the geofence of an assigned dealership to punch. Location: ({latitude},{longitude})",
            )

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
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,  # 409 Conflict is suitable for state errors
                    detail=f"Cannot {punch_type.value.replace('_', ' ')} twice in a row.",
                )
        else:
            # No Previous Punch Exists; There Must CLOCK_IN First
            if punch_type == PunchType.CLOCK_OUT:

                # Return Error Response Code
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,  # 409 Conflict
                    detail="Cannot clock out before clocking in.",
                )

        # Creates a TimeLog Object w/ Data From Endpoint Defined In models/TimeLog
        punch = TimeLog(
            employee_id=employee_id,
            dealership_id=valid_shop.id,
            punch_type=punch_type,
            latitude=latitude,
            longitude=longitude,
            timestamp=datetime.now(timezone.utc),
            injured_at_work=injured_at_work if punch_type == PunchType.CLOCK_OUT else None,
            safety_signature=safety_signature.strip() if punch_type == PunchType.CLOCK_OUT and safety_signature else None,
        )

        # Append New Punch to List of Changes
        session.add(punch)

        # Commits Changse to DB
        session.commit()

        # Refereshes Object W/ Auto Generated Fields
        session.refresh(punch)

        # JSON Response back to Call
        return {"status": "success", "data": punch}
