import os
from fastapi import HTTPException, UploadFile
from sqlmodel import Session, select
from models.device_photo import DevicePhoto
from db.session import engine
from datetime import datetime
from typing import Optional
import base64

async def store_device_photo_in_db(
    file: UploadFile, 
    user_id: str, 
    device_id: str
) -> int:
    """
    Store device registration photo directly in PostgreSQL database.
    Returns the photo ID for future reference.
    """
    
    print(f"✅ DATABASE UPLOAD STARTED: file={file.filename}, user_id={user_id}, device_id={device_id}")
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        print(f"❌ UPLOAD FAILED: Invalid file type {file.content_type}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        print(f"✅ File type validated: {file.content_type}")
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        print(f"✅ File content read: {file_size} bytes")
        
        # Create new photo record
        device_photo = DevicePhoto(
            user_id=user_id,
            device_id=device_id,
            filename=file.filename or "unknown.jpg",
            content_type=file.content_type,
            file_size=file_size,
            image_data=file_content
        )
        
        # Save to database
        with Session(engine) as session:
            session.add(device_photo)
            session.commit()
            session.refresh(device_photo)
            
            photo_id = device_photo.id
            print(f"✅ Photo stored in database with ID: {photo_id}")
            
            return photo_id
        
    except Exception as e:
        print(f"❌ Database storage error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to store photo in database"
        )

async def get_device_photo_from_db(photo_id: int) -> Optional[DevicePhoto]:
    """
    Retrieve a device photo from the database by ID.
    """
    try:
        with Session(engine) as session:
            statement = select(DevicePhoto).where(DevicePhoto.id == photo_id)
            photo = session.exec(statement).first()
            return photo
    except Exception as e:
        print(f"❌ Error retrieving photo {photo_id}: {e}")
        return None

async def get_device_photo_by_user_device(user_id: str, device_id: str) -> Optional[DevicePhoto]:
    """
    Get the most recent device photo for a specific user and device.
    """
    try:
        with Session(engine) as session:
            statement = (
                select(DevicePhoto)
                .where(DevicePhoto.user_id == user_id)
                .where(DevicePhoto.device_id == device_id)
                .order_by(DevicePhoto.uploaded_at.desc())
            )
            photo = session.exec(statement).first()
            return photo
    except Exception as e:
        print(f"❌ Error retrieving photo for user {user_id}, device {device_id}: {e}")
        return None

async def delete_device_photo_from_db(photo_id: int) -> bool:
    """
    Delete a device photo from the database.
    """
    try:
        with Session(engine) as session:
            statement = select(DevicePhoto).where(DevicePhoto.id == photo_id)
            photo = session.exec(statement).first()
            
            if not photo:
                return False
                
            session.delete(photo)
            session.commit()
            print(f"✅ Photo {photo_id} deleted from database")
            return True
            
    except Exception as e:
        print(f"❌ Error deleting photo {photo_id}: {e}")
        return False

def photo_to_base64(photo: DevicePhoto) -> str:
    """
    Convert stored photo to base64 string for API responses.
    """
    encoded = base64.b64encode(photo.image_data).decode('utf-8')
    return f"data:{photo.content_type};base64,{encoded}" 