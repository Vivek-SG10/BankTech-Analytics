"""
Survey and analytics ORM models.

Three survey types:
  EmployeeSurveyOrm  — submitted by employees (role: employee)
  ManagerSurveyOrm   — submitted by managers (role: manager)
  CustomerSurveyOrm  — submitted by customers (role: customer)

Schema rationale
----------------
Employee and manager surveys use five-point Likert items (1–5).
Customer surveys also use five-point Likert items plus categorical fields.
Manager surveys additionally capture approved aggregated operational metrics
at the branch/team level (not individual employee data).

All personal identifiers are limited to what is already stored in the users
table (id, department).  No names, email addresses, or employee IDs are
stored directly inside survey rows to minimise re-identification risk.

See analytics/indices.py for index computation details.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.auth.models import Base

# ── Shared helpers ─────────────────────────────────────────────────────────────

def _likert(name: str) -> Column:
    """Integer column constrained to 1–5 (Likert scale)."""
    return Column(
        Integer,
        CheckConstraint(f"{name} BETWEEN 1 AND 5", name=f"ck_{name}_likert"),
        nullable=False,
    )

def _likert_opt(name: str) -> Column:
    """Optional integer column constrained to 1–5."""
    return Column(
        Integer,
        CheckConstraint(f"{name} IS NULL OR {name} BETWEEN 1 AND 5", name=f"ck_{name}_likert_opt"),
        nullable=True,
    )


# ── Employee Survey ────────────────────────────────────────────────────────────

class EmployeeSurveyOrm(Base):
    """
    Employee self-report survey.

    Section A — Technology Adoption (contributes to TAI_employee)
    tai_1..5: five items measuring perceived usefulness and ease of use of
              banking technology.  Based on Davis (1989) TAM constructs.

    Section B — Job Satisfaction (contributes to EJSI)
    ejsi_1..6: six items measuring overall satisfaction, management support,
               workload, meaningfulness and organisational commitment.
               Based on validated facets of the Job Descriptive Index.

    Section C — Self-assessed Performance (EPI_self, kept separate from
                 manager assessment; reported independently per scientific protocol)
    epi_s_1..3: three items on target attainment, customer handling, teamwork.

    All items: 1 = Strongly Disagree … 5 = Strongly Agree.
    """
    __tablename__ = "survey_employee"

    id: str = Column(UUID(as_uuid=False), primary_key=True,
                     default=lambda: str(uuid.uuid4()))
    respondent_id: str = Column(UUID(as_uuid=False), nullable=False, index=True)
    department: str | None = Column(String(100), nullable=True, index=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # prevent duplicate submissions (one active per respondent)
    is_voided: bool = Column(Boolean, nullable=False, default=False)

    # ── Section A: Technology Adoption ────────────────────────────────────
    # tai_1: "The digital banking tools I use daily are easy to operate."
    tai_1 = _likert("tai_1")
    # tai_2: "Using digital tools makes my daily tasks more efficient."
    tai_2 = _likert("tai_2")
    # tai_3: "I receive sufficient training to use banking technology confidently."
    tai_3 = _likert("tai_3")
    # tai_4: "I regularly use digital tools for customer-facing tasks."
    tai_4 = _likert("tai_4")
    # tai_5: "Technology enables me to resolve customer queries more quickly."
    tai_5 = _likert("tai_5")

    # ── Section B: Job Satisfaction ───────────────────────────────────────
    # ejsi_1: "Overall, I am satisfied with my current role."
    ejsi_1 = _likert("ejsi_1")
    # ejsi_2: "I feel valued as an employee of this organisation."
    ejsi_2 = _likert("ejsi_2")
    # ejsi_3: "I am satisfied with the support I receive from my manager."
    ejsi_3 = _likert("ejsi_3")
    # ejsi_4: "My workload is manageable within normal working hours."
    ejsi_4 = _likert("ejsi_4")
    # ejsi_5: "My work is meaningful and contributes to organisational goals."
    ejsi_5 = _likert("ejsi_5")
    # ejsi_6: "I would recommend this organisation as a good place to work."
    ejsi_6 = _likert("ejsi_6")

    # ── Section C: Self-assessed Performance ──────────────────────────────
    # epi_s_1: "I consistently meet my individual performance targets."
    epi_s_1 = _likert("epi_s_1")
    # epi_s_2: "I handle customer queries and complaints effectively."
    epi_s_2 = _likert("epi_s_2")
    # epi_s_3: "I collaborate effectively with colleagues to achieve team goals."
    epi_s_3 = _likert("epi_s_3")

    # ── Open-ended (optional, limited length) ─────────────────────────────
    open_challenges: str | None = Column(Text, nullable=True)   # max enforced in schema

    # ── Classification fields (for analytics filters) ─────────────────────
    experience_range: str | None = Column(String(10), nullable=True)
    bank_type: str | None = Column(String(30), nullable=True)


# ── Manager Survey ─────────────────────────────────────────────────────────────

class ManagerSurveyOrm(Base):
    """
    Manager/supervisor survey.

    Section A — Technology Assessment of Team (contributes to TAI_manager)
    tai_mgr_1..3: three items on team technology adoption.

    Section B — Performance Assessment of Team (contributes to EPI_manager)
    epi_m_1..4: four items on team performance.

    IMPORTANT: Manager assesses the TEAM (aggregated), not named individuals.
    The 'department' field links the response to a branch/team for aggregation.

    Section C — Approved Aggregated Operational Metrics
    These are branch-level figures (not individual employee data):
      avg_resolution_min   — mean customer query resolution time (minutes)
      digital_adoption_pct — % of customer transactions via digital channels (0–100)
      team_size            — number of direct reports (1–200)
    Managers are instructed to report team-level aggregates only.
    """
    __tablename__ = "survey_manager"

    id: str = Column(UUID(as_uuid=False), primary_key=True,
                     default=lambda: str(uuid.uuid4()))
    respondent_id: str = Column(UUID(as_uuid=False), nullable=False, index=True)
    department: str | None = Column(String(100), nullable=True, index=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_voided: bool = Column(Boolean, nullable=False, default=False)

    # ── Section A: Technology Assessment ──────────────────────────────────
    # tai_mgr_1: "My team effectively uses the digital banking tools available."
    tai_mgr_1 = _likert("tai_mgr_1")
    # tai_mgr_2: "Technology adoption has improved my team's overall productivity."
    tai_mgr_2 = _likert("tai_mgr_2")
    # tai_mgr_3: "The technology training provided is adequate for my team's needs."
    tai_mgr_3 = _likert("tai_mgr_3")

    # ── Section B: Performance Assessment ─────────────────────────────────
    # epi_m_1: "My team members consistently meet their individual targets."
    epi_m_1 = _likert("epi_m_1")
    # epi_m_2: "My team handles customer queries and complaints effectively."
    epi_m_2 = _likert("epi_m_2")
    # epi_m_3: "My team adapts well to changes introduced by new technology."
    epi_m_3 = _likert("epi_m_3")
    # epi_m_4: "Overall, I rate my team's performance as..."
    epi_m_4 = _likert("epi_m_4")

    # ── Section C: Aggregated Operational Metrics ─────────────────────────
    # Average customer query resolution time for the team (minutes); nullable
    avg_resolution_min: float | None = Column(
        Float,
        CheckConstraint("avg_resolution_min IS NULL OR avg_resolution_min > 0",
                        name="ck_avg_resolution_positive"),
        nullable=True,
    )
    # Percentage of transactions via digital channels (0–100); nullable
    digital_adoption_pct: float | None = Column(
        Float,
        CheckConstraint(
            "digital_adoption_pct IS NULL OR (digital_adoption_pct BETWEEN 0 AND 100)",
            name="ck_digital_adoption_range",
        ),
        nullable=True,
    )
    # Number of direct reports
    team_size: int | None = Column(
        Integer,
        CheckConstraint("team_size IS NULL OR (team_size BETWEEN 1 AND 500)",
                        name="ck_team_size_range"),
        nullable=True,
    )

    # ── Classification fields (for analytics filters) ─────────────────────────
    experience_range: str | None = Column(String(10), nullable=True)
    bank_type: str | None = Column(String(30), nullable=True)


# ── Customer Survey ────────────────────────────────────────────────────────────

class CustomerSurveyOrm(Base):
    """
    Customer service effectiveness survey.

    Submitted by authenticated customers after a service interaction.
    Contributes to CSEI (Customer Service Effectiveness Index).

    IMPORTANT: Customers are not required to provide their employee's name.
    Responses are linked to the branch (department) via the customer's profile,
    not to a specific employee — preventing individual staff re-identification.

    Items: 1 = Strongly Disagree … 5 = Strongly Agree.
    """
    __tablename__ = "survey_customer"

    id: str = Column(UUID(as_uuid=False), primary_key=True,
                     default=lambda: str(uuid.uuid4()))
    respondent_id: str = Column(UUID(as_uuid=False), nullable=False, index=True)
    department: str | None = Column(String(100), nullable=True, index=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_voided: bool = Column(Boolean, nullable=False, default=False)

    # Interaction context (categorical, not identifying)
    interaction_type: str = Column(
        String(30),
        CheckConstraint(
            "interaction_type IN ('branch_visit','phone','digital_channel','other')",
            name="ck_interaction_type",
        ),
        nullable=False,
    )
    service_type: str = Column(
        String(30),
        CheckConstraint(
            "service_type IN ('account_enquiry','transaction','complaint',"
            "'digital_onboarding','other')",
            name="ck_service_type",
        ),
        nullable=False,
    )

    # ── CSEI items ─────────────────────────────────────────────────────────
    # csei_1: "The staff member who assisted me was knowledgeable about digital services."
    csei_1 = _likert("csei_1")
    # csei_2: "My query was resolved efficiently without unnecessary delays."
    csei_2 = _likert("csei_2")
    # csei_3: "I am satisfied with the overall quality of service I received."
    csei_3 = _likert("csei_3")
    # csei_4: "The staff member helped me understand or use digital banking channels."
    csei_4 = _likert("csei_4")
    # csei_5: "The service met my expectations."
    csei_5 = _likert("csei_5")
    # csei_6: "I would recommend this branch to friends or family."
    csei_6 = _likert("csei_6")

    open_feedback: str | None = Column(Text, nullable=True)
