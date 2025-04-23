from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel
import models.time_log  
import models.shop       
from db.session import engine
from contextlib import asynccontextmanager
from api.time_routes import router as time_router

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
