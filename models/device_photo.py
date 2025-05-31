from sqlmodel import SQLModel, Field, Index
from typing import Optional
from datetime import datetime, timezone

class DevicePhoto(SQLModel, table=True):
    __tablename__ = "device_photos"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Link to user and device (indexes defined in __table_args__ below)
    user_id: str
    device_id: str
    
    # File information
    filename: str
    content_type: str  # e.g., "image/jpeg", "image/png"
    file_size: int     # Size in bytes
    
    # Binary data of the image
    image_data: bytes  # This will store the actual image file as binary data
    
    # Metadata
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Explicit indexes to avoid duplicates
    __table_args__ = (
        Index("ix_device_photos_user_id", "user_id"),
        Index("ix_device_photos_device_id", "device_id"),
        Index("ix_device_photos_user_device", "user_id", "device_id"),  # Composite index
    ) 