from fastapi import APIRouter, Depends, HTTPException, Header, status, File, UploadFile, Form
from fastapi.responses import JSONResponse
from typing import Annotated
from core.firebase import db
from core.deps import get_current_user, get_current_user_basic_auth
from datetime import datetime,timezone
from google.cloud.firestore_v1.transforms import ArrayUnion
from google.cloud.firestore_v1.base_query import FieldFilter
from utils.storage import validate_device_id_format, extract_phone_from_device_id
from utils.database_storage import store_device_photo_in_db

router = APIRouter()


@router.post("/register")
async def register_device(
    current_user: Annotated[dict, Depends(get_current_user_basic_auth)],
    device_id: Annotated[str, Form()],
    id_photo: Annotated[UploadFile, File(description="Photo of user's ID document")],
):
    """
    Register a new device for the user.
    
    Requirements:
    - device_id: Format should be phone_number + device_type (e.g., "4435713151iphone")
    - id_photo: Photo of user's ID document (JPEG, PNG, WEBP, max 5MB)
    """

    # Extract User's ID
    user_uid = current_user.get("uid")

    # Ensure Valid User In Our Firestore DB
    if not user_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )

    # Validate device ID format
    if not validate_device_id_format(device_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device ID format. Expected format: phone_number + device_type (e.g., '4435713151iphone')",
        )

    # Extract phone number for validation
    phone_number = extract_phone_from_device_id(device_id)
    if not phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract valid phone number from device ID.",
        )

    # Validate ID photo file
    if not id_photo or not id_photo.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID photo is required for device registration.",
        )

    try:
        print(f"🔄 DEVICE REGISTRATION: user_uid={user_uid}, device_id={device_id}")

        # Pull Collection W/ All Requests
        request_ref = db.collection("deviceRequests")

        # pull all exisiting requests
        existing_query = (
            request_ref.where(filter=FieldFilter("userId", "==", user_uid))
            .where(filter=FieldFilter("deviceId", "==", device_id))
            .where(filter=FieldFilter("status", "==", "pending"))
            .limit(1)
        )
        
        # Execute query     
        users_existing_requests = list(existing_query.stream()) 
        print(f"📋 Found {len(users_existing_requests)} existing pending requests for this device")

        # Inform User They Have a Pending Request Already For This Device
        if len(users_existing_requests) > 0:
            print(f"⚠️ EARLY RETURN: Existing pending request found - not uploading file")
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "pending",
                    "message": "Device registration request is already pending approval.",
                }
            )

        print(f"✅ No existing requests found - proceeding with upload")
        
        # Store ID photo in database (more secure than Firebase Storage)
        try:
            photo_id = await store_device_photo_in_db(id_photo, user_uid, device_id)
            print(f"✅ Photo stored in database with ID: {photo_id}")
        except HTTPException as upload_error:
            # Re-raise upload errors directly
            raise upload_error
        except Exception as e:
            print(f"Unexpected error storing ID photo in database: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store ID photo. Please try again.",
            )
        
        # Add to Firestore Collection with photo_id instead of photo_url
        request_doc_ref, write_result = request_ref.add({
            "userId" : user_uid,
            "userEmail" : current_user.get("email"),
            "userName" : current_user.get("name"),
            "deviceId" : device_id,
            "phoneNumber" : phone_number,  # Extracted phone number
            "photoId" : photo_id,  # Database photo ID (secure internal reference)
            "status" : "pending",
            "requestedAt" : datetime.now(timezone.utc)
        })
        
         # Return a success response indicating submission using 202 Accepted
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "submitted", 
                "message": "Device registration request submitted for approval.",
                "device_id": device_id,
                "phone_number": phone_number
            }
        )
        

    except Exception as e:
        # Log the exception e for debugging purposes
        print(f"Error registering device for user {user_uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not register device.",
        )
