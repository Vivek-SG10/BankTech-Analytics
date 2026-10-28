"""
Analytics API endpoints — admin and researcher access only.

New in this revision
--------------------
- Filter parameters on all index/correlation/regression endpoints:
    department, from_date, to_date, bank_type, experience_range
- GET /api/v1/analytics/summary — lightweight overview for dashboard cards
- GET /api/v1/analytics/export/csv — download aggregated stats as CSV
  (Never exports individual responses; Cronbach's alpha + descriptive stats only)
- All endpoints return 200 with suppressed flags when data is insufficient.

Privacy rules
-------------
- No individual-level responses are returned by any endpoint.
- CSV export contains only aggregated index scores and descriptive stats.
- Minimum-N thresholds enforced inside the indices engine.
"""
from __future__ import annotations

import csv
import io
from dataclasses import asdict
from datetime import date
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_roles
from app.auth.models import UserOrm
from app.core.database import get_db
from app.surveys.crud import (
    list_all_customer_surveys,
    list_all_employee_surveys,
    list_all_manager_surveys,
)
from app.analytics.indices import (
    compute_correlations,
    compute_csei,
    compute_descriptive_stats,
    compute_epi_manager,
    compute_epi_self,
    compute_ejsi,
    compute_regression,
    compute_tai_employee,
    compute_tai_manager,
    missing_value_report,
)

analytics_router = APIRouter()


# ── Helper: ORM list → DataFrame ──────────────────────────────────────────────

def _to_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([
        {c.key: getattr(row, c.key) for c in row.__table__.columns}
        for row in rows
    ])


def _apply_filters(
    df: pd.DataFrame,
    department: str | None,
    from_date: date | None,
    to_date: date | None,
    bank_type: str | None,
    experience_range: str | None,
) -> pd.DataFrame:
    if df.empty:
        return df
    if department and "department" in df.columns:
        df = df[df["department"] == department]
    if from_date and "submitted_at" in df.columns:
        df = df[pd.to_datetime(df["submitted_at"]).dt.date >= from_date]
    if to_date and "submitted_at" in df.columns:
        df = df[pd.to_datetime(df["submitted_at"]).dt.date <= to_date]
    if bank_type and "bank_type" in df.columns:
        df = df[df["bank_type"] == bank_type]
    if experience_range and "experience_range" in df.columns:
        df = df[df["experience_range"] == experience_range]
    return df.reset_index(drop=True)


