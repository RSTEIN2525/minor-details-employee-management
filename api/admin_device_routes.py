from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from typing import Annotated
from datetime import datetime, timezone, timedelta
from core.firebase import db
from google.cloud.firestore_v1.transforms import ArrayUnion, ArrayRemove
from google.cloud.firestore_v1.base_query import FieldFilter
from core.deps import require_admin_role, get_current_user_basic_auth
from pydantic import BaseModel, field_serializer
from typing import List
from google.cloud import storage
import os
from utils.storage import debug_file_metadata, remove_download_tokens_from_file
from utils.database_storage import get_device_photo_from_db, photo_to_base64
from utils.datetime_helpers import format_utc_datetime

router = APIRouter()


# Return Model For Device Enrichment Endpoint
class DeviceRequestHistory(BaseModel):
    id: str  # The request document ID
    userId: str
    userEmail: str | None
    userName: str | None
    deviceId: str
    phoneNumber: str | None  # Phone number extracted from device ID
    photoId: int | None  # Database photo ID (required for new system)
    status: str
    requestedAt: datetime | str | None
    processedAt: datetime | str | None
    processedByUid: str | None
    processedByEmail: str | None

    @field_serializer('requestedAt', 'processedAt')
    def serialize_timestamps(self, dt: datetime | str | None) -> str | None:
        """Ensure timestamps are formatted as UTC with Z suffix"""
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt  # Already a string
        return format_utc_datetime(dt)


# Return Model For User Device Registration Analytics Endpoint
class DeviceRequestSummary(BaseModel):
    totalRequests: int
    lastRequestedAt: datetime | str | None

    @field_serializer('lastRequestedAt')
    def serialize_last_requested_at(self, dt: datetime | str | None) -> str | None:
        """Ensure lastRequestedAt is formatted as UTC with Z suffix"""
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt  # Already a string
        return format_utc_datetime(dt)


