import uuid
from typing import Optional
from fastapi import HTTPException, UploadFile
from google.cloud import storage
import os
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import storage as admin_storage
import asyncio

# Initialize Firebase Storage client
def get_storage_client():
    """Initialize and return Google Cloud Storage client"""
    return storage.Client()

def get_storage_client_for_signing():
    """
    Initialize and return a Google Cloud Storage client capable of generating signed URLs.
    This tries different authentication methods to ensure signed URL generation works.
    """
    try:
        # First, try to use service account key file if available
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path and os.path.exists(credentials_path):
            return storage.Client.from_service_account_json(credentials_path)
        
        # Fallback to default client (might work in some environments)
        return storage.Client()
        
    except Exception as e:
        print(f"Warning: Could not create storage client for signing: {e}")
        # Return None to indicate that signed URL generation might not work
        return None

async def generate_secure_photo_url(object_path: str, expiration_minutes: int = 15) -> str:
    """
    Generate a secure URL for accessing a photo using Firebase Admin SDK.
    Assumes Firebase Admin SDK is initialized with credentials that can sign URLs.
    
    Args:
        object_path: The GCS object path
        expiration_minutes: How long the URL should be valid (in minutes)
        
    Returns:
        str: A secure URL for accessing the photo
    """
    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "minordetails-1aff3.appspot.com")
    
    try:
        # Get bucket through Firebase Admin SDK
        bucket = admin_storage.bucket(bucket_name)
        blob = bucket.blob(object_path)
        
        if not await asyncio.to_thread(blob.exists):
             raise HTTPException(
                status_code=404,
                detail=f"ID photo not found at path: {object_path}"
            )
            
        # Generate signed URL using Firebase Admin SDK
        signed_url = await asyncio.to_thread(
            blob.generate_signed_url,
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
            version="v4" # v4 is generally recommended
        )
        return signed_url
        
    except HTTPException as http_exc: # Re-raise known HTTP exceptions
        raise http_exc
    except Exception as e:
        print(f"Firebase Admin SDK URL generation failed for {object_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Unable to generate secure access URL for the requested photo. Check server logs and Firebase/GCS permissions."
        )

async def upload_id_photo(
    file: UploadFile, 
    user_id: str, 
    device_id: str
) -> str:
    """
    Upload ID photo to Firebase Storage and return the public URL
    
    Args:
        file: The uploaded file
        user_id: User's UID for organizing files
        device_id: Device ID for file naming
        
    Returns:
        str: Public URL of the uploaded file
    """
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    # Validate file size (5MB limit)
    max_size = 5 * 1024 * 1024  # 5MB in bytes
    file_content = await file.read()
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds 5MB limit"
        )
    
    try:
        # Initialize storage client
        client = get_storage_client()
        
        # Get bucket (replace with your Firebase Storage bucket name)
        # You'll need to set this as an environment variable or config
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "minordetails-1aff3.appspot.com")
        bucket = client.bucket(bucket_name)
        
        # Generate unique filename using the new base path
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        base_path = "employee_device_registration_identification" # <-- New base path
        filename = f"{base_path}/{user_id}/{device_id}_{timestamp}.{file_extension}"
        
        # Create blob and upload
        blob = bucket.blob(filename)
        blob.upload_from_string(file_content, content_type=file.content_type)
        
        # The blob is no longer made public here.
        # Access is controlled by Firebase Storage Security Rules.
        # Owners will access via Firebase SDK or Signed URLs generated by the backend.
        
        # Return the object path (filename) within the bucket.
        # This path will be used to generate signed URLs when access is needed.
        return filename
        
    except Exception as e:
        print(f"Error uploading file: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to upload ID photo"
        )

def validate_device_id_format(device_id: str) -> bool:
    """
    Validate that device_id follows the format: phone_number + device_type
    Example: 4435713151iphone, 5551234567android
    
    Args:
        device_id: The device ID to validate
        
    Returns:
        bool: True if format is valid, False otherwise
    """
    if not device_id or len(device_id) < 11:  # Minimum: 10-digit phone + 1 char device type
        return False
    
    # Check if it ends with known device types
    valid_device_types = ['iphone', 'android', 'ios', 'web']
    
    for device_type in valid_device_types:
        if device_id.lower().endswith(device_type):
            # Extract phone number part
            phone_part = device_id[:-len(device_type)]
            # Check if phone part is all digits and reasonable length (10-15 digits)
            if phone_part.isdigit() and 10 <= len(phone_part) <= 15:
                return True
    
    return False

def extract_phone_from_device_id(device_id: str) -> Optional[str]:
    """
    Extract phone number from device_id
    
    Args:
        device_id: The device ID in format phone_number + device_type
        
    Returns:
        str: Phone number if valid format, None otherwise
    """
    if not validate_device_id_format(device_id):
        return None
    
    valid_device_types = ['iphone', 'android', 'ios', 'web']
    
    for device_type in valid_device_types:
        if device_id.lower().endswith(device_type):
            return device_id[:-len(device_type)]
    
    return None 