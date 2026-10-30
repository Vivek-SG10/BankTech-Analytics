"""
Survey submission endpoints.

  POST /api/v1/surveys/employee  — employee only
  POST /api/v1/surveys/manager   — manager only
  POST /api/v1/surveys/customer  — customer only
  GET  /api/v1/surveys/mine      — any authenticated user; own submissions only

Role enforcement: require_roles dependency blocks wrong-role callers at 403.
Submissions return the new record's ID and timestamp only — no other user data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_roles
from app.auth.models import UserOrm
from app.core.database import get_db
from app.surveys.crud import (
    create_customer_survey,
    create_employee_survey,
    create_manager_survey,
    get_customer_submissions_by_respondent,
    get_employee_submissions_by_respondent,
    get_manager_submissions_by_respondent,
    list_all_customer_surveys,
    list_all_employee_surveys,
    list_all_manager_surveys,
)
from app.surveys.schemas import (
    CustomerSurveyRequest,
    CustomerSurveyResponse,
    EmployeeSurveyRequest,
    EmployeeSurveyResponse,
    ManagerSurveyRequest,
    ManagerSurveyResponse,
    SubmissionSummary,
)

survey_router = APIRouter()


# ── Submit employee survey ─────────────────────────────────────────────────────

@survey_router.post(
    "/employee",
    response_model=EmployeeSurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit employee survey",
    description=(
        "Authenticated employees submit their technology adoption, job satisfaction "
        "and self-assessed performance survey. Re-submission voids the previous response."
    ),
)
async def submit_employee_survey(
    body: EmployeeSurveyRequest,
    actor: UserOrm = Depends(require_roles("employee")),
    db: AsyncSession = Depends(get_db),
) -> EmployeeSurveyResponse:
    data = body.model_dump(exclude_none=True)
    row = await create_employee_survey(
        db,
        respondent_id=actor.id,
        department=actor.department,
        data=data,
    )
    return EmployeeSurveyResponse(
        id=row.id,
        respondent_id=row.respondent_id,
        submitted_at=row.submitted_at.isoformat(),
    )


# ── Submit manager survey ──────────────────────────────────────────────────────

@survey_router.post(
    "/manager",
    response_model=ManagerSurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit manager survey",
    description=(
        "Authenticated managers submit team technology assessment, performance "
        "assessment and optional aggregated operational metrics."
    ),
)
async def submit_manager_survey(
    body: ManagerSurveyRequest,
    actor: UserOrm = Depends(require_roles("manager")),
    db: AsyncSession = Depends(get_db),
) -> ManagerSurveyResponse:
    data = body.model_dump(exclude_none=True)
    row = await create_manager_survey(
        db,
        respondent_id=actor.id,
        department=actor.department,
        data=data,
    )
    return ManagerSurveyResponse(
        id=row.id,
        respondent_id=row.respondent_id,
        submitted_at=row.submitted_at.isoformat(),
    )


# ── Submit customer survey ─────────────────────────────────────────────────────

@survey_router.post(
    "/customer",
    response_model=CustomerSurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit customer service survey",
    description=(
        "Authenticated customers submit a service effectiveness survey. "
        "No individual staff members are identified in responses."
    ),
)
async def submit_customer_survey(
    body: CustomerSurveyRequest,
    actor: UserOrm = Depends(require_roles("customer")),
    db: AsyncSession = Depends(get_db),
) -> CustomerSurveyResponse:
    data = body.model_dump(exclude_none=True)
    row = await create_customer_survey(
        db,
        respondent_id=actor.id,
        department=actor.department,
        data=data,
    )
    return CustomerSurveyResponse(
        id=row.id,
        respondent_id=row.respondent_id,
        submitted_at=row.submitted_at.isoformat(),
    )


# ── List own submissions ───────────────────────────────────────────────────────

@survey_router.get(
    "/mine",
    response_model=list[SubmissionSummary],
    summary="List my own survey submissions",
    description="Returns all submissions by the currently authenticated user.",
)
async def list_my_submissions(
    current_user: UserOrm = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SubmissionSummary]:
    summaries: list[SubmissionSummary] = []

    if current_user.role == "employee":
        rows = await get_employee_submissions_by_respondent(db, current_user.id)
        for r in rows:
            summaries.append(SubmissionSummary(
                id=r.id, survey_type="employee",
                submitted_at=r.submitted_at.isoformat(),
                is_voided=r.is_voided,
            ))

    elif current_user.role == "manager":
        rows = await get_manager_submissions_by_respondent(db, current_user.id)
        for r in rows:
            summaries.append(SubmissionSummary(
                id=r.id, survey_type="manager",
                submitted_at=r.submitted_at.isoformat(),
                is_voided=r.is_voided,
            ))

    elif current_user.role == "customer":
        rows = await get_customer_submissions_by_respondent(db, current_user.id)
        for r in rows:
            summaries.append(SubmissionSummary(
                id=r.id, survey_type="customer",
                submitted_at=r.submitted_at.isoformat(),
                is_voided=r.is_voided,
            ))

    return summaries


# ── Admin: List all submitted surveys with detailed answers ─────────────────────

@survey_router.get(
    "/submissions",
    summary="[Admin] List all submitted surveys with answers",
    description="Returns all submitted surveys across employee, manager, and customer roles for admin review.",
)
async def list_all_submissions(
    actor: UserOrm = Depends(require_roles("admin", "researcher")),
    db: AsyncSession = Depends(get_db),
):
    emp_rows = await list_all_employee_surveys(db)
    mgr_rows = await list_all_manager_surveys(db)
    cust_rows = await list_all_customer_surveys(db)

    def serialize_emp(r):
        scores = {
            "tai_1": r.tai_1, "tai_2": r.tai_2, "tai_3": r.tai_3, "tai_4": r.tai_4, "tai_5": r.tai_5,
            "ejsi_1": r.ejsi_1, "ejsi_2": r.ejsi_2, "ejsi_3": r.ejsi_3, "ejsi_4": r.ejsi_4, "ejsi_5": r.ejsi_5, "ejsi_6": r.ejsi_6,
            "epi_s_1": r.epi_s_1, "epi_s_2": r.epi_s_2, "epi_s_3": r.epi_s_3,
        }
        valid_vals = [v for v in scores.values() if v is not None]
        avg = round(sum(valid_vals) / len(valid_vals), 2) if valid_vals else 0.0
        return {
            "id": str(r.id),
            "survey_type": "employee",
            "respondent_id": str(r.respondent_id),
            "department": r.department or "General",
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else "",
            "is_voided": r.is_voided,
            "experience_range": r.experience_range,
            "bank_type": r.bank_type,
            "open_feedback": r.open_challenges,
            "avg_score": avg,
            "scores": scores,
        }

    def serialize_mgr(r):
        scores = {
            "tai_mgr_1": r.tai_mgr_1, "tai_mgr_2": r.tai_mgr_2, "tai_mgr_3": r.tai_mgr_3,
            "epi_m_1": r.epi_m_1, "epi_m_2": r.epi_m_2, "epi_m_3": r.epi_m_3, "epi_m_4": r.epi_m_4,
        }
        valid_vals = [v for v in scores.values() if v is not None]
        avg = round(sum(valid_vals) / len(valid_vals), 2) if valid_vals else 0.0
        return {
            "id": str(r.id),
            "survey_type": "manager",
            "respondent_id": str(r.respondent_id),
            "department": r.department or "Management",
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else "",
            "is_voided": r.is_voided,
            "experience_range": r.experience_range,
            "bank_type": r.bank_type,
            "avg_resolution_min": r.avg_resolution_min,
            "digital_adoption_pct": r.digital_adoption_pct,
            "team_size": r.team_size,
            "open_feedback": f"Team Size: {r.team_size or 'N/A'}, Digital Adoption: {r.digital_adoption_pct or 'N/A'}%" if (r.team_size or r.digital_adoption_pct) else None,
            "avg_score": avg,
            "scores": scores,
        }

    def serialize_cust(r):
        scores = {
            "csei_1": r.csei_1, "csei_2": r.csei_2, "csei_3": r.csei_3,
            "csei_4": r.csei_4, "csei_5": r.csei_5, "csei_6": r.csei_6,
        }
        valid_vals = [v for v in scores.values() if v is not None]
        avg = round(sum(valid_vals) / len(valid_vals), 2) if valid_vals else 0.0
        return {
            "id": str(r.id),
            "survey_type": "customer",
            "respondent_id": str(r.respondent_id),
            "department": r.department or "Retail Branch",
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else "",
            "is_voided": r.is_voided,
            "interaction_type": r.interaction_type,
            "service_type": r.service_type,
            "open_feedback": r.open_feedback,
            "avg_score": avg,
            "scores": scores,
        }

    employee_list = [serialize_emp(r) for r in emp_rows]
    manager_list = [serialize_mgr(r) for r in mgr_rows]
    customer_list = [serialize_cust(r) for r in cust_rows]

    all_submissions = sorted(
        employee_list + manager_list + customer_list,
        key=lambda x: x["submitted_at"],
        reverse=True,
    )

    return {
        "total": len(all_submissions),
        "counts": {
            "employee": len(employee_list),
            "manager": len(manager_list),
            "customer": len(customer_list),
        },
        "all": all_submissions,
        "employee": employee_list,
        "manager": manager_list,
        "customer": customer_list,
    }
