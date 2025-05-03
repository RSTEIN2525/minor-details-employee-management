# api/admin_dealership_routes.py

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated, List, Optional
from pydantic import BaseModel

# Import Firestore client 'db'
from core.firebase import db

# Import the admin role dependency
from core.deps import require_admin_role

router = APIRouter()


# --- Pydantic Model for Response ---
class DealershipInfo(BaseModel):
    id: str  # The Dealership ID (Firestore Document ID)
    name: Optional[str]  # The Dealership Name


# --- API Endpoints ---
@router.get("/dealerships", response_model=List[DealershipInfo])
async def list_all_dealerships(
    admin_user: Annotated[dict, Depends(require_admin_role)],  # Protect route
):

    try:
        # Reference to the master dealerships collection in Firestore
        dealerships_ref = db.collection("dealerships")

        # Fetch all documents
        # Consider pagination or server-side filtering if list becomes very large
        dealerships_stream = dealerships_ref.stream()

        dealerships_list: List[DealershipInfo] = []
        for doc in dealerships_stream:
            data = doc.to_dict()
            # Create DealershipInfo object using doc ID and 'name' field
            dealership_info = DealershipInfo(id=doc.id, name=data.get("name"))
            dealerships_list.append(dealership_info)

        # Sort alphabetically by name for better UI presentation
        dealerships_list.sort(key=lambda x: x.name or x.id)

        return dealerships_list

    except Exception as e:
        print(f"Error fetching list of dealerships: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve dealership list.",
        )
