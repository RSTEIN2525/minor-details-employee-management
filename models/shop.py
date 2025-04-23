from sqlmodel import SQLModel, Field
from typing import Optional

# Defines the Structure of Data for Comapring an Employee Clock In/Out to Expected Location

# Dealership w/ Circular Geofence
class Shop(SQLModel, table=True):
    id: str = Field(primary_key=True, description="Unique shop identifier")
    name: Optional[str] = Field(default=None, description="Human-friendly shop name")
    center_lat: float = Field(..., description="Latitude of shop center")
    center_lng: float = Field(..., description="Longitude of shop center")
    radius_meters: float = Field(..., description="Allowed clock-in radius in meters")
