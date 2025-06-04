from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
from sqlalchemy import text
import models.time_log  
import models.shop       
import models.clock_request_log # Ensure this model is known by SQLModel for table creation
import models.admin_time_change # New model for tracking admin time changes
import models.device_photo # New model for device photos stored in database
from db.session import engine
from contextlib import asynccontextmanager
from api.time_routes import router as time_router
from api.device_routes import router as device_router
from api.admin_device_routes import router as admin_device_router
from api.admin_user_routes import router as admin_user_router
from api.admin_shop_routes import router as admin_shop_router
from api.admin_dealership_routes import router as admin_dealership_router
from api.user_dashboard_routes import router as user_dashboard_router
from api.admin_clock_request_routes import router as admin_clock_request_router
from api.admin_analytics_routes import router as admin_analytics_router
from api.admin_time_routes import router as admin_time_router
from api.admin_injury_routes import router as admin_injury_router
from api.shop_routes import router as shop_router
import logging # Add this import
import os
from dotenv import load_dotenv

# Configure logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING) # Add this line

# This file is the control center of the whole application

# Load environment variables from .env file, if it exists
load_dotenv()

# Default values can be provided if the env var is not set
DEV_DOMAIN = os.getenv("DEV_DOMAIN", "http://localhost:5173")
PRODUCTION_DOMAIN = os.getenv("PRODUCTION_DOMAIN", "https://minorautodetails.app")

# Construct the list of allowed origins, always including both dev and production
allowed_origins_list = [
    DEV_DOMAIN,
    PRODUCTION_DOMAIN,
    "http://localhost:3000",  # Additional fallback for React dev
    "http://127.0.0.1:5173",  # Additional fallback for Vite dev
]

# Remove any None values and duplicates
allowed_origins_list = list(set([origin for origin in allowed_origins_list if origin]))

print(f"🌐 CORS: Allowing origins: {allowed_origins_list}")

# When We Start, Create the DB Tables if they don't exist
@asynccontextmanager
async def lifespan(app: FastAPI):
 
    SQLModel.metadata.create_all(engine)

    # (would do shutdown cleanup here if needed)
    yield


# Starts Fast API Up; Init
app = FastAPI(lifespan=lifespan)

# Allow requests from your React dev server & production
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list, # Use the constructed list
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connects Routes From Time_Routes (clock-in / out) to main app
app.include_router(time_router, prefix="/time", tags=["Time"])
app.include_router(device_router, prefix="/device", tags=["Device"])
app.include_router(admin_device_router, prefix="/admin/device-requests", tags=["Admin Device"])
app.include_router(admin_user_router, prefix="/admin/user-requests", tags = ["Admin", "User Management"])
app.include_router(admin_shop_router, prefix="/admin/shop-requests", tags = ["Admin", "Shop Management"])
app.include_router(admin_dealership_router,prefix="/admin/dealership-requests", tags=["Admin", "Dealerships"] )
app.include_router(user_dashboard_router, prefix = "/user-dashboard-requests", tags=["User", "Finances"])
app.include_router(admin_clock_request_router, prefix="/admin/clock-requests", tags=["Admin", "Clock Requests"])
app.include_router(admin_analytics_router, prefix="/admin/analytics", tags=["Admin", "Labor Analytics"])
app.include_router(admin_time_router, prefix="/admin/time", tags=["Admin", "Direct Time Management"])
app.include_router(admin_injury_router, prefix="/admin/injury", tags=["Admin", "Injury Reports"])
app.include_router(shop_router, prefix="/shops", tags=["Shops", "Geofence"])
