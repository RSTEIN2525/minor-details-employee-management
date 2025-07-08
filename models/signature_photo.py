from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Index, SQLModel


class SignaturePhoto(SQLModel, table=True):
    __tablename__ = "signature_photos"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Link to employee who created the signature
    employee_id: str

    # Link to the specific time log entry (punch) this signature belongs to
    # This will be set when the signature is used for a clock-out
    time_log_id: Optional[int] = Field(default=None, foreign_key="time_log.id")

    # File information
    filename: str
    content_type: str  # e.g., "image/jpeg", "image/png"
    file_size: int  # Size in bytes

    # Binary data of the signature image
    image_data: bytes  # This will store the actual signature image as binary data

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Explicit indexes for performance
    __table_args__ = (
        Index("ix_signature_photos_employee_id", "employee_id"),
        Index("ix_signature_photos_time_log_id", "time_log_id"),
        Index("ix_signature_photos_created_at", "created_at"),
        # Composite index for employee + time queries
        Index("ix_signature_photos_employee_created", "employee_id", "created_at"),
    )
