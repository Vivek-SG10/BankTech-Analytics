"""
Survey CRUD — async database operations for survey submission and retrieval.

All functions accept an AsyncSession and return ORM objects.
Business logic (index computation, aggregation) lives in analytics/indices.py.

Privacy rules enforced here
---------------------------
- Submissions store respondent_id (UUID), NOT names or email addresses.
- One active submission per respondent per survey type is enforced:
  submitting again voids the previous response so analyses always use
  the latest response per person.
- list_all_* functions are restricted to admin/researcher callers (enforced
  in router.py via require_roles dependency).
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.surveys.models import CustomerSurveyOrm, EmployeeSurveyOrm, ManagerSurveyOrm


# ── Employee Survey ────────────────────────────────────────────────────────────

async def create_employee_survey(
    db: AsyncSession,
    respondent_id: str,
    department: str | None,
    data: dict,
) -> EmployeeSurveyOrm:
    """
    Persist an employee survey response.
    Voids any previous active submission by the same respondent.
    """
    # Void previous
    await db.execute(
        update(EmployeeSurveyOrm)
        .where(EmployeeSurveyOrm.respondent_id == respondent_id,
               EmployeeSurveyOrm.is_voided == False)  # noqa: E712
        .values(is_voided=True)
    )
    row = EmployeeSurveyOrm(
        respondent_id=respondent_id,
        department=department,
        **data,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_employee_submissions_by_respondent(
    db: AsyncSession, respondent_id: str
) -> list[EmployeeSurveyOrm]:
    result = await db.execute(
        select(EmployeeSurveyOrm)
        .where(EmployeeSurveyOrm.respondent_id == respondent_id)
        .order_by(EmployeeSurveyOrm.submitted_at.desc())
    )
    return list(result.scalars().all())


async def list_all_employee_surveys(db: AsyncSession) -> list[EmployeeSurveyOrm]:
    """Admin/researcher only — returns all non-voided employee responses."""
    result = await db.execute(
        select(EmployeeSurveyOrm)
        .where(EmployeeSurveyOrm.is_voided == False)  # noqa: E712
        .order_by(EmployeeSurveyOrm.submitted_at)
    )
    return list(result.scalars().all())


# ── Manager Survey ─────────────────────────────────────────────────────────────

async def create_manager_survey(
    db: AsyncSession,
    respondent_id: str,
    department: str | None,
    data: dict,
) -> ManagerSurveyOrm:
    await db.execute(
        update(ManagerSurveyOrm)
        .where(ManagerSurveyOrm.respondent_id == respondent_id,
               ManagerSurveyOrm.is_voided == False)  # noqa: E712
        .values(is_voided=True)
    )
    row = ManagerSurveyOrm(
        respondent_id=respondent_id,
        department=department,
        **data,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_manager_submissions_by_respondent(
    db: AsyncSession, respondent_id: str
) -> list[ManagerSurveyOrm]:
    result = await db.execute(
        select(ManagerSurveyOrm)
        .where(ManagerSurveyOrm.respondent_id == respondent_id)
        .order_by(ManagerSurveyOrm.submitted_at.desc())
    )
    return list(result.scalars().all())


async def list_all_manager_surveys(db: AsyncSession) -> list[ManagerSurveyOrm]:
    result = await db.execute(
        select(ManagerSurveyOrm)
        .where(ManagerSurveyOrm.is_voided == False)  # noqa: E712
        .order_by(ManagerSurveyOrm.submitted_at)
    )
    return list(result.scalars().all())


# ── Customer Survey ────────────────────────────────────────────────────────────

async def create_customer_survey(
    db: AsyncSession,
    respondent_id: str,
    department: str | None,
    data: dict,
) -> CustomerSurveyOrm:
    # Customers may submit multiple times (different interactions)
    # but we still void previous to keep only latest per research analysis
    await db.execute(
        update(CustomerSurveyOrm)
        .where(CustomerSurveyOrm.respondent_id == respondent_id,
               CustomerSurveyOrm.is_voided == False)  # noqa: E712
        .values(is_voided=True)
    )
    row = CustomerSurveyOrm(
        respondent_id=respondent_id,
        department=department,
        **data,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_customer_submissions_by_respondent(
    db: AsyncSession, respondent_id: str
) -> list[CustomerSurveyOrm]:
    result = await db.execute(
        select(CustomerSurveyOrm)
        .where(CustomerSurveyOrm.respondent_id == respondent_id)
        .order_by(CustomerSurveyOrm.submitted_at.desc())
    )
    return list(result.scalars().all())


async def list_all_customer_surveys(db: AsyncSession) -> list[CustomerSurveyOrm]:
    result = await db.execute(
        select(CustomerSurveyOrm)
        .where(CustomerSurveyOrm.is_voided == False)  # noqa: E712
        .order_by(CustomerSurveyOrm.submitted_at)
    )
    return list(result.scalars().all())