@router.get("/pending")
async def list_pending_device_requests(
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    try:

        # Pull Collection
        request_ref = db.collection("deviceRequests")

        # Form Query
        request_query = request_ref.where(
            filter=FieldFilter("status", "==", "pending")
        ).order_by(
            "requestedAt", direction="ASCENDING"
        )  # Or DESCENDING
        # Pull Docx
        pending_requests = []

        for doc in request_query.stream():
            request_data = doc.to_dict()
            
            # Ensure essential fields are present and formatted for consistent API response
            processed_request = {
                "id": doc.id,
                "userId": request_data.get("userId"),
                "userEmail": request_data.get("userEmail"),
                "userName": request_data.get("userName"),
                "deviceId": request_data.get("deviceId"),
                "phoneNumber": request_data.get("phoneNumber"),
                "photoId": request_data.get("photoId"), # Ensure photoId is included, even if None
                "status": request_data.get("status", "pending"),
                "requestedAt": request_data.get("requestedAt"),
                "processedAt": request_data.get("processedAt"),
                "processedByUid": request_data.get("processedByUid"),
                "processedByEmail": request_data.get("processedByEmail"),
            }

            # Convert Timestamp For JSON Compatibility
            if isinstance(processed_request["requestedAt"], datetime):
                processed_request["requestedAt"] = processed_request["requestedAt"].isoformat()
            if isinstance(processed_request["processedAt"], datetime):
                 processed_request["processedAt"] = processed_request["processedAt"].isoformat()

            pending_requests.append(processed_request)

        return {"status": "success", "data": pending_requests}

    except Exception as e:
        print(f"Error fetching pending device requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve pending device requests.",
        )


@router.get("/approved")
async def list_approved_device_requests(
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    try:

        # Pull Collection
        request_ref = db.collection("deviceRequests")

        # Form Query
        request_query = (
            request_ref.where(filter=FieldFilter("status", "==", "approved"))
            .order_by("processedAt", direction="DESCENDING")
            .limit(25)
        )
        # Pull Docx
        approved_requests = []

        for doc in request_query.stream():
            request_data = doc.to_dict()

            processed_request = {
                "id": doc.id,
                "userId": request_data.get("userId"),
                "userEmail": request_data.get("userEmail"),
                "userName": request_data.get("userName"),
                "deviceId": request_data.get("deviceId"),
                "phoneNumber": request_data.get("phoneNumber"),
                "photoId": request_data.get("photoId"), # Ensure photoId is included, even if None
                "status": request_data.get("status", "approved"),
                "requestedAt": request_data.get("requestedAt"),
                "processedAt": request_data.get("processedAt"),
                "processedByUid": request_data.get("processedByUid"),
                "processedByEmail": request_data.get("processedByEmail"),
            }

            if isinstance(processed_request["requestedAt"], datetime):
                processed_request["requestedAt"] = processed_request["requestedAt"].isoformat()
            if isinstance(processed_request["processedAt"], datetime):
                processed_request["processedAt"] = processed_request["processedAt"].isoformat()

            approved_requests.append(processed_request)

        return {"status": "success", "data": approved_requests}

    except Exception as e:
        print(f"Error fetching approved device requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve approved device requests.",
        )


@router.get("/rejected")
async def list_rejected_device_requests(
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    try:

        # Pull Collection
        request_ref = db.collection("deviceRequests")

        # Form Query
        request_query = (
            request_ref.where(filter=FieldFilter("status", "==", "rejected"))
            .order_by("processedAt", direction="DESCENDING")
            .limit(25)
        )
        # Pull Docx
        rejected_requests = []

        for doc in request_query.stream():
            request_data = doc.to_dict()

            processed_request = {
                "id": doc.id,
                "userId": request_data.get("userId"),
                "userEmail": request_data.get("userEmail"),
                "userName": request_data.get("userName"),
                "deviceId": request_data.get("deviceId"),
                "phoneNumber": request_data.get("phoneNumber"),
                "photoId": request_data.get("photoId"), # Ensure photoId is included, even if None
                "status": request_data.get("status", "rejected"),
                "requestedAt": request_data.get("requestedAt"),
                "processedAt": request_data.get("processedAt"),
                "processedByUid": request_data.get("processedByUid"),
                "processedByEmail": request_data.get("processedByEmail"),
            }

            if isinstance(processed_request["requestedAt"], datetime):
                processed_request["requestedAt"] = processed_request["requestedAt"].isoformat()
            if isinstance(processed_request["processedAt"], datetime):
                processed_request["processedAt"] = processed_request["processedAt"].isoformat()

            rejected_requests.append(processed_request)

        return {"status": "success", "data": rejected_requests}

    except Exception as e:
        print(f"Error fetching rejected device requests: {e}") 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve rejected device requests.", 
        )


@router.get("/users/{user_id}/devices")
async def get_user_approved_devices(
    user_id: str, admin_user: Annotated[dict, Depends(require_admin_role)]
):
    try:

        # Reference To Document
        user_ref = db.collection("users").document(user_id)

        # Fetch Document Snapshot
        user_doc = user_ref.get()

        # Check If User Doc Exists
        if not user_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )

        # Turn to Dictionary
        profile = user_doc.to_dict()

        # Extract List of Devices On Their Profile
        devices_list = profile.get("devices", [])

        # Make Sure It's Actually a List
        if not isinstance(devices_list, list):
            devices_list = []

        return {"status": "success", "user_id": user_id, "data": devices_list}
    except Exception as e:
        print(f"Error fetching devices for user {user_id}: {e}")
        # Check if it was an HTTPException already (like 404), re-raise if so
        if isinstance(e, HTTPException):
            raise e
        # Otherwise, raise a generic server error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve devices for the user.",
        )


