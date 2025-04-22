from fastapi import FastAPI
from models.time_log import SQLModel
from db.session import engine
from contextlib import asynccontextmanager
from api.time_routes import router as time_router

app = FastAPI()

# Create tables if they don't exist
@asynccontextmanager
def on_startup():
    SQLModel.metadata.create_all(engine)

app.include_router(time_router, prefix="/time", tags=["Time Tracking"])
