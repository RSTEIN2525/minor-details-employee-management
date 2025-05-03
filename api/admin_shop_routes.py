
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated, List, Optional
from sqlmodel import Session, select  
from pydantic import BaseModel, Field as PydanticField
from models.shop import Shop 
from db.session import get_session  
from core.deps import require_admin_role  

# --- Router Definition ---
router = APIRouter()


# --- Pydantic Data Models ---
# These models define the expected structure for data in API requests/responses


# Base model: Common fields required or used by other Shop models
class ShopBase(BaseModel):
    name: Optional[str] = None
    center_lat: float
    center_lng: float
    radius_meters: float = PydanticField(gt=0)  # Ensures radius is positive


# Create model: Data needed when creating a NEW shop via POST
class ShopCreate(ShopBase):
    id: str = PydanticField(
        ..., min_length=1, description="Unique shop identifier (e.g., dealership code)"
    )  # ID is required for creation


# Read model: Defines how shop data should look when sent back in responses
class ShopRead(ShopBase):
    id: str
    name: Optional[str]  # Make sure name is included


# Update model: Defines fields that CAN be updated via PUT/PATCH (all optional)
class ShopUpdate(BaseModel):
    name: Optional[str] = None
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
    radius_meters: Optional[float] = PydanticField(
        default=None, gt=0
    )  # Validate if sent


# --- API Endpoints ---


# Endpoint: Create a New Shop
@router.post("/shops", response_model=ShopRead, status_code=status.HTTP_201_CREATED)
async def create_shop(
    shop_in: ShopCreate,  # Expects request body matching ShopCreate model
    session: Annotated[Session, Depends(get_session)],  # DB session dependency
    admin_user: Annotated[dict, Depends(require_admin_role)],  # Admin auth dependency
):

    # Check If Shop Already Exists using Primary Key (ID)
    existing_shop = session.get(Shop, shop_in.id)
    if existing_shop:
        # If exists, raise conflict error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shop with ID '{shop_in.id}' already exists.",
        )

    # If not existing, proceed with creation
    try:
        # Convert Incoming Pydantic Model Data Into Python Dictionary
        shop_data = shop_in.model_dump()

        # Create DB Model Instance using the dictionary data
        db_shop = Shop(**shop_data)

        # Add the new DB model instance to the session (stage for saving)
        session.add(db_shop)
        # Commit the session to save changes to the actual database
        session.commit()
        # Refresh the instance to get any updated info from the DB (like defaults)
        session.refresh(db_shop)

        # Log admin action for auditing
        print(f"Admin {admin_user.get('email')} created shop {db_shop.id}")

        # Return the newly created shop object (FastAPI converts to JSON)
        return db_shop

    except Exception as e:
        # If any error occurs during DB operations, rollback changes
        session.rollback()
        print(f"Error creating shop {shop_in.id}: {e}")
        # Raise a generic server error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create shop.",
        )


# Endpoint: List All Shops
@router.get("/shops", response_model=List[ShopRead])
async def list_all_shops(
    session: Annotated[Session, Depends(get_session)],  # DB session dependency
    admin_user: Annotated[dict, Depends(require_admin_role)],  # Admin auth dependency
):
    try:
        # Build Query to select all Shop objects, order by ID
        statement = select(Shop).order_by(Shop.id)
        # Execute query and get all results
        shops = session.exec(statement).all()
        # Return the list of shops
        return shops
    except Exception as e:
        print(f"Error listing shops: {e}")
        # Raise a generic server error if DB query fails
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve shop list.",
        )


# Endpoint: Get a Single Shop by ID
@router.get("/shops/{shop_id}", response_model=ShopRead)
async def read_shop(
    shop_id: str,  # Shop ID from the URL path
    session: Annotated[Session, Depends(get_session)],  # DB session dependency
    admin_user: Annotated[dict, Depends(require_admin_role)],  # Admin auth dependency
):

    # Attempt to get the Shop object directly using its primary key (ID)
    db_shop = session.get(Shop, shop_id)

    # Check if the shop was found
    if not db_shop:
        # If not found, raise a 404 error
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop with ID '{shop_id}' not found.",
        )

    # If found, return the shop object
    return db_shop


# Endpoint: Update an Existing Shop by ID
@router.put("/shops/{shop_id}", response_model=ShopRead)
async def update_shop(
    shop_id: str,  # Shop ID from the URL path
    shop_update: ShopUpdate,  # Expects request body matching ShopUpdate model
    session: Annotated[Session, Depends(get_session)],  # DB session dependency
    admin_user: Annotated[dict, Depends(require_admin_role)],  # Admin auth dependency
):

    # First, get the existing shop object from the DB
    db_shop = session.get(Shop, shop_id)
    if not db_shop:
        # If not found, raise a 404 error
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop with ID '{shop_id}' not found.",
        )

    try:
        # Convert the incoming update data to a dictionary
        # exclude_unset=True ensures we only get fields the client actually sent
        update_data = shop_update.model_dump(exclude_unset=True)

        # Loop through the key/value pairs in the update data
        for key, value in update_data.items():
            # Update the corresponding attribute on the existing db_shop object
            setattr(db_shop, key, value)

        # Add the modified db_shop object back to the session (marks it as changed)
        session.add(db_shop)
        # Commit the changes to the database
        session.commit()
        # Refresh the object to reflect the saved state
        session.refresh(db_shop)

        # Log admin action
        print(f"Admin {admin_user.get('email')} updated shop {db_shop.id}")

        # Return the updated shop object
        return db_shop
    except Exception as e:
        # Rollback if update fails
        session.rollback()
        print(f"Error updating shop {shop_id}: {e}")
        # Raise a generic server error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update shop.",
        )


# Endpoint: Delete a Shop by ID
@router.delete("/shops/{shop_id}", status_code=status.HTTP_200_OK)
async def delete_shop(
    shop_id: str,  # Shop ID from the URL path
    session: Annotated[Session, Depends(get_session)],  # DB session dependency
    admin_user: Annotated[dict, Depends(require_admin_role)],  # Admin auth dependency
):
    # First, get the existing shop object to ensure it exists
    db_shop = session.get(Shop, shop_id)
    if not db_shop:
        # If not found, raise a 404 error
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop with ID '{shop_id}' not found.",
        )

    try:
        # Tell the session to delete the object
        session.delete(db_shop)
        # Commit the deletion to the database
        session.commit()

        # Log admin action
        print(f"Admin {admin_user.get('email')} deleted shop {shop_id}")

        # Return a success message
        # Alternatively, use status_code=204 and return None
        return {
            "status": "success",
            "message": f"Shop '{shop_id}' deleted successfully.",
        }
    except Exception as e:
        # Rollback if delete fails (though less common for delete)
        session.rollback()
        print(f"Error deleting shop {shop_id}: {e}")
        # Raise a generic server error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete shop.",
        )
