from fastapi import APIRouter, Depends, HTTPException, Header, status, File, UploadFile, Form
from fastapi.responses import JSONResponse
from typing import Annotated
from core.firebase import db
from core.deps import get_current_user, get_current_user_basic_auth
from datetime import datetime,timezone
from google.cloud.firestore_v1.transforms import ArrayUnion
from utils.storage import upload_id_photo, validate_device_id_format, extract_phone_from_device_id

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

        # Pull Collection W/ All Requests
        request_ref = db.collection("deviceRequests")

        # pull all exisiting requests
        existing_query = (
            request_ref.where("userId", "==", user_uid)
            .where("deviceId", "==", device_id)
            .where("status", "==", "pending")
            .limit(1)
        )
        
        # Execute query     
        users_existing_requests = list(existing_query.stream()) 

        # Inform User They Have a Pending Request Already For This Device
        if len(users_existing_requests) > 0:
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "status": "pending",
                    "message": "Device registration request is already pending approval.",
                },
            )

        # Upload ID photo to Firebase Storage
        try:
            photo_url = await upload_id_photo(id_photo, user_uid, device_id)
        except HTTPException as upload_error:
            # Re-raise upload errors directly
            raise upload_error
        except Exception as e:
            print(f"Unexpected error uploading ID photo: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload ID photo. Please try again.",
            )
        
        # Add to Firestore Collection with additional fields
        request_doc_ref, write_result = request_ref.add({
            "userId" : user_uid,
            "userEmail" : current_user.get("email"),
            "userName" : current_user.get("name"),
            "deviceId" : device_id,
            "phoneNumber" : phone_number,  # Extracted phone number
            "idPhotoUrl" : photo_url,  # URL to uploaded ID photo
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
