from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, field_serializer
from sqlmodel import Session, select

from core.deps import require_admin_role
from db.session import get_session
from models.signature_photo import SignaturePhoto
from models.time_log import TimeLog
from utils.database_storage import (
    get_signature_photo_from_db,
    signature_photo_to_base64,
)
from utils.datetime_helpers import format_utc_datetime

router = APIRouter()

# --- Response Models ---


class SignaturePhotoInfo(BaseModel):
    id: int
    employee_id: str
    time_log_id: int | None
    filename: str
    content_type: str
    file_size: int
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime) -> str:
        """Ensure created_at is formatted as UTC with Z suffix"""
        result = format_utc_datetime(dt)
        return result if result is not None else dt.isoformat()


# --- API Endpoints ---


@router.get("/signature-photo/{photo_id}")
async def get_signature_photo(
    photo_id: int,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    """
    🔒 SECURE ADMIN ENDPOINT: View signature photo by ID.

    Security Features:
    - Requires admin authentication
    - Photos stored securely in database
    - All access logged
    """
    try:
        # Retrieve photo from secure database storage
        photo = await get_signature_photo_from_db(photo_id)
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signature photo {photo_id} not found",
            )

        # Log secure access
        admin_email = admin_user.get("email", "unknown")
        print(
            f"🔒 SECURE SIGNATURE ACCESS: Admin {admin_email} viewing signature photo {photo_id} for employee {photo.employee_id}"
        )

        # Return photo with security headers
        return Response(
            content=photo.image_data,
            media_type=photo.content_type,
            headers={
                "Content-Disposition": f"inline; filename={photo.filename}",
                "X-Photo-Info": f"ID: {photo.id}, Employee: {photo.employee_id}, TimeLog: {photo.time_log_id}",
                "X-Security-Level": "admin-only",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving secure signature photo {photo_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve signature photo",
        )


@router.get("/signature-photo-base64/{photo_id}")
async def get_signature_photo_base64(
    photo_id: int,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    """
    🔒 SECURE ADMIN ENDPOINT: Get signature photo as base64.
    """
    try:
        photo = await get_signature_photo_from_db(photo_id)
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signature photo {photo_id} not found",
            )

        # Log secure access
        admin_email = admin_user.get("email", "unknown")
        print(
            f"🔒 SECURE SIGNATURE ACCESS (base64): Admin {admin_email} viewing signature photo {photo_id}"
        )

        base64_data = signature_photo_to_base64(photo)

        return {
            "photo_id": photo.id,
            "employee_id": photo.employee_id,
            "time_log_id": photo.time_log_id,
            "filename": photo.filename,
            "content_type": photo.content_type,
            "file_size": photo.file_size,
            "created_at": photo.created_at,
            "base64_data": base64_data,
            "security_level": "admin-only",
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving secure base64 signature photo {photo_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve signature photo",
        )


@router.get(
    "/employee/{employee_id}/signatures", response_model=List[SignaturePhotoInfo]
)
async def get_employee_signatures(
    employee_id: str,
    admin_user: Annotated[dict, Depends(require_admin_role)],
    session: Session = Depends(get_session),
    limit: int = 20,
):
    """Get signature photos for a specific employee."""

    signatures = session.exec(
        select(SignaturePhoto)
        .where(SignaturePhoto.employee_id == employee_id)
        .order_by(SignaturePhoto.created_at.desc())
        .limit(limit)
    ).all()

    return [
        SignaturePhotoInfo(
            id=sig.id,
            employee_id=sig.employee_id,
            time_log_id=sig.time_log_id,
            filename=sig.filename,
            content_type=sig.content_type,
            file_size=sig.file_size,
            created_at=sig.created_at,
        )
        for sig in signatures
    ]
