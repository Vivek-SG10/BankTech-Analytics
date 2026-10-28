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
