from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
import models.time_log  
import models.shop       
from db.session import engine
from contextlib import asynccontextmanager
from api.time_routes import router as time_router
from api.device_routes import router as device_router
from api.admin_device_routes import router as admin_device_router
from api.admin_user_routes import router as admin_user_router
from api.admin_shop_routes import router as admin_shop_router
from api.admin_dealership_routes import router as admin_dealership_router

# This file is the control center of the whole application


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
    allow_origins=[
        "http://localhost:5173",  # React dev
        "https://minorautodetails.app",  # Production domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connects Routes From Time_Routes (clock-in / out) to main app
app.include_router(time_router, prefix="/time", tags=["Time Tracking"])
app.include_router(device_router,prefix="/device", tags=["Device Identification"])
app.include_router(admin_device_router, prefix="/admin/device-requests", tags=["Admin" "Device Identification"])
app.include_router(admin_user_router, prefix="/admin/user-requests", tags = ["Admin", "User Management"])
app.include_router(admin_shop_router, prefix="/admin/shop-requests", tags = ["Admin", "Shop Management"])
app.include_router(admin_dealership_router,prefix="/admin/dealership-requests", tags=["Admin", "Dealerships"] )
