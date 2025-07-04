from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile
from typing import Annotated, List
from sqlmodel import Session, select
from datetime import date, datetime, timedelta, timezone
from pydantic import BaseModel

from core.deps import get_session, get_current_user
from models.company_transaction import CompanyTransaction
from utils.storage import upload_receipt_image

router = APIRouter()

class MyTransactionResponse(BaseModel):
    id: int
    amount: float
    notes: str | None
    transaction_date: date
    created_at: datetime

@router.get("/me", response_model=List[MyTransactionResponse])
async def get_my_recent_transactions(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """
    Returns a list of the authenticated employee's transactions from the past 7 days.
    """
    employee_id = user.get("uid")
    if not employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate user credentials."
        )

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    statement = (
        select(CompanyTransaction)
        .where(CompanyTransaction.employee_id == employee_id)
        .where(CompanyTransaction.created_at >= seven_days_ago)
        .order_by(CompanyTransaction.transaction_date.desc())
    )
    
    transactions = session.exec(statement).all()
    
    return transactions

@router.post("/")
async def submit_transaction(
    user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    amount: float = Form(...),
    notes: str = Form(None),
    transaction_date: date = Form(...),
    receipt: UploadFile = (...),
):
    """
    Allows an authenticated employee to submit a company card transaction.
    """
    employee_id = user.get("uid")
    if not employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate user credentials."
        )

    try:
        # 1. Upload the receipt image and get its storage path
        receipt_path = await upload_receipt_image(file=receipt, user_id=employee_id)
        
        # 2. Create the transaction record in the database
        new_transaction = CompanyTransaction(
            employee_id=employee_id,
            amount=amount,
            notes=notes,
            transaction_date=transaction_date,
            receipt_image_path=receipt_path
        )
        
        session.add(new_transaction)
        session.commit()
        session.refresh(new_transaction)
        
        return {
            "status": "success",
            "message": "Transaction submitted successfully.",
            "data": new_transaction
        }
        
    except HTTPException as http_exc:
        # Re-raise exceptions from the upload function
        raise http_exc
    except Exception as e:
        # Handle other potential errors (e.g., database issues)
        print(f"❌ Error submitting transaction for user {employee_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        ) 