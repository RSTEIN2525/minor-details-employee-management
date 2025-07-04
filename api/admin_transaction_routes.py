from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request, Header
from typing import Annotated, List
from sqlmodel import Session, select
from datetime import date, datetime
import asyncio
import os
from firebase_admin import storage as admin_storage

from core.deps import get_session, require_admin_role, require_admin_role_from_token
from core.firebase import db
from models.company_transaction import CompanyTransaction
from utils.storage import debug_file_metadata,remove_download_tokens_from_file
from pydantic import BaseModel

router = APIRouter()

class TransactionResponse(BaseModel):
    id: int
    employee_id: str
    employee_name: str | None
    employee_email: str | None
    amount: float
    notes: str | None
    transaction_date: date
    receipt_url: str
    created_at: datetime

async def enrich_transactions(transactions: List[CompanyTransaction]) -> List[TransactionResponse]:
    """Helper to enrich transaction data with user info and a secure receipt URL."""
    if not transactions:
        return []

    # Get unique employee IDs from the transactions
    employee_ids = list(set(t.employee_id for t in transactions))

    # Fetch user data from Firestore in a batch
    user_refs = [db.collection("users").document(uid) for uid in employee_ids]
    user_docs = await asyncio.to_thread(db.get_all, user_refs)
    
    user_map = {doc.id: doc.to_dict() for doc in user_docs if doc.exists}

    # Create response models
    response_list = []
    for t in transactions:
        user_info = user_map.get(t.employee_id, {})
        
        # The URL now points to our new secure proxy endpoint
        receipt_url = f"/admin/transactions/receipt/{t.id}"

        response_list.append(
            TransactionResponse(
                id=t.id,
                employee_id=t.employee_id,
                employee_name=user_info.get("displayName"),
                employee_email=user_info.get("email"),
                amount=t.amount,
                notes=t.notes,
                transaction_date=t.transaction_date,
                receipt_url=receipt_url,
                created_at=t.created_at,
            )
        )
    return response_list

@router.get("/", response_model=List[TransactionResponse])
async def get_all_transactions(
    admin_user: Annotated[dict, Depends(require_admin_role)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Retrieves all company card transactions, sorted by most recent.
    """
    statement = select(CompanyTransaction).order_by(CompanyTransaction.transaction_date.desc()).limit(limit).offset(offset)
    transactions = session.exec(statement).all()
    
    return await enrich_transactions(transactions)

@router.get("/by-date-range", response_model=List[TransactionResponse])
async def get_transactions_by_date_range(
    admin_user: Annotated[dict, Depends(require_admin_role)],
    session: Annotated[Session, Depends(get_session)],
    start_date: date,
    end_date: date,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Retrieves company card transactions within a specified date range.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date.")
        
    statement = (
        select(CompanyTransaction)
        .where(CompanyTransaction.transaction_date >= start_date)
        .where(CompanyTransaction.transaction_date <= end_date)
        .order_by(CompanyTransaction.transaction_date.desc())
        .limit(limit)
        .offset(offset)
    )
    transactions = session.exec(statement).all()

    return await enrich_transactions(transactions)

@router.get("/receipt/{transaction_id}", response_class=Response)
async def get_transaction_receipt_image(
    transaction_id: int,
    session: Annotated[Session, Depends(get_session)],
    request: Request,
    token: str | None = Query(None, description="Firebase ID token for auth (optional if Authorization header provided)"),
    authorization: str | None = Header(None, description="Bearer token in Authorization header (optional if token query param provided)"),
):
    """Securely serves a receipt image from GCS by transaction ID.

    Access is permitted if EITHER:
      1. A valid Firebase ID token is supplied in the `token` query parameter, OR
      2. A standard `Authorization: Bearer <token>` header is supplied and the associated
         user has an admin role (currently `owner`).
    """

    # --------------------------------------------------
    # 1) Authenticate caller and ensure admin role
    # --------------------------------------------------
    admin_user: dict | None = None

    if token:
        # Prefer explicit query-string token if provided
        admin_user = require_admin_role_from_token(token)
    else:
        # Fall back to Authorization header if present
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized – no valid credentials supplied")
        header_token = authorization.split(" ", 1)[1]
        admin_user = require_admin_role_from_token(header_token)

    # --------------------------------------------------
    # 2) Fetch the transaction and the receipt image bytes
    # --------------------------------------------------
    transaction = session.get(CompanyTransaction, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    object_path = transaction.receipt_image_path

    try:
        bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "minordetails-1aff3.appspot.com")

        bucket = admin_storage.bucket(bucket_name)
        blob = bucket.blob(object_path)

        if not await asyncio.to_thread(blob.exists):
            raise HTTPException(status_code=404, detail="Receipt image not found in storage.")

        # Download the file contents as bytes
        image_bytes = await asyncio.to_thread(blob.download_as_bytes)

        # Get content type from blob metadata
        content_type = blob.content_type or "image/jpeg"

        # Log access for auditing
        admin_email = admin_user.get("email", "unknown") if admin_user else "unknown"
        print(f"🔒 SECURE RECEIPT ACCESS: Admin {admin_email} viewing receipt for transaction {transaction_id}")

        return Response(
            content=image_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=receipt_{transaction_id}.jpg",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )
    except HTTPException:
        # Pass through HTTP exceptions untouched
        raise
    except Exception as e:
        print(f"❌ Error streaming receipt {object_path}: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve receipt image.") 