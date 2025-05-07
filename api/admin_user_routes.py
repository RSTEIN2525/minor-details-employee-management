from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated, List
from core.firebase import db
from core.deps import require_admin_role
from google.cloud.firestore_v1.transforms import ArrayRemove
from pydantic import BaseModel
from pydantic import Field as PydanticField
from typing import Optional

# Define Router
router = APIRouter()


# Model For Key Value Pair Display Name : ID
class UserInfo(BaseModel):
    id: str
    displayName: str | None

# Models For Wage Management
class UserWageUpdate(BaseModel):
    hourlyWage: float = PydanticField(
        ..., ge=0, description="The employee's hourly wage rate."
    )

class UserWageRead(BaseModel):
    hourlyWage: Optional[float] = None


@router.get("/users", response_model=List[UserInfo])
async def list_all_users_for_admin(
    admin_user: Annotated[dict, Depends(require_admin_role)],
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
                id=doc.id, displayName=user_data.get("displayName", "MIssing")
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
            detail="Could not retrieve user list.",
        )


@router.put("/users/{user_id}/wage", response_model=UserWageRead)
async def set_or_update_user_wage(
    user_id: str,
    wage_data: UserWageUpdate,
    admin_user: Annotated[dict, Depends(require_admin_role)],
):
    try:

        # Pull Docuement Reference
        user_ref = db.collection("users").document(user_id)

        # Get Actual Data
        user_doc = user_ref.get()

        # Check if user DNE
        if not user_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with user_id {user_id}, does not exist.",
            )

        # Update the user document with the new wage
        update_results = user_ref.update({"hourlyWage": wage_data.hourlyWage})

        # Return the newly set wage data
        return UserWageRead(hourlyWage=wage_data.hourlyWage)

    except Exception as e:
        print(f"Error updating wage for user {user_id}: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update user wage.",
        )


@router.get("/users/{user_id}/wage", response_model=UserWageRead)
async def get_user_wage(
    user_id: str,  # User ID from path
    admin_user: Annotated[dict, Depends(require_admin_role)],  # Admin auth
):

    try:
        # Pull Document Reference
        user_ref = db.collection("users").document(user_id)

        # Get Document
        user_doc = user_ref.get()

        # Ensure It Exists
        if not user_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found.",
            )
        # Convert to Python Dictorionary
        profile = user_doc.to_dict()

        # Extract Wage Key From Dictionary
        current_wage = profile.get("hourlyWage")

        # Ensure Type Safety
        if current_wage is not None and not isinstance(current_wage, (int, float)):
            print(f"Warning: User {user_id} has non-numeric wage value: {current_wage}")
            current_wage = None  # Treat invalid data as None

        # Return Wage
        return UserWageRead(hourlyWage=current_wage)

    except Exception as e:
        print(f"Error retrieving wage for user {user_id}: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve user wage.",
        )
