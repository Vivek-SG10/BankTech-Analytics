from typing import List, Dict, Any
import numpy as np


class AnalyticsEngine:
    """Core analytics engine for banking transaction metrics and fraud anomaly detection."""

    @staticmethod
    def calculate_summary(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not transactions:
            return {"total_volume": 0, "count": 0, "avg_amount": 0.0}

        amounts = [t.get("amount", 0.0) for t in transactions]
        return {
            "total_volume": float(sum(amounts)),
            "count": len(amounts),
            "avg_amount": float(np.mean(amounts)) if amounts else 0.0,
            "max_amount": float(max(amounts)) if amounts else 0.0,
            "min_amount": float(min(amounts)) if amounts else 0.0,
        }

    @staticmethod
    def detect_anomalies(transactions: List[Dict[str, Any]], threshold_sigma: float = 2.5) -> List[Dict[str, Any]]:
        if len(transactions) < 3:
            return []

        amounts = np.array([t.get("amount", 0.0) for t in transactions])
        mean = np.mean(amounts)
        std = np.std(amounts)
        if std == 0:
            return []

        z_scores = np.abs((amounts - mean) / std)
        anomalies = []
        for idx, z in enumerate(z_scores):
            if z > threshold_sigma:
                anomalies.append({**transactions[idx], "z_score": float(z)})
        return anomalies