@router.delete("/users/{user_id}/devices/{device_id}")
async def delete_user_device(
    user_id: str,
    device_id: str,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):

    try:
        # Get reference to the user's document
        user_ref = db.collection("users").document(user_id)

        # Check if user exists first
        user_doc = user_ref.get()
        if not user_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found. Cannot remove device.",
            )

        # Use ArrayRemove to remove the specified device ID from the 'devices' array
        user_ref.update({"devices": ArrayRemove([device_id])})

        try:

            # Pull Reference Device Requests Collection
            requests_ref = db.collection("deviceRequests")

            # Pull Most Recent Docx W/ Matching Device ID
            request_query = (
                requests_ref.where(filter=FieldFilter("deviceId", "==", device_id))
                .order_by("requestedAt", direction="DESCENDING")
                .limit(1)
            )

            # Execute the query to get the snapshot(s)
            results = list(request_query.stream())

            # Check if a corresponding request document was found
            if results:

                # Get the snapshot of the first (and only) result
                request_snapshot = results[0]

                # Get the DocumentReference from the snapshot
                specific_request_ref = request_snapshot.reference

                # Now, update THIS specific document reference
                specific_request_ref.update(
                    {
                        "status": "deleted",  # Mark as deleted by admin
                        "processedAt": datetime.now(
                            timezone.utc
                        ),  # Use processedAt for consistency
                        "processedByUid": admin_user.get("uid"),
                        "processedByEmail": admin_user.get("email"),
                    }
                )
            else:
                # It's okay if no matching request is found (maybe it was old/purged)
                print(
                    f"No corresponding device request found for deviceId {device_id} to mark as 'deleted'."
                )

        except Exception as req_update_ex:
            # Log if updating the request fails, but don't stop the process
            print(
                f"Warning: Failed to update status for device request matching {device_id}: {req_update_ex}"
            )

        return {
            "status": "success",
            "message": f"Device {device_id} successfully removed from user {user_id}.",
        }

    except Exception as e:
        print(f"Error removing device {device_id} for user {user_id}: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not remove device for the user.",
        )


@router.post("/{request_id}/approve")
async def approve_device_request(
    request_id: str,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    try:

        # Get reference to the request document
        request_ref = db.collection("deviceRequests").document(request_id)

        # Fetch the request document snapshot
        request_doc = request_ref.get()

        # Check If Docx Actually Exists
        if not request_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device Request {request_id} Does Not Exist",
            )

        # Extract Data from Docx
        request_data = request_doc.to_dict()

        # Ensure It's Actually Pending
        if request_data.get("status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Request is not pending (current status: {request_data.get('status')}).",
            )

        # Pull User & Device Information
        user_id = request_data.get("userId")
        device_id = request_data.get("deviceId")

        # Check User & Device ID Exist
        if not user_id or not device_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request document is missing required user or device ID.",
            )

        # Get User Doc
        user_ref = db.collection("users").document(user_id)

        # Add the device_id to the USER's 'devices' array
        user_ref.update({"devices": ArrayUnion([device_id])})

        # Update Request
        request_ref.update(
            {
                "status": "approved",  # Correct status
                "processedAt": datetime.now(timezone.utc),
                "processedByUid": admin_user.get("uid"),
                "processedByEmail": admin_user.get("email"),
            }
        )

        # Return Success Message
        return {"status": "success", "message": "Device request approved successfully."}

    except Exception as e:
        print(f"Error approving device request {request_id}: {e}")
        # Check if it was an HTTPException already, re-raise if so
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not approve device request.",
        )


