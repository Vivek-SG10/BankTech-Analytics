"""
Pydantic schemas for survey submission validation.

Design principles
-----------------
- Likert items are validated as integers in [1, 5].
- All required fields are explicit; optional fields default to None.
- Open-text fields are length-capped to prevent storage abuse.
- Interaction / service type fields use constrained literals.
- Role enforcement (who may submit which survey) is handled in router.py.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Likert field type alias ────────────────────────────────────────────────────
Likert = int  # validated below; range 1–5

def _validate_likert(value: int, name: str) -> int:
    if value not in (1, 2, 3, 4, 5):
        raise ValueError(f"{name} must be an integer between 1 and 5 (got {value})")
    return value


# ── Employee Survey ────────────────────────────────────────────────────────────

class EmployeeSurveyRequest(BaseModel):
    """
    Submitted by an authenticated employee.

    Scale for all Likert items:
      1 = Strongly Disagree
      2 = Disagree
      3 = Neither Agree nor Disagree
      4 = Agree
      5 = Strongly Agree
    """
    # Section A — Technology Adoption (TAI_employee)
    tai_1: Likert = Field(..., ge=1, le=5,
        description="The digital banking tools I use daily are easy to operate.")
    tai_2: Likert = Field(..., ge=1, le=5,
        description="Using digital tools makes my daily tasks more efficient.")
    tai_3: Likert = Field(..., ge=1, le=5,
        description="I receive sufficient training to use banking technology confidently.")
    tai_4: Likert = Field(..., ge=1, le=5,
        description="I regularly use digital tools for customer-facing tasks.")
    tai_5: Likert = Field(..., ge=1, le=5,
        description="Technology enables me to resolve customer queries more quickly.")

    # Section B — Job Satisfaction (EJSI)
    ejsi_1: Likert = Field(..., ge=1, le=5,
        description="Overall, I am satisfied with my current role.")
    ejsi_2: Likert = Field(..., ge=1, le=5,
        description="I feel valued as an employee of this organisation.")
    ejsi_3: Likert = Field(..., ge=1, le=5,
        description="I am satisfied with the support I receive from my manager.")
    ejsi_4: Likert = Field(..., ge=1, le=5,
        description="My workload is manageable within normal working hours.")
    ejsi_5: Likert = Field(..., ge=1, le=5,
        description="My work is meaningful and contributes to organisational goals.")
    ejsi_6: Likert = Field(..., ge=1, le=5,
        description="I would recommend this organisation as a good place to work.")

    # Section C — Self-assessed Performance (EPI_self — reported separately)
    epi_s_1: Likert = Field(..., ge=1, le=5,
        description="I consistently meet my individual performance targets.")
    epi_s_2: Likert = Field(..., ge=1, le=5,
        description="I handle customer queries and complaints effectively.")
    epi_s_3: Likert = Field(..., ge=1, le=5,
        description="I collaborate effectively with colleagues to achieve team goals.")

    # Optional open-ended
    open_challenges: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional: biggest challenges using banking technology (max 1000 chars).",
    )

    # ── Optional classification fields (enable analytics filters) ─────────────
    experience_range: Literal["0-1", "2-5", "6-10", "11+"] | None = Field(
        default=None,
        description="Self-reported years of experience in banking (grouped for anonymity).",
    )
    bank_type: Literal["retail", "commercial", "investment", "Islamic", "cooperative"] | None = Field(
        default=None,
        description="Type of banking institution.",
    )


class EmployeeSurveyResponse(BaseModel):
    id: str
    respondent_id: str
    submitted_at: str
    message: str = "Employee survey submitted successfully."


# ── Manager Survey ─────────────────────────────────────────────────────────────

class ManagerSurveyRequest(BaseModel):
    """
    Submitted by an authenticated manager/supervisor.

    Likert scale: 1 (Strongly Disagree) … 5 (Strongly Agree).

    Operational metrics (Sections C) are optional aggregated branch-level
    figures — not individual employee data.
    """
    # Section A — Technology Assessment of Team (TAI_manager)
    tai_mgr_1: Likert = Field(..., ge=1, le=5,
        description="My team effectively uses the digital banking tools available.")
    tai_mgr_2: Likert = Field(..., ge=1, le=5,
        description="Technology adoption has improved my team's overall productivity.")
    tai_mgr_3: Likert = Field(..., ge=1, le=5,
        description="The technology training provided is adequate for my team's needs.")

    # Section B — Performance Assessment of Team (EPI_manager)
    epi_m_1: Likert = Field(..., ge=1, le=5,
        description="My team members consistently meet their individual targets.")
    epi_m_2: Likert = Field(..., ge=1, le=5,
        description="My team handles customer queries and complaints effectively.")
    epi_m_3: Likert = Field(..., ge=1, le=5,
        description="My team adapts well to changes introduced by new technology.")
    epi_m_4: Likert = Field(..., ge=1, le=5,
        description="Overall, I rate my team's performance as: (1=Poor … 5=Excellent)")

    # Section C — Aggregated Operational Metrics (optional)
    avg_resolution_min: float | None = Field(
        default=None, gt=0,
        description="Mean customer query resolution time for the team (minutes). "
                    "Report team average, not individual values.",
    )
    digital_adoption_pct: float | None = Field(
        default=None, ge=0, le=100,
        description="Percentage of customer transactions via digital channels "
                    "for your branch this month (0–100).",
    )
    team_size: int | None = Field(
        default=None, ge=1, le=500,
        description="Number of direct reports in your team.",
    )
    experience_range: Literal["0-1", "2-5", "6-10", "11+"] | None = Field(
        default=None,
        description="Self-reported years of managerial experience in banking.",
    )
    bank_type: Literal["retail", "commercial", "investment", "Islamic", "cooperative"] | None = Field(
        default=None,
        description="Type of banking institution.",
    )

class ManagerSurveyResponse(BaseModel):
    id: str
    respondent_id: str
    submitted_at: str
    message: str = "Manager survey submitted successfully."


# ── Customer Survey ────────────────────────────────────────────────────────────

InteractionType = Literal["branch_visit", "phone", "digital_channel", "other"]
ServiceType     = Literal["account_enquiry", "transaction", "complaint",
                           "digital_onboarding", "other"]


class CustomerSurveyRequest(BaseModel):
    """
    Submitted by an authenticated customer after a service interaction.
    Contributes to CSEI (Customer Service Effectiveness Index).

    No staff member is identified — responses are aggregated at branch level.

    Likert scale: 1 (Strongly Disagree) … 5 (Strongly Agree).
    """
    interaction_type: InteractionType = Field(
        ..., description="How did you interact with the bank today?")
    service_type: ServiceType = Field(
        ..., description="What was the purpose of your visit/contact?")

    # CSEI items
    csei_1: Likert = Field(..., ge=1, le=5,
        description="The staff member who assisted me was knowledgeable about digital services.")
    csei_2: Likert = Field(..., ge=1, le=5,
        description="My query was resolved efficiently without unnecessary delays.")
    csei_3: Likert = Field(..., ge=1, le=5,
        description="I am satisfied with the overall quality of service I received.")
    csei_4: Likert = Field(..., ge=1, le=5,
        description="The staff member helped me understand or use digital banking channels.")
    csei_5: Likert = Field(..., ge=1, le=5,
        description="The service met my expectations.")
    csei_6: Likert = Field(..., ge=1, le=5,
        description="I would recommend this branch to friends or family.")

    open_feedback: str | None = Field(
        default=None,
        max_length=500,
        description="Optional: any additional feedback (max 500 chars).",
    )


class CustomerSurveyResponse(BaseModel):
    id: str
    respondent_id: str
    submitted_at: str
    message: str = "Customer survey submitted successfully."


# ── My submissions ─────────────────────────────────────────────────────────────

class SubmissionSummary(BaseModel):
    """Lightweight record of own past submissions."""
    id: str
    survey_type: Literal["employee", "manager", "customer"]
    submitted_at: str
    is_voided: bool
