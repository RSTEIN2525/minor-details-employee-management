from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import JSONResponse
from typing import Annotated
from core.firebase import db
from core.deps import get_current_user, get_current_user_basic_auth
from datetime import datetime,timezone
from google.cloud.firestore_v1.transforms import ArrayUnion

router = APIRouter()


@router.post("/register")
async def register_device(
    current_user: Annotated[dict, Depends(get_current_user_basic_auth)],
    x_device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None,
):

    # Extract User's ID
    user_uid = current_user.get("uid")

    # Ensure Device ID Passed in Header
    if not x_device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Device-Id header is required.",
        )

    # Ensure Valid User In Our Firestore DB
    if not user_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )

    try:

        # Pull Collection W/ All Requests
        request_ref = db.collection("deviceRequests")

        # pull all exisiting requests
        existing_query = (
            request_ref.where("userId", "==", user_uid)
            .where("deviceId", "==", x_device_id)
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
        
        # Add to Firestore Collection
        request_doc_ref, write_result = request_ref.add({
            "userId" : user_uid,
            "userEmail" : current_user.get("email"),
            "userName" : current_user.get("name"),
            "deviceId" : x_device_id,
            "status" : "pending",
            "requestedAt" : datetime.now(timezone.utc)
        })
        
         # Return a success response indicating submission using 202 Accepted
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "submitted", "message": "Device registration request submitted for approval."}
        )
        

    except Exception as e:
        # Log the exception e for debugging purposes
        print(f"Error registering device for user {user_uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not register device.",
        )