@router.post("/{request_id}/reject")
async def reject_device_request(
    request_id: str, admin_user: Annotated[dict, Depends(require_admin_role)]
):

    try:

        # Pull Doc Reference
        request_ref = db.collection("deviceRequests").document(request_id)

        # Pull Actual Doc
        request_doc = request_ref.get()

        # Check If Docx Actually Exists
        if not request_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device Request {request_id} Does Not Exist",
            )

        # Extract Data From Docx
        request_data = request_doc.to_dict()

        # Pull User Data
        user_id = request_data.get("userId")
        device_id = request_data.get("deviceId")

        # Check User & Device ID Exist
        if not user_id or not device_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request document is missing required user or device ID.",
            )

        # Update Docx
        request_ref.update(
            {
                "status": "rejected",
                "processedAt": datetime.now(timezone.utc),
                "processedByUid": admin_user.get("uid"),
                "processedByEmail": admin_user.get("email"),
            }
        )

        # Inform of Successful Request
        return {"status": "success", "message": "Device request rejected successfully."}

    except Exception as e:
        print(f"Error rejecting device request {request_id}: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not reject device request.",
        )


@router.get("/devices/{device_id}/get-info", response_model=DeviceRequestHistory | None)
async def get_latest_device_request_info(  # Renamed for clarity
    device_id: str,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):

    try:
        requests_ref = db.collection("deviceRequests")

        # Query for the single most recent request based on requestedAt
        requests_query = (
            requests_ref.where(filter=FieldFilter("deviceId", "==", device_id))
            .order_by("requestedAt", direction="DESCENDING")
            .limit(1)
        )

        # Execute the query and get results (will be a list with 0 or 1 item)
        results = list(requests_query.stream())

        # Check if a document was found
        if not results:
            # Option 1: Return 404 Not Found (Recommended)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No request history found for device ID {device_id}",
            )

        # Get the single document snapshot from the list
        doc_snapshot = results[0]
        data = doc_snapshot.to_dict()

        # Format timestamps if they exist
        req_at = data.get("requestedAt")
        proc_at = data.get("processedAt")
        requested_at_str = req_at.isoformat() if isinstance(req_at, datetime) else None
        processed_at_str = (
            proc_at.isoformat() if isinstance(proc_at, datetime) else None
        )

        # Create the response object using the Pydantic model
        history_entry = DeviceRequestHistory(
            id=doc_snapshot.id,  # Use .id from the snapshot
            userId=data.get("userId", "N/A"),
            userEmail=data.get("userEmail"),
            userName=data.get("userName"),
            deviceId=data.get("deviceId", device_id),  # Should match input
            phoneNumber=data.get("phoneNumber"),
            photoId=data.get("photoId"),
            status=data.get("status", "unknown"),
            requestedAt=requested_at_str,
            processedAt=processed_at_str,
            processedByUid=data.get("processedByUid"),
            processedByEmail=data.get("processedByEmail"),
        )

        # Return the single object matching the response_model
        return history_entry

    except Exception as e:
        # Re-raise HTTPExceptions (like the 404) directly
        if isinstance(e, HTTPException):
            raise e
        # Log and raise 500 for other unexpected errors
        print(f"Error fetching latest request info for device {device_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve latest device request info.",
        )


@router.get("/users/{user_id}/device-request-summary", response_model=DeviceRequestSummary)
async def get_user_device_request_summary(
    user_id: str, admin_user: Annotated[dict, Depends(require_admin_role)]
):

    try:

        # Pulls Request Collection
        requests_ref = db.collection("deviceRequests")

        # Accumulators For Statistics
        total_requests = 0
        last_requested_at = None
        last_requested_at_str = None

        # More efficient than fetching all documents
        count_query = requests_ref.where(filter=FieldFilter("userId", "==", user_id))

        # Define the aggregation (count)
        aggregation_query = count_query.count(alias="total_count")

        # Execute the aggregation query
        count_results = aggregation_query.get()

        # Extract the count value safely
        if count_results and count_results[0] and count_results[0][0]:
            total_requests = count_results[0][0].value
        else:
            # Should not happen often, but handle gracefully
            print(f"Warning: Could not parse count result structure for user {user_id}")
            total_requests = 0  # Default to 0 if structure is unexpected

        # Get Most Recent Request Timestamp
        if total_requests > 0:

            # Query To Doc With Matching User Sorted By Recent
            last_req_query = (
                requests_ref.where(filter=FieldFilter("userId", "==", user_id))
                .order_by("requestedAt", direction="DESCENDING")
                .limit(1)
            )

            # Pulled Docx
            results = list(last_req_query.stream())

            if results:

                # Format To Extarct Data
                data = results[0].to_dict()

                # Pull Timestamp
                last_requested_at = data.get("requestedAt")

                # Format timestamp to ISO string
                if isinstance(last_requested_at, datetime):
                    last_requested_at_str = last_requested_at.isoformat()

        # Return the Summary
        summary = DeviceRequestSummary(
            totalRequests=total_requests, lastRequestedAt=last_requested_at_str
        )
        return summary

    except Exception as e:
        print(f"Error fetching device request summary for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve device request summary for the user.",
        )


