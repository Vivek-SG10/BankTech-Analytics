from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Transaction(BaseModel):
    transaction_id: str
    account_id: str
    amount: float
    currency: str = "USD"
    transaction_type: str  # debit, credit, transfer
    category: str
    merchant_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_fraud_flagged: bool = False
    risk_score: float = 0.0
