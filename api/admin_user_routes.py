from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated, List 
from core.firebase import db
from core.deps import require_admin_role
from google.cloud.firestore_v1.transforms import ArrayRemove
from pydantic import BaseModel

# Define Router
router = APIRouter()

# Model For Key Value Pair Display Name : ID
class UserInfo(BaseModel):
    id: str
    displayName: str | None 

@router.get("/users", response_model=List[UserInfo]) 
async def list_all_users_for_admin(
    admin_user: Annotated[dict, Depends(require_admin_role)] 
):

    try:

        # Reference To User Collection
        users_ref = db.collection("users")
       
        # Fetch all documents in the collection
        users_stream = users_ref.stream()

        # Accumulator List
        users_list: List[UserInfo] = [] 

        # Loop Through Each Docx
        for doc in users_stream:

            # Make User's Data Readable
            user_data = doc.to_dict()

            # Don't Include Users Who Aren't Employees
            if user_data.get("role") != "employee":
                continue

            # Extract required fields
            user_info = UserInfo(
                id=doc.id,
                displayName=user_data.get("displayName", "MIssing") 
            )

            # Add To List
            users_list.append(user_info)

        # Sort list alphabetically by display name 
        users_list.sort(key=lambda x: x.displayName or "")

        return users_list

    except Exception as e:
        print(f"Error fetching list of users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve user list."
        )