@router.get("/get-device-photo/{request_id}")
async def get_device_photo_for_request(
    request_id: str,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    """
    🔒 SECURE ADMIN ENDPOINT: View photo for a specific device request.
    
    Security Features:
    - Requires admin authentication
    - Access by request ID only (not photo ID)
    - Photos stored securely in database
    - No public URLs or direct access possible
    - All access logged
    """
    try:
        # Get the device request document
        request_ref = db.collection("deviceRequests").document(request_id)
        request_doc = request_ref.get()
        
        if not request_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device request {request_id} not found"
            )
        
        request_data = request_doc.to_dict()
        
        # Only support database storage (photoId)
        photo_id = request_data.get("photoId")
        if not photo_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No photo found for this device request. Only new database-stored photos are supported."
            )
        
        # Retrieve photo from secure database storage
        photo = await get_device_photo_from_db(photo_id)
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Photo {photo_id} not found in database"
            )
        
        # Log secure access
        admin_email = admin_user.get("email", "unknown")
        print(f"🔒 SECURE PHOTO ACCESS: Admin {admin_email} viewing photo {photo_id} for request {request_id}")
        
        # Return photo with security headers
        return Response(
            content=photo.image_data,
            media_type=photo.content_type,
            headers={
                "Content-Disposition": f"inline; filename={photo.filename}",
                "X-Request-Info": f"Request: {request_id}, User: {request_data.get('userId')}, Device: {request_data.get('deviceId')}",
                "X-Security-Level": "admin-only",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving secure photo for request {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve photo for device request"
        )


@router.get("/get-device-photo-base64/{request_id}")
async def get_device_photo_base64_for_request(
    request_id: str,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    """
    🔒 SECURE ADMIN ENDPOINT: Get device photo as base64 for a specific request.
    
    Security Features:
    - Requires admin authentication
    - Access by request ID only (not photo ID)
    - Returns base64 data for web display
    - All access logged
    """
    try:
        # Get the device request document
        request_ref = db.collection("deviceRequests").document(request_id)
        request_doc = request_ref.get()
        
        if not request_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device request {request_id} not found"
            )
        
        request_data = request_doc.to_dict()
        photo_id = request_data.get("photoId")
        
        if not photo_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No photo found for this device request. Only new database-stored photos are supported."
            )
        
        # Retrieve photo from secure database storage
        photo = await get_device_photo_from_db(photo_id)
        if not photo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Photo {photo_id} not found in database"
            )
        
        # Log secure access
        admin_email = admin_user.get("email", "unknown")
        print(f"🔒 SECURE PHOTO ACCESS (base64): Admin {admin_email} viewing photo {photo_id} for request {request_id}")
        
        base64_data = photo_to_base64(photo)
        
        return {
            "request_id": request_id,
            "photo_id": photo.id,
            "user_id": request_data.get("userId"),
            "device_id": request_data.get("deviceId"),
            "filename": photo.filename,
            "content_type": photo.content_type,
            "file_size": photo.file_size,
            "uploaded_at": photo.uploaded_at,
            "base64_data": base64_data,
            "security_level": "admin-only"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error retrieving secure base64 photo for request {request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve photo for device request"
        )
