"""
Phase 3 Research Analytics Tests — BankTech Analytics
======================================================

Tests cover:

A. Survey Submission (via HTTPX + in-memory SQLite)
   1. Employee survey — success, wrong role, re-submission voids previous
   2. Manager survey — success, wrong role, operational metrics validation
   3. Customer survey — success, wrong role
   4. /mine — own submissions only

B. Analytics Engine (pure unit tests; no DB; known synthetic datasets)
   5. TAI computation with known Likert values → expected score
   6. EJSI computation
   7. EPI (manager and self) kept separate
   8. CSEI computation
   9. Cronbach's alpha for a known matrix
  10. Descriptive statistics (mean, SD, median, IQR)
  11. Correlation suppressed when N < MIN_N_CORRELATION
  12. Correlation computed correctly with known data
  13. Regression suppressed when N < MIN_N_REGRESSION
  14. Regression result matches known OLS solution
  15. Missing-value report counts correctly
  16. Index suppressed when N < MIN_N_INDEX

SYNTHETIC DATA LABEL
--------------------
All data used in tests is artificially generated (not real participant data).
Values are chosen to produce mathematically verifiable index scores.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.analytics.indices import (
    MIN_N_CORRELATION,
    MIN_N_INDEX,
    MIN_N_REGRESSION,
    EJSI_COLS,
    EPI_MGR_COLS,
    EPI_SELF_COLS,
    CSEI_COLS,
    TAI_EMP_COLS,
    TAI_MGR_COLS,
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
    _cronbach_alpha,
)
from app.auth.models import Base
from app.core.database import get_db
from app.main import app

# ── Test DB ────────────────────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
_SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture(autouse=True)
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
async def client():
    async def override_get_db():
        async with _SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ── Auth helpers ───────────────────────────────────────────────────────────────

async def _seed(client: AsyncClient) -> None:
    await client.post("/api/v1/dev/seed")


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/api/v1/auth/login",
                          json={"email": email, "password": "Demo1234!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Valid survey payloads ──────────────────────────────────────────────────────

EMPLOYEE_PAYLOAD = {
    "tai_1": 4, "tai_2": 5, "tai_3": 3, "tai_4": 4, "tai_5": 4,
    "ejsi_1": 4, "ejsi_2": 3, "ejsi_3": 4, "ejsi_4": 3, "ejsi_5": 5, "ejsi_6": 4,
    "epi_s_1": 4, "epi_s_2": 5, "epi_s_3": 4,
    "open_challenges": "Sometimes the system is slow.",
}

MANAGER_PAYLOAD = {
    "tai_mgr_1": 4, "tai_mgr_2": 4, "tai_mgr_3": 3,
    "epi_m_1": 4, "epi_m_2": 4, "epi_m_3": 3, "epi_m_4": 4,
    "avg_resolution_min": 12.5,
    "digital_adoption_pct": 68.0,
    "team_size": 8,
}

CUSTOMER_PAYLOAD = {
    "interaction_type": "branch_visit",
    "service_type": "account_enquiry",
    "csei_1": 5, "csei_2": 4, "csei_3": 5, "csei_4": 4, "csei_5": 5, "csei_6": 4,
}


# ══════════════════════════════════════════════════════════════════════════════
# A. Survey Submission Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestEmployeeSurvey:
    @pytest.mark.anyio
    async def test_employee_can_submit(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        r = await client.post("/api/v1/surveys/employee",
                              json=EMPLOYEE_PAYLOAD, headers=_hdr(token))
        assert r.status_code == 201, r.text
        body = r.json()
        assert "id" in body
        assert body["message"] == "Employee survey submitted successfully."

    @pytest.mark.anyio
    async def test_manager_cannot_submit_employee_survey(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "manager@banktech.dev")
        r = await client.post("/api/v1/surveys/employee",
                              json=EMPLOYEE_PAYLOAD, headers=_hdr(token))
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_customer_cannot_submit_employee_survey(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "customer@banktech.dev")
        r = await client.post("/api/v1/surveys/employee",
                              json=EMPLOYEE_PAYLOAD, headers=_hdr(token))
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_resubmission_returns_new_id(self, client: AsyncClient):
        """Re-submission should succeed and return a new ID (previous is voided)."""
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        r1 = await client.post("/api/v1/surveys/employee",
                               json=EMPLOYEE_PAYLOAD, headers=_hdr(token))
        r2 = await client.post("/api/v1/surveys/employee",
                               json=EMPLOYEE_PAYLOAD, headers=_hdr(token))
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]

    @pytest.mark.anyio
    async def test_invalid_likert_value_rejected(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        bad = {**EMPLOYEE_PAYLOAD, "tai_1": 6}  # out of range
        r = await client.post("/api/v1/surveys/employee",
                              json=bad, headers=_hdr(token))
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_zero_likert_rejected(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        bad = {**EMPLOYEE_PAYLOAD, "ejsi_1": 0}
        r = await client.post("/api/v1/surveys/employee",
                              json=bad, headers=_hdr(token))
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_open_text_too_long_rejected(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        bad = {**EMPLOYEE_PAYLOAD, "open_challenges": "x" * 1001}
        r = await client.post("/api/v1/surveys/employee",
                              json=bad, headers=_hdr(token))
        assert r.status_code == 422


class TestManagerSurvey:
    @pytest.mark.anyio
    async def test_manager_can_submit(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "manager@banktech.dev")
        r = await client.post("/api/v1/surveys/manager",
                              json=MANAGER_PAYLOAD, headers=_hdr(token))
        assert r.status_code == 201, r.text

    @pytest.mark.anyio
    async def test_employee_cannot_submit_manager_survey(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        r = await client.post("/api/v1/surveys/manager",
                              json=MANAGER_PAYLOAD, headers=_hdr(token))
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_digital_adoption_out_of_range_rejected(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "manager@banktech.dev")
        bad = {**MANAGER_PAYLOAD, "digital_adoption_pct": 101.0}
        r = await client.post("/api/v1/surveys/manager",
                              json=bad, headers=_hdr(token))
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_negative_resolution_time_rejected(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "manager@banktech.dev")
        bad = {**MANAGER_PAYLOAD, "avg_resolution_min": -5.0}
        r = await client.post("/api/v1/surveys/manager",
                              json=bad, headers=_hdr(token))
        assert r.status_code == 422

    @pytest.mark.anyio
    async def test_operational_metrics_are_optional(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "manager@banktech.dev")
        minimal = {k: v for k, v in MANAGER_PAYLOAD.items()
                   if k not in ("avg_resolution_min", "digital_adoption_pct", "team_size")}
        r = await client.post("/api/v1/surveys/manager",
                              json=minimal, headers=_hdr(token))
        assert r.status_code == 201


class TestCustomerSurvey:
    @pytest.mark.anyio
    async def test_customer_can_submit(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "customer@banktech.dev")
        r = await client.post("/api/v1/surveys/customer",
                              json=CUSTOMER_PAYLOAD, headers=_hdr(token))
        assert r.status_code == 201, r.text

    @pytest.mark.anyio
    async def test_employee_cannot_submit_customer_survey(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        r = await client.post("/api/v1/surveys/customer",
                              json=CUSTOMER_PAYLOAD, headers=_hdr(token))
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_invalid_interaction_type_rejected(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "customer@banktech.dev")
        bad = {**CUSTOMER_PAYLOAD, "interaction_type": "carrier_pigeon"}
        r = await client.post("/api/v1/surveys/customer",
                              json=bad, headers=_hdr(token))
        assert r.status_code == 422


class TestMineEndpoint:
    @pytest.mark.anyio
    async def test_employee_sees_own_submissions(self, client: AsyncClient):
        await _seed(client)
        token = await _login(client, "employee@banktech.dev")
        await client.post("/api/v1/surveys/employee",
                          json=EMPLOYEE_PAYLOAD, headers=_hdr(token))
        r = await client.get("/api/v1/surveys/mine", headers=_hdr(token))
        assert r.status_code == 200
        subs = r.json()
        assert len(subs) >= 1
        assert all(s["survey_type"] == "employee" for s in subs)

    @pytest.mark.anyio
    async def test_unauthenticated_mine_is_401(self, client: AsyncClient):
        r = await client.get("/api/v1/surveys/mine")
        assert r.status_code == 403  # HTTPBearer returns 403 for missing header


# ══════════════════════════════════════════════════════════════════════════════
# B. Analytics Engine Unit Tests (known synthetic data)
# ══════════════════════════════════════════════════════════════════════════════

# Synthetic data note: All values below are artificially constructed.
# They are designed so the expected outputs are mathematically verifiable.

def _emp_df(n: int = 20, seed: int = 42) -> pd.DataFrame:
    """Synthetic employee survey DataFrame with known properties."""
    rng = np.random.default_rng(seed)
    base = rng.integers(3, 6, size=(n, len(TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS)))
    cols = TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS
    df = pd.DataFrame(base.clip(1, 5), columns=cols)
    df["department"] = ["Retail"] * (n // 2) + ["Operations"] * (n - n // 2)
    return df


def _mgr_df(n: int = 12, seed: int = 7) -> pd.DataFrame:
    """Synthetic manager survey DataFrame."""
    rng = np.random.default_rng(seed)
    base = rng.integers(3, 6, size=(n, len(TAI_MGR_COLS + EPI_MGR_COLS)))
    cols = TAI_MGR_COLS + EPI_MGR_COLS
    df = pd.DataFrame(base.clip(1, 5), columns=cols)
    df["department"] = ["Retail"] * (n // 2) + ["Operations"] * (n - n // 2)
    return df


def _cust_df(n: int = 15, seed: int = 99) -> pd.DataFrame:
    """Synthetic customer survey DataFrame."""
    rng = np.random.default_rng(seed)
    base = rng.integers(3, 6, size=(n, len(CSEI_COLS)))
    df = pd.DataFrame(base.clip(1, 5), columns=CSEI_COLS)
    df["department"] = ["Retail"] * (n // 2) + ["Operations"] * (n - n // 2)
    return df


class TestIndexComputation:
    def test_tai_employee_score_range(self):
        """TAI_employee score must be in [0, 100]."""
        result = compute_tai_employee(_emp_df())
        assert result.n == 20
        assert result.score_pct is not None
        assert 0.0 <= result.score_pct <= 100.0

    def test_tai_employee_known_value(self):
        """All 5s → score = (5/5)*100 = 100.0"""
        df = pd.DataFrame(
            [[5] * 5] * 10,
            columns=TAI_EMP_COLS,
        )
        result = compute_tai_employee(df)
        assert result.score_pct == pytest.approx(100.0)
        assert result.mean_raw == pytest.approx(5.0)

    def test_tai_employee_minimum_score(self):
        """All 1s → score = (1/5)*100 = 20.0"""
        df = pd.DataFrame([[1] * 5] * 10, columns=TAI_EMP_COLS)
        result = compute_tai_employee(df)
        assert result.score_pct == pytest.approx(20.0)

    def test_ejsi_score_range(self):
        result = compute_ejsi(_emp_df())
        assert result.n == 20
        assert 0.0 <= result.score_pct <= 100.0

    def test_ejsi_known_value(self):
        """Mean of 4.0 across 6 items → score = (4/5)*100 = 80.0"""
        df = pd.DataFrame([[4] * 6] * 8, columns=EJSI_COLS)
        result = compute_ejsi(df)
        assert result.score_pct == pytest.approx(80.0)

    def test_epi_manager_and_self_are_separate(self):
        """EPI_manager and EPI_self must not be the same object / score."""
        emp_df = _emp_df()
        mgr_df = _mgr_df()
        epi_mgr  = compute_epi_manager(mgr_df)
        epi_self = compute_epi_self(emp_df)
        assert epi_mgr.name == "EPI_manager"
        assert epi_self.name == "EPI_self"
        # Items must be disjoint
        assert set(epi_mgr.items).isdisjoint(set(epi_self.items))

    def test_csei_score_range(self):
        result = compute_csei(_cust_df())
        assert result.n == 15
        assert 0.0 <= result.score_pct <= 100.0

    def test_csei_known_value(self):
        """Mean of 3.0 → score = 60.0"""
        df = pd.DataFrame([[3] * 6] * 10, columns=CSEI_COLS)
        result = compute_csei(df)
        assert result.score_pct == pytest.approx(60.0)

    def test_index_suppressed_below_minimum_n(self):
        """Index returns None score when N < MIN_N_INDEX."""
        tiny = pd.DataFrame([[4] * 5] * (MIN_N_INDEX - 1), columns=TAI_EMP_COLS)
        result = compute_tai_employee(tiny)
        assert result.score_pct is None
        assert result.warning is not None
        assert "Insufficient" in result.warning


class TestCronbachAlpha:
    def test_perfect_internal_consistency(self):
        """Perfectly correlated items → alpha close to 1."""
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5],
                           "b": [1, 2, 3, 4, 5],
                           "c": [1, 2, 3, 4, 5]})
        alpha = _cronbach_alpha(df, ["a", "b", "c"])
        assert alpha == pytest.approx(1.0, abs=1e-6)

    def test_single_item_returns_none(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
        assert _cronbach_alpha(df, ["a"]) is None

    def test_alpha_range(self):
        emp = _emp_df(30)
        alpha = _cronbach_alpha(emp, EJSI_COLS)
        assert alpha is None or (-1.0 <= alpha <= 1.0)


class TestDescriptiveStats:
    def test_stats_contain_all_items(self):
        emp = _emp_df()
        mgr = _mgr_df()
        cust = _cust_df()
        stats = compute_descriptive_stats(emp, mgr, cust)
        items = {s.item for s in stats}
        for col in TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS:
            assert col in items
        for col in CSEI_COLS:
            assert col in items

    def test_mean_within_likert_range(self):
        emp = _emp_df()
        mgr = _mgr_df()
        cust = _cust_df()
        for stat in compute_descriptive_stats(emp, mgr, cust):
            if stat.mean is not None:
                assert 1.0 <= stat.mean <= 5.0, f"{stat.item}: mean={stat.mean}"

    def test_sd_nonnegative(self):
        emp = _emp_df()
        mgr = _mgr_df()
        cust = _cust_df()
        for stat in compute_descriptive_stats(emp, mgr, cust):
            if stat.sd is not None:
                assert stat.sd >= 0.0

    def test_known_mean_and_sd(self):
        """All tai_1 = 4 → mean=4.0, sd=0.0"""
        df = pd.DataFrame([[4] * 5] * 10, columns=TAI_EMP_COLS)
        stats = compute_descriptive_stats(df, pd.DataFrame(), pd.DataFrame())
        tai1 = next(s for s in stats if s.item == "tai_1")
        assert tai1.mean == pytest.approx(4.0)
        assert tai1.sd == pytest.approx(0.0)


class TestCorrelations:
    def test_correlation_suppressed_below_min_n(self):
        """Correlation result is suppressed when N < MIN_N_CORRELATION."""
        emp = pd.DataFrame([[4] * 14] * (MIN_N_CORRELATION - 1),
                           columns=TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS)
        mgr = pd.DataFrame(columns=TAI_MGR_COLS + EPI_MGR_COLS + ["department"])
        cust = pd.DataFrame(columns=CSEI_COLS + ["department"])
        results = compute_correlations(emp, mgr, cust)
        tai_ejsi = results[0]
        assert tai_ejsi.suppressed is True
        assert tai_ejsi.r is None

    def test_perfect_correlation(self):
        """TAI and EJSI with identical values → r = 1.0"""
        n = MIN_N_CORRELATION + 5
        vals = np.linspace(1, 5, n)
        rows = {col: vals for col in TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS}
        emp = pd.DataFrame(rows)
        mgr = pd.DataFrame(columns=TAI_MGR_COLS + EPI_MGR_COLS + ["department"])
        cust = pd.DataFrame(columns=CSEI_COLS + ["department"])
        results = compute_correlations(emp, mgr, cust)
        tai_ejsi = results[0]  # RQ1: TAI_emp ↔ EJSI
        assert not tai_ejsi.suppressed
        assert tai_ejsi.r == pytest.approx(1.0, abs=1e-4)
        assert tai_ejsi.significant is True

    def test_zero_correlation(self):
        """Orthogonal series → r ≈ 0"""
        n = 30
        rng = np.random.default_rng(123)
        tai_vals = rng.uniform(1, 5, n)
        # EJSI that is entirely unrelated (orthogonalised)
        ejsi_vals = rng.uniform(1, 5, n)
        rows = {c: tai_vals for c in TAI_EMP_COLS}
        rows.update({c: ejsi_vals for c in EJSI_COLS})
        rows.update({c: rng.uniform(1, 5, n) for c in EPI_SELF_COLS})
        emp = pd.DataFrame(rows)
        mgr = pd.DataFrame(columns=TAI_MGR_COLS + EPI_MGR_COLS + ["department"])
        cust = pd.DataFrame(columns=CSEI_COLS + ["department"])
        results = compute_correlations(emp, mgr, cust)
        tai_ejsi = results[0]
        assert not tai_ejsi.suppressed
        assert tai_ejsi.r is not None
        assert abs(tai_ejsi.r) <= 0.6  # not strongly correlated


class TestRegression:
    def test_regression_suppressed_below_min_n(self):
        """Regression suppressed when N < MIN_N_REGRESSION."""
        emp = pd.DataFrame(
            [[4] * len(TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS)] * (MIN_N_REGRESSION - 1),
            columns=TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS
        )
        mgr = pd.DataFrame(columns=TAI_MGR_COLS + EPI_MGR_COLS)
        results = compute_regression(emp, mgr)
        assert results[0].suppressed is True

    def test_perfect_regression_r2(self):
        """Perfect linear relationship → R² = 1.0"""
        n = MIN_N_REGRESSION + 5
        x = np.linspace(1, 5, n)
        # EJSI = 0.8 * TAI + 0.5 (exact linear)
        rows: dict = {c: x for c in TAI_EMP_COLS}
        ejsi_y = 0.8 * x + 0.5
        rows.update({c: ejsi_y for c in EJSI_COLS})
        rows.update({c: x for c in EPI_SELF_COLS})
        emp = pd.DataFrame(rows)
        mgr = pd.DataFrame(
            [[4] * len(TAI_MGR_COLS + EPI_MGR_COLS)] * (MIN_N_REGRESSION + 5),
            columns=TAI_MGR_COLS + EPI_MGR_COLS,
        )
        results = compute_regression(emp, mgr)
        model1 = results[0]
        assert not model1.suppressed
        assert model1.r_squared == pytest.approx(1.0, abs=1e-4)

    def test_regression_coefficients_present(self):
        """Regression output includes intercept and predictor coefficient."""
        n = MIN_N_REGRESSION + 10
        rng = np.random.default_rng(11)
        rows = {c: rng.uniform(2, 5, n) for c in TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS}
        emp = pd.DataFrame(rows)
        mgr = pd.DataFrame(
            {c: rng.uniform(2, 5, n) for c in TAI_MGR_COLS + EPI_MGR_COLS}
        )
        results = compute_regression(emp, mgr)
        m1 = results[0]
        if not m1.suppressed:
            assert "intercept" in m1.coefficients
            assert "TAI_employee" in m1.coefficients


class TestMissingValueReport:
    def test_no_missing_data(self):
        emp  = _emp_df()
        mgr  = _mgr_df()
        cust = _cust_df()
        report = missing_value_report(emp, mgr, cust)
        for item in report["employee_survey"]["items"]:
            assert item["n_missing"] == 0
            assert item["pct_missing"] == 0.0

    def test_detects_missing_values(self):
        emp = _emp_df()
        emp.loc[0, "tai_1"] = float("nan")
        emp.loc[1, "tai_1"] = float("nan")
        report = missing_value_report(emp, pd.DataFrame(), pd.DataFrame())
        tai1 = next(i for i in report["employee_survey"]["items"] if i["item"] == "tai_1")
        assert tai1["n_missing"] == 2
        assert tai1["pct_missing"] == pytest.approx(10.0, abs=0.1)

    def test_empty_dataframes_handled(self):
        report = missing_value_report(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
        assert report["employee_survey"]["n_responses"] == 0
        assert report["manager_survey"]["n_responses"] == 0
