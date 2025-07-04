import os
import asyncio
from fastapi import HTTPException, UploadFile
from firebase_admin import storage as admin_storage
from google.cloud import storage as gcs_storage
from datetime import datetime
import uuid
from typing import Optional
from google.cloud import storage
from datetime import timezone, timedelta
import firebase_admin

# Initialize Firebase Storage client
def get_storage_client():
    """Initialize and return Google Cloud Storage client"""
    return storage.Client()

async def upload_id_photo(
    file: UploadFile, 
    user_id: str, 
    device_id: str
) -> str:
    """
    Upload ID photo to Firebase Storage and return the GCS object path,
    preventing public download tokens by setting metadata during server-side upload.
    """
    
    print(f"✅ UPLOAD STARTED (v3.2 - Admin SDK Upload + Admin SDK Token Nullification): file={file.filename}, user_id={user_id}, device_id={device_id}")
    
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        print(f"❌ UPLOAD FAILED: Invalid file type {file.content_type}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        print(f"✅ File type validated: {file.content_type}")
        file_content = await file.read()
        print(f"✅ File content read: {len(file_content)} bytes")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"{device_id}android_{timestamp}.{file_extension}" # Ensure 'android' is dynamic if needed
        object_path = f"employee_device_registration_identification/{user_id}/{filename}"
        print(f"✅ Object path created: {object_path}")
        
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "minordetails-1aff3.appspot.com")
        
        # Step 1: Upload using Firebase Admin SDK (as it's convenient)
        admin_bucket = admin_storage.bucket(bucket_name)
        admin_blob = admin_bucket.blob(object_path)
        
        # We won't try to set firebaseStorageDownloadTokens here with Admin SDK,
        # as it seems ineffective for actual prevention in our Python context.
        admin_blob.upload_from_string(
            file_content, 
            content_type=file.content_type
        )
        print(f"✅ Initial file upload via Firebase Admin SDK complete: {object_path}")

        # Step 2: Forcefully nullify the token using Firebase Admin SDK blob.patch.
        # This mirrors the successful approach from remove_download_tokens_from_file.
        print(f"🔄 Attempting forceful token nullification via Firebase Admin SDK patch...")
        
        # Set metadata with firebaseStorageDownloadTokens = None
        admin_blob.metadata = {'firebaseStorageDownloadTokens': None}
        
        # Then patch to apply the metadata change
        await asyncio.to_thread(admin_blob.patch)
        
        print(f"✅ Firebase Admin SDK metadata patch submitted to nullify token.")

        # Step 3: Verify metadata using the same admin_blob
        await asyncio.to_thread(admin_blob.reload)
        final_metadata = admin_blob.metadata or {}
        print(f"🔍 Final metadata after Admin SDK patch & reload: {final_metadata}")

        if 'firebaseStorageDownloadTokens' in final_metadata and final_metadata['firebaseStorageDownloadTokens']:
            print(f"⚠️ WARNING: Token still present and non-empty after Admin SDK patch: '{final_metadata['firebaseStorageDownloadTokens']}'")
        elif 'firebaseStorageDownloadTokens' in final_metadata and (final_metadata['firebaseStorageDownloadTokens'] is None or final_metadata['firebaseStorageDownloadTokens'] == ''):
            print(f"✅ Token field present but nullified (None or empty), as intended, after Admin SDK patch.")
        elif 'firebaseStorageDownloadTokens' not in final_metadata:
            print(f"✅ Token field ABSENT, as intended, after Admin SDK patch.")
        else: # Should not happen if logic above is correct
            print(f"🤔 Unexpected token state: {final_metadata.get('firebaseStorageDownloadTokens')}")
            
        print(f"🎉 UPLOAD COMPLETE (v3.2): {object_path}")
        return object_path
        
    except Exception as e:
        print(f"❌ UPLOAD ERROR (v3.2): {str(e)}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not upload file (v3.2): {str(e)}"
        )

async def upload_receipt_image(
    file: UploadFile, 
    user_id: str
) -> str:
    """
    Upload a transaction receipt image to Firebase Storage.
    """
    
    print(f"✅ RECEIPT UPLOAD STARTED: file={file.filename}, user_id={user_id}")
    
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type for receipt. Allowed types: {', '.join(allowed_types)}"
        )
    
    try:
        file_content = await file.read()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        unique_id = uuid.uuid4().hex[:6]
        filename = f"{timestamp}_{unique_id}.{file_extension}"
        object_path = f"company_card_receipts/{user_id}/{filename}"
        
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "minordetails-1aff3.appspot.com")
        
        admin_bucket = admin_storage.bucket(bucket_name)
        admin_blob = admin_bucket.blob(object_path)
        
        admin_blob.upload_from_string(
            file_content, 
            content_type=file.content_type
        )
        
        # Make the file secure by nullifying any potential download tokens
        admin_blob.metadata = {'firebaseStorageDownloadTokens': None}
        await asyncio.to_thread(admin_blob.patch)
        
        print(f"🎉 RECEIPT UPLOAD COMPLETE: {object_path}")
        return object_path
        
    except Exception as e:
        print(f"❌ RECEIPT UPLOAD ERROR: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Could not upload receipt image: {str(e)}"
        )

async def debug_file_metadata(object_path: str) -> dict:
    """
    Debug function to inspect file metadata and see if download tokens exist.
    
    Args:
        object_path: The GCS object path
        
    Returns:
        dict: File metadata information
    """
    try:
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "minordetails-1aff3.appspot.com")
        bucket = admin_storage.bucket(bucket_name)
        blob = bucket.blob(object_path)
        
        # Check if file exists
        if not await asyncio.to_thread(blob.exists):
            return {"error": f"File not found: {object_path}"}
        
        # Reload metadata to get fresh data
        await asyncio.to_thread(blob.reload)
        
        metadata = blob.metadata or {}
        
        return {
            "object_path": object_path,
            "exists": True,
            "metadata": metadata,
            "download_tokens": metadata.get('firebaseStorageDownloadTokens'),
            "content_type": blob.content_type,
            "size": blob.size,
            "time_created": blob.time_created.isoformat() if blob.time_created else None
        }
        
    except Exception as e:
        return {"error": f"Error inspecting {object_path}: {e}"}

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

async def remove_download_tokens_from_file(object_path: str) -> bool:
    """
    Remove download tokens from an existing file in Firebase Storage.
    This will invalidate any existing public URLs with tokens.
    
    Args:
        object_path: The GCS object path (e.g., 'employee_device_registration_identification/user_id/file.jpg')
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "minordetails-1aff3.appspot.com")
        bucket = admin_storage.bucket(bucket_name)
        blob = bucket.blob(object_path)
        
        # Check if file exists
        if not await asyncio.to_thread(blob.exists):
            print(f"File not found: {object_path}")
            return False
        
        # Remove download tokens completely by setting to None
        # This is the proper way to remove Firebase download tokens
        blob.metadata = {'firebaseStorageDownloadTokens': None}
        await asyncio.to_thread(blob.patch)
        
        print(f"Successfully removed download tokens from: {object_path}")
        return True
        
    except Exception as e:
        print(f"Error removing download tokens from {object_path}: {e}")
        return False 