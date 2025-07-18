import asyncio
from datetime import date
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from core.deps import require_admin_role
from db.session import get_session

from .admin_analytics_routes import (
    get_all_dealerships_comprehensive_labor_spend_by_range,
)

router = APIRouter()


class JobStatus(BaseModel):
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None


# In-memory job store (for simplicity; use Redis or Firestore in production)
job_store: Dict[str, JobStatus] = {}


async def run_report_generation(
    job_id: str, start_date: date, end_date: date, admin_user_id: str
):
    """
    This function runs in the background to generate the report.
    """
    try:
        # Create a fresh database session for the background task
        session = next(get_session())

        # Create a minimal admin user dict (we just need the ID for authorization)
        admin_user = {"uid": admin_user_id}

        # This is the long-running task
        report_data = await get_all_dealerships_comprehensive_labor_spend_by_range(
            start_date=start_date,
            end_date=end_date,
            session=session,
            admin_user=admin_user,
        )

        # Convert the result to a serializable format
        serialized_data = []
        for daily_report in report_data:
            serialized_data.append(daily_report.model_dump())

        job_store[job_id] = JobStatus(status="complete", result=serialized_data)

        # Close the session
        session.close()

    except Exception as e:
        print(f"Background job {job_id} failed: {str(e)}")
        job_store[job_id] = JobStatus(status="failed", error=str(e))


@router.post("/request-labor-spend-report")
async def request_labor_spend_report(
    start_date: date,
    end_date: date,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    admin_user: dict = Depends(require_admin_role),
):
    """
    Kick off the generation of a comprehensive labor spend report in the background.
    """
    job_id = str(uuid4())
    job_store[job_id] = JobStatus(status="in_progress")

    # Add the long-running task to the background
    background_tasks.add_task(
        run_report_generation, job_id, start_date, end_date, admin_user["uid"]
    )

    return {"job_id": job_id}


@router.get("/labor-spend-report-status/{job_id}", response_model=JobStatus)
async def get_labor_spend_report_status(job_id: str):
    """
    Check the status of a previously requested labor spend report.
    """
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
