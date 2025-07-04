from sqlmodel import SQLModel, Field, Index
from typing import Optional
from datetime import datetime, date, timezone

class CompanyTransaction(SQLModel, table=True):
    __tablename__ = "company_transactions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    employee_id: str = Field()
    
    amount: float
    notes: Optional[str] = Field(default=None)
    transaction_date: date
    
    # Store the GCS path to the receipt image
    receipt_image_path: str 
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("ix_company_transactions_employee_id", "employee_id"),
        Index("ix_company_transactions_transaction_date", "transaction_date"),
    ) 