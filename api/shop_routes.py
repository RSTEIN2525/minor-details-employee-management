from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import Optional

from models.shop import Shop
from db.session import get_session
from core.deps import get_current_user # For authenticated users, if needed later
from pydantic import BaseModel

router = APIRouter()

# --- Pydantic Models for Response ---

class ShopGeofenceResponse(BaseModel):
    shop_id: str
    name: Optional[str] = None
    center_lat: float
    center_lng: float
    radius_meters: float

# --- API Endpoints ---

@router.get("/{shop_id}/geofence", response_model=ShopGeofenceResponse)
def get_shop_geofence(
    shop_id: str,
    session: Session = Depends(get_session),
    # current_user: dict = Depends(get_current_user) # Uncomment if endpoint should be restricted to authenticated users only
):
    """
    Retrieve the geofence information (latitude, longitude, radius) for a specific shop.
    """
    shop = session.get(Shop, shop_id)
    
    if not shop:
        raise HTTPException(status_code=404, detail=f"Shop with ID {shop_id} not found.")
        
    return ShopGeofenceResponse(
        shop_id=shop.id,
        name=shop.name,
        center_lat=shop.center_lat,
        center_lng=shop.center_lng,
        radius_meters=shop.radius_meters
    )

# Future: Endpoint to get geofence for all shops a user is assigned to, if needed.
# @router.get("/my-dealership-geofences", response_model=List[ShopGeofenceResponse])
# def get_my_dealership_geofences(
#     session: Session = Depends(get_session),
#     current_user: dict = Depends(get_current_user) 
# ):
#     user_dealership_ids = current_user.get("dealerships", []) # Assuming 'dealerships' is a list of shop_ids
#     if not user_dealership_ids:
#         return []
#     
#     shops = session.exec(select(Shop).where(Shop.id.in_(user_dealership_ids))).all()
#     return [
#         ShopGeofenceResponse(
#             shop_id=shop.id,
#             name=shop.name,
#             center_lat=shop.center_lat,
#             center_lng=shop.center_lng,
#             radius_meters=shop.radius_meters
#         ) for shop in shops
#     ] 