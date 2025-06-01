from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
import models.time_log  
import models.shop       
import models.clock_request_log # Ensure this model is known by SQLModel for table creation
import models.shift_change # New model for shift changes
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
from api.admin_shift_change_routes import router as admin_shift_change_router
from api.user_shift_change_routes import router as user_shift_change_router
from api.admin_time_routes import router as admin_time_router

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
app.include_router(time_router, prefix="/time", tags=["Time"])
app.include_router(device_router, prefix="/device", tags=["Device"])
app.include_router(admin_device_router, prefix="/admin/device-requests", tags=["Admin Device"])
app.include_router(admin_user_router, prefix="/admin/user-requests", tags = ["Admin", "User Management"])
app.include_router(admin_shop_router, prefix="/admin/shop-requests", tags = ["Admin", "Shop Management"])
app.include_router(admin_dealership_router,prefix="/admin/dealership-requests", tags=["Admin", "Dealerships"] )
app.include_router(user_dashboard_router, prefix = "/user-dashboard-requests", tags=["User", "Finances"])
app.include_router(admin_clock_request_router, prefix="/admin/clock-requests", tags=["Admin", "Clock Requests"])
app.include_router(admin_analytics_router, prefix="/admin/analytics", tags=["Admin", "Labor Analytics"])
app.include_router(admin_shift_change_router, prefix="/admin/shift-changes", tags=["Admin", "Shift Changes"])
app.include_router(user_shift_change_router, prefix="/shift-changes", tags=["User", "Shift Changes"])
app.include_router(admin_time_router, prefix="/admin/time", tags=["Admin", "Direct Time Management"])
