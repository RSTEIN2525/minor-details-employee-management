from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated
from datetime import datetime, timezone
from core.firebase import db
from google.cloud.firestore_v1.transforms import ArrayUnion
from google.cloud.firestore_v1.base_query import FieldFilter 
from core.deps import require_admin_role, get_current_user_basic_auth

router = APIRouter()

@router.get("/pending")
async def list_pending_device_requests(
    admin_user: Annotated[dict, Depends(require_admin_role)]
):
    try:
        
        # Pull Collection
        request_ref = db.collection("deviceRequests")

        # Form Query
        request_query = request_ref.where(filter=FieldFilter("status", "==", "pending"))\
                                    .order_by("requestedAt", direction="ASCENDING") # Or DESCENDING
        # Pull Docx
        pending_requests = []

        for doc in request_query.stream():
            
            # Pull Individual Doc As Dictionary
            request_data = doc.to_dict()

            # Add Firestore Doc ID
            request_data["id"] = doc.id

            # Convert Timestamp For JSON Compatibility
            if isinstance(request_data.get("requestedAt"), datetime):
                request_data["requestedAt"] = request_data["requestedAt"].isoformat()
            
            # Add To List
            pending_requests.append(request_data)
        
        return {"status": "success", "data": pending_requests}

    except Exception as e:
        print(f"Error fetching pending device requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve pending device requests."
        )

@router.get("/approved")
async def list_approved_device_requests(
    admin_user: Annotated[dict, Depends(require_admin_role)]
):
    try:
        
        # Pull Collection
        request_ref = db.collection("deviceRequests")

        # Form Query
        request_query = request_ref.where(filter=FieldFilter("status", "==", "approved"))\
                                    .order_by("processedAt", direction="DESCENDING")\
                                    .limit(25)
        # Pull Docx
        approved_requests = []

        for doc in request_query.stream():
            
            # Pull Individual Doc As Dictionary
            request_data = doc.to_dict()

            # Add Firestore Doc ID
            request_data["id"] = doc.id

            # Convert Timestamp For JSON Compatibility
            if isinstance(request_data.get("processedAt"), datetime):
                request_data["processedAt"] = request_data["processedAt"].isoformat()
            
            # Add To List
            approved_requests.append(request_data)
        
        return {"status": "success", "data": approved_requests}

    except Exception as e:
        print(f"Error fetching approved device requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve approved device requests."
        )

@router.get("/rejected")
async def list_rejected_device_requests(
    admin_user: Annotated[dict, Depends(require_admin_role)]
):
    try:
        
        # Pull Collection
        request_ref = db.collection("deviceRequests")

        # Form Query
        request_query = request_ref.where(filter=FieldFilter("status", "==", "rejected"))\
                                    .order_by("processedAt", direction="DESCENDING")\
                                    .limit(25)
        # Pull Docx
        rejected_requests = []

        for doc in request_query.stream():
            
            # Pull Individual Doc As Dictionary
            request_data = doc.to_dict()

            # Add Firestore Doc ID
            request_data["id"] = doc.id

            # Convert Timestamp For JSON Compatibility
            if isinstance(request_data.get("processedAt"), datetime):
                request_data["processedAt"] = request_data["processedAt"].isoformat()
            
            # Add To List
            rejected_requests.append(request_data)
        
        return {"status": "success", "data": rejected_requests}

    except Exception as e:
        print(f"Error fetching approved device requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve approved device requests."
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
                detail= f"Device Request {request_id} Does Not Exist"
            )
        
        # Extract Data from Docx
        request_data = request_doc.to_dict()

        # Ensure It's Actually Pending
        if request_data.get("status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
              detail=f"Request is not pending (current status: {request_data.get('status')})."
            )

        # Pull User & Device Information
        user_id = request_data.get("userId")
        device_id = request_data.get("deviceId")

        # Check User & Device ID Exist
        if not user_id or not device_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request document is missing required user or device ID.")

        # Get User Doc
        user_ref = db.collection("users").document(user_id)

        # Add the device_id to the USER's 'devices' array
        user_ref.update({
            "devices": ArrayUnion([device_id])
        })

        # Update Request
        request_ref.update({
            "status": "approved", # Correct status
            "processedAt": datetime.now(timezone.utc),
            "processedByUid": admin_user.get("uid"),
            "processedByEmail": admin_user.get("email")
        })

        # Return Success Message
        return {"status": "success", "message": "Device request approved successfully."}

    except Exception as e:
        print(f"Error approving device request {request_id}: {e}")
        # Check if it was an HTTPException already, re-raise if so
        if isinstance(e, HTTPException):
             raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not approve device request."
        )
    
@router.post("/{request_id}/reject")
async def reject_device_request(
    request_id: str,
    admin_user: Annotated[dict, Depends(require_admin_role)]
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
                detail= f"Device Request {request_id} Does Not Exist"
            )
        
        # Extract Data From Docx
        request_data = request_doc.to_dict()

        #Pull User Data
        user_id = request_data.get("userId")
        device_id = request_data.get("deviceId")

        # Check User & Device ID Exist
        if not user_id or not device_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request document is missing required user or device ID.")
        
        # Update Docx
        request_ref.update({
            "status" : "rejected",
            "processedAt": datetime.now(timezone.utc),
            "processedByUid": admin_user.get("uid"),
            "processedByEmail": admin_user.get("email")
        })

        # Inform of Successful Request
        return {"status": "success", "message": "Device request rejected successfully."}

    except Exception as e:
        print(f"Error rejecting device request {request_id}: {e}")
        if isinstance(e, HTTPException):
                raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not reject device request."
        )