async def _load_dataframes(
    db: AsyncSession,
    department: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    bank_type: str | None = None,
    experience_range: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    emp_rows  = await list_all_employee_surveys(db)
    mgr_rows  = await list_all_manager_surveys(db)
    cust_rows = await list_all_customer_surveys(db)
    emp_df  = _apply_filters(_to_df(emp_rows),  department, from_date, to_date, bank_type, experience_range)
    mgr_df  = _apply_filters(_to_df(mgr_rows),  department, from_date, to_date, bank_type, experience_range)
    cust_df = _apply_filters(_to_df(cust_rows), department, from_date, to_date, None, None)
    return emp_df, mgr_df, cust_df


# ── Common filter deps ─────────────────────────────────────────────────────────

def _filter_params(
    department: str | None = Query(None, description="Filter by department name"),
    from_date: date | None = Query(None, description="Earliest submission date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="Latest submission date (YYYY-MM-DD)"),
    bank_type: str | None = Query(None, description="Bank type filter"),
    experience_range: str | None = Query(None, description="Experience range filter (e.g. '2-5')"),
) -> dict:
    return dict(department=department, from_date=from_date, to_date=to_date,
                bank_type=bank_type, experience_range=experience_range)


# ── Dashboard Summary ──────────────────────────────────────────────────────────

@analytics_router.get(
    "/summary",
    summary="[Researcher] Dashboard summary cards",
    description=(
        "Lightweight endpoint for dashboard summary cards. "
        "Returns response counts and index scores (suppressed when N insufficient)."
    ),
)
async def summary(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    emp_df, mgr_df, cust_df = await _load_dataframes(db)
    tai_emp = compute_tai_employee(emp_df)
    ejsi    = compute_ejsi(emp_df)
    epi_mgr = compute_epi_manager(mgr_df)
    csei    = compute_csei(cust_df)
    return {
        "response_counts": {
            "employee": len(emp_df),
            "manager":  len(mgr_df),
            "customer": len(cust_df),
            "total":    len(emp_df) + len(mgr_df) + len(cust_df),
        },
        "index_scores": {
            "TAI_employee": tai_emp.score_pct,
            "EJSI":         ejsi.score_pct,
            "EPI_manager":  epi_mgr.score_pct,
            "CSEI":         csei.score_pct,
        },
        "suppression_notes": {
            "TAI_employee": tai_emp.warning,
            "EJSI":         ejsi.warning,
            "EPI_manager":  epi_mgr.warning,
            "CSEI":         csei.warning,
        },
        "data_label": "LIVE — drawn from PostgreSQL survey responses.",
    }


# ── Overview ───────────────────────────────────────────────────────────────────

@analytics_router.get("/overview", summary="[Researcher] Survey response overview")
async def overview(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, mgr_df, cust_df = await _load_dataframes(db, **filters)
    return {
        "employee_responses": len(emp_df),
        "manager_responses":  len(mgr_df),
        "customer_responses": len(cust_df),
        "filters_applied": {k: v for k, v in filters.items() if v is not None},
        "note": "Counts reflect non-voided (latest) responses per participant.",
    }


# ── Descriptive statistics ─────────────────────────────────────────────────────

@analytics_router.get("/descriptive", summary="[Researcher] Descriptive statistics per survey item")
async def descriptive_statistics(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, mgr_df, cust_df = await _load_dataframes(db, **filters)
    stats = compute_descriptive_stats(emp_df, mgr_df, cust_df)
    return {"items": [asdict(s) for s in stats], "n_employee": len(emp_df),
            "n_manager": len(mgr_df), "n_customer": len(cust_df)}


# ── Missing-value report ───────────────────────────────────────────────────────

@analytics_router.get("/missing", summary="[Researcher] Missing-value analysis")
async def missing_values(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, mgr_df, cust_df = await _load_dataframes(db, **filters)
    return missing_value_report(emp_df, mgr_df, cust_df)


# ── TAI ────────────────────────────────────────────────────────────────────────

@analytics_router.get("/tai", summary="[Researcher] Technology Adoption Index")
async def tai(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, mgr_df, _ = await _load_dataframes(db, **filters)
    tai_emp = compute_tai_employee(emp_df)
    tai_mgr = compute_tai_manager(mgr_df)
    return {
        "TAI_employee": asdict(tai_emp),
        "TAI_manager":  asdict(tai_mgr),
        "methodology": (
            "Five-point Likert scale. Score = (mean / 5) × 100. "
            "Employee and manager components are kept separate."
        ),
    }


# ── EJSI ───────────────────────────────────────────────────────────────────────

@analytics_router.get("/ejsi", summary="[Researcher] Employee Job Satisfaction Index")
async def ejsi(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, _, _ = await _load_dataframes(db, **filters)
    result = compute_ejsi(emp_df)
    return {
        "EJSI": asdict(result),
        "methodology": (
            "Six-item self-report scale. Score = (mean / 5) × 100. "
            "Limitation: subject to social-desirability bias."
        ),
    }


# ── EPI ────────────────────────────────────────────────────────────────────────

@analytics_router.get("/epi", summary="[Researcher] Employee Performance Index")
async def epi(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, mgr_df, _ = await _load_dataframes(db, **filters)
    epi_mgr  = compute_epi_manager(mgr_df)
    epi_self = compute_epi_self(emp_df)
    return {
        "EPI_manager": asdict(epi_mgr),
        "EPI_self":    asdict(epi_self),
        "methodology": (
            "EPI_manager (primary): supervisor assessment. "
            "EPI_self (supplementary): employee self-assessment. "
            "Never aggregated — Podsakoff & Organ (1986)."
        ),
    }


# ── CSEI ───────────────────────────────────────────────────────────────────────

@analytics_router.get("/csei", summary="[Researcher] Customer Service Effectiveness Index")
async def csei(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    _, _, cust_df = await _load_dataframes(db, **filters)
    result = compute_csei(cust_df)
    return {
        "CSEI": asdict(result),
        "methodology": (
            "Six-item customer self-report. Score = (mean / 5) × 100. "
            "No individual staff identified."
        ),
    }


# ── Correlations ───────────────────────────────────────────────────────────────

@analytics_router.get("/correlations", summary="[Researcher] Pre-specified correlation analyses")
async def correlations(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, mgr_df, cust_df = await _load_dataframes(db, **filters)
    results = compute_correlations(emp_df, mgr_df, cust_df)
    return {
        "correlations": [asdict(r) for r in results],
        "caution": (
            "Correlation does not imply causation. "
            "Suppressed results indicate insufficient data (N < 10)."
        ),
    }


# ── Regression ─────────────────────────────────────────────────────────────────

@analytics_router.get("/regression", summary="[Researcher] OLS regression models")
async def regression(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
) -> dict[str, Any]:
    emp_df, mgr_df, _ = await _load_dataframes(db, **filters)
    results = compute_regression(emp_df, mgr_df)
    return {
        "models": [asdict(r) for r in results],
        "caution": (
            "OLS regression results are associative, not causal. "
            "Results suppressed when N < 20."
        ),
    }


# ── CSV Export ─────────────────────────────────────────────────────────────────

@analytics_router.get(
    "/export/csv",
    summary="[Researcher] Export aggregated analytics as CSV",
    description=(
        "Downloads a CSV file of aggregated index scores and per-item descriptive statistics. "
        "NO individual-level responses are included. "
        "The file is clearly labelled LIVE or SUPPRESSED."
    ),
    response_class=StreamingResponse,
)
async def export_csv(
    _actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
    filters: dict = Depends(_filter_params),
):
    emp_df, mgr_df, cust_df = await _load_dataframes(db, **filters)

    tai_emp = compute_tai_employee(emp_df)
    tai_mgr = compute_tai_manager(mgr_df)
    ejsi_r  = compute_ejsi(emp_df)
    epi_mgr = compute_epi_manager(mgr_df)
    epi_s   = compute_epi_self(emp_df)
    csei_r  = compute_csei(cust_df)
    desc    = compute_descriptive_stats(emp_df, mgr_df, cust_df)

    output = io.StringIO()
    writer = csv.writer(output)

    # ── Index scores ──
    writer.writerow(["BankTech Analytics — Aggregated Index Scores"])
    writer.writerow(["IMPORTANT: This file contains aggregated data only. No individual responses."])
    writer.writerow([])
    writer.writerow(["Index", "N", "Score (%)", "Mean (raw)", "SD", "Cronbach Alpha", "Status"])
    for idx in [tai_emp, tai_mgr, ejsi_r, epi_mgr, epi_s, csei_r]:
        writer.writerow([
            idx.name, idx.n,
            f"{idx.score_pct:.2f}" if idx.score_pct is not None else "SUPPRESSED",
            f"{idx.mean_raw:.4f}" if idx.mean_raw is not None else "SUPPRESSED",
            f"{idx.sd:.4f}" if idx.sd is not None else "SUPPRESSED",
            f"{idx.cronbach_alpha:.4f}" if idx.cronbach_alpha is not None else "—",
            "SUPPRESSED" if idx.score_pct is None else "LIVE",
        ])

    # ── Descriptive stats ──
    writer.writerow([])
    writer.writerow(["Per-Item Descriptive Statistics"])
    writer.writerow(["Item", "N", "Mean", "Median", "SD", "IQR", "Skewness", "Kurtosis"])
    for s in desc:
        writer.writerow([
            s.item, s.n,
            f"{s.mean:.4f}" if s.mean is not None else "",
            f"{s.median:.4f}" if s.median is not None else "",
            f"{s.sd:.4f}" if s.sd is not None else "",
            f"{s.iqr:.4f}" if s.iqr is not None else "",
            f"{s.skewness:.4f}" if s.skewness is not None else "",
            f"{s.kurtosis:.4f}" if s.kurtosis is not None else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=banktech_analytics_export.csv"},
    )
