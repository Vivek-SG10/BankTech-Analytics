from fastapi import APIRouter
from typing import List, Dict, Any

from app.analytics.engine import AnalyticsEngine
from app.rag.pipeline import RAGPipeline

api_router = APIRouter()
rag_pipeline = RAGPipeline()


@api_router.get("/transactions/summary")
async def get_transactions_summary():
    # Sample analytical overview
    sample_data = [
        {"amount": 1250.50, "category": "Wire Transfer"},
        {"amount": 45.20, "category": "Merchant POS"},
        {"amount": 10500.00, "category": "International Transfer"},
    ]
    summary = AnalyticsEngine.calculate_summary(sample_data)
    anomalies = AnalyticsEngine.detect_anomalies(sample_data)
    return {
        "summary": summary,
        "anomalies": anomalies,
    }


@api_router.post("/rag/ask")
async def ask_compliance_bot(payload: Dict[str, str]):
    question = payload.get("question", "")
    response = await rag_pipeline.query(question)
    return response
