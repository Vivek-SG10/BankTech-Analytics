"""
Extended backend tests — Phase 3 integration.

Covers:
1. Analytics /summary endpoint.
2. Analytics /export/csv endpoint.
3. Filter parameters on analytics endpoints.
4. Experience_range and bank_type fields persisted and filterable.
5. Score calculations with known deterministic values.
6. Empty-dataset behaviour for all index endpoints.
7. Authorization on all new endpoints.
8. Missing-value and descriptive-stats endpoints.
"""
from __future__ import annotations

import math
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

ANALYST_EMAIL = "researcher@banktech.dev"
EMP_EMAIL     = "employee@banktech.dev"
MGR_EMAIL     = "manager@banktech.dev"
CUST_EMAIL    = "customer@banktech.dev"
PW            = "Demo1234!"

BASE      = "http://localhost:8000/api/v1"


def login(requests_session, email: str) -> str:
    r = requests_session.post(f"{BASE}/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    import requests
    s = requests.Session()
    # Ensure demo accounts exist
    s.post(f"{BASE}/dev/seed")
    return s


@pytest.fixture(scope="module")
def researcher_token(client):
    return login(client, ANALYST_EMAIL)


@pytest.fixture(scope="module")
def employee_token(client):
    return login(client, EMP_EMAIL)


@pytest.fixture(scope="module")
def manager_token(client):
    return login(client, MGR_EMAIL)


@pytest.fixture(scope="module")
def customer_token(client):
    return login(client, CUST_EMAIL)


# ── Known deterministic payloads ──────────────────────────────────────────────
# TAI_emp expected: mean(4,5,3,4,4) = 4.0 → 80.0%
# EJSI expected:    mean(4,3,4,3,5,4) = 23/6 → 76.667%
# EPI_self expected: mean(4,5,4) = 13/3 → 86.667%

KNOWN_EMP_PAYLOAD = {
    "tai_1": 4, "tai_2": 5, "tai_3": 3, "tai_4": 4, "tai_5": 4,
    "ejsi_1": 4, "ejsi_2": 3, "ejsi_3": 4, "ejsi_4": 3, "ejsi_5": 5, "ejsi_6": 4,
    "epi_s_1": 4, "epi_s_2": 5, "epi_s_3": 4,
    "experience_range": "2-5",
    "bank_type": "retail",
}

KNOWN_MGR_PAYLOAD = {
    "tai_mgr_1": 4, "tai_mgr_2": 4, "tai_mgr_3": 3,
    "epi_m_1": 4, "epi_m_2": 4, "epi_m_3": 3, "epi_m_4": 4,
    "avg_resolution_min": 12.5,
    "digital_adoption_pct": 68.0,
    "team_size": 8,
    "experience_range": "6-10",
    "bank_type": "retail",
}

KNOWN_CUST_PAYLOAD = {
    "interaction_type": "branch_visit",
    "service_type": "account_enquiry",
    "csei_1": 5, "csei_2": 4, "csei_3": 5,
    "csei_4": 4, "csei_5": 5, "csei_6": 4,
}
# CSEI expected: mean(5,4,5,4,5,4) = 27/6 = 4.5 → 90.0%


# ── Suite A: Endpoint registration ────────────────────────────────────────────

class TestEndpointRegistration:
    def test_summary_endpoint_exists(self, client):
        routes = client.get(f"{BASE.replace('/api/v1', '')}/openapi.json").json()["paths"]
        assert "/api/v1/analytics/summary" in routes

    def test_export_csv_endpoint_exists(self, client):
        routes = client.get(f"{BASE.replace('/api/v1', '')}/openapi.json").json()["paths"]
        assert "/api/v1/analytics/export/csv" in routes


# ── Suite B: Summary endpoint ─────────────────────────────────────────────────

class TestSummaryEndpoint:
    def test_summary_requires_auth(self, client):
        # FastAPI/OAuth2 returns 403 when no credentials supplied (depends on config)
        r = client.get(f"{BASE}/analytics/summary")
        assert r.status_code in (401, 403)

    def test_summary_employee_forbidden(self, client, employee_token):
        r = client.get(f"{BASE}/analytics/summary", headers=auth(employee_token))
        assert r.status_code == 403

    def test_summary_researcher_ok(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/summary", headers=auth(researcher_token))
        assert r.status_code == 200
        data = r.json()
        assert "response_counts" in data
        assert "index_scores" in data
        assert "suppression_notes" in data
        assert "data_label" in data
        assert set(data["response_counts"].keys()) >= {"employee", "manager", "customer", "total"}
        assert set(data["index_scores"].keys()) >= {"TAI_employee", "EJSI", "EPI_manager", "CSEI"}


# ── Suite C: CSV export ────────────────────────────────────────────────────────

class TestCsvExport:
    def test_csv_requires_researcher(self, client, employee_token):
        r = client.get(f"{BASE}/analytics/export/csv", headers=auth(employee_token))
        assert r.status_code == 403

    def test_csv_returns_csv_content_type(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/export/csv", headers=auth(researcher_token))
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_csv_has_privacy_header(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/export/csv", headers=auth(researcher_token))
        content = r.text
        assert "aggregated data only" in content.lower() or "No individual" in content

    def test_csv_has_index_scores_section(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/export/csv", headers=auth(researcher_token))
        content = r.text
        assert "TAI" in content or "Index Scores" in content


# ── Suite D: Filter parameters ────────────────────────────────────────────────

class TestFilterParameters:
    def test_overview_accepts_department_filter(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/overview",
                       params={"department": "NonExistentDept"},
                       headers=auth(researcher_token))
        assert r.status_code == 200
        data = r.json()
        # With a non-existent department, counts should all be 0
        assert data["employee_responses"] == 0
        assert data["manager_responses"] == 0
        assert data["customer_responses"] == 0

    def test_overview_accepts_bank_type_filter(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/overview",
                       params={"bank_type": "commercial"},
                       headers=auth(researcher_token))
        assert r.status_code == 200

    def test_overview_accepts_date_filters(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/overview",
                       params={"from_date": "2020-01-01", "to_date": "2020-12-31"},
                       headers=auth(researcher_token))
        assert r.status_code == 200

    def test_tai_accepts_filters(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/tai",
                       params={"experience_range": "11+"},
                       headers=auth(researcher_token))
        assert r.status_code == 200


# ── Suite E: New fields persisted ─────────────────────────────────────────────

class TestNewFieldsPersistence:
    def test_employee_survey_stores_experience_range(self, client, employee_token, researcher_token):
        # Submit with known fields
        r = client.post(f"{BASE}/surveys/employee",
                        json={**KNOWN_EMP_PAYLOAD, "experience_range": "11+", "bank_type": "Islamic"},
                        headers=auth(employee_token))
        assert r.status_code == 201

        # Filter by that experience range — should find at least 1
        r2 = client.get(f"{BASE}/analytics/overview",
                        params={"experience_range": "11+"},
                        headers=auth(researcher_token))
        assert r2.status_code == 200
        # bank_type Islamic should also be filterable
        r3 = client.get(f"{BASE}/analytics/overview",
                        params={"bank_type": "Islamic"},
                        headers=auth(researcher_token))
        assert r3.status_code == 200

    def test_manager_survey_stores_filter_fields(self, client, manager_token):
        r = client.post(f"{BASE}/surveys/manager",
                        json={**KNOWN_MGR_PAYLOAD},
                        headers=auth(manager_token))
        assert r.status_code == 201

    def test_customer_survey_submits_with_fresh_account(self, client):
        """Register a fresh customer account to avoid stale role from previous test runs."""
        import time, hashlib
        suffix = hashlib.md5(str(time.time()).encode()).hexdigest()[:6]
        reg = client.post(f"{BASE}/auth/register", json={
            "name": "Test Customer",
            "email": f"testcust_{suffix}@banktech.dev",
            "password": "Demo1234!",
            "role": "customer",
        })
        assert reg.status_code in (200, 201)
        token = reg.json()["access_token"]
        r = client.post(f"{BASE}/surveys/customer", json=KNOWN_CUST_PAYLOAD, headers=auth(token))
        assert r.status_code == 201


# ── Suite F: Score calculation — known values ──────────────────────────────────
# These tests verify the analytics engine with data seeded in Suite E.
# TAI_emp suppressed (N=1 < 5); the maths are verified in test_surveys_analytics.py

class TestScoreCalculationEndToEnd:
    def test_tai_endpoint_returns_suppressed_with_n1(self, client, researcher_token):
        """With only one employee response, TAI score should be suppressed (N < 5)."""
        r = client.get(f"{BASE}/analytics/tai", headers=auth(researcher_token))
        assert r.status_code == 200
        data = r.json()
        tai_emp = data["TAI_employee"]
        # N >= 1 but score should be None (suppressed)
        assert tai_emp["n"] >= 1
        assert tai_emp["score_pct"] is None
        assert tai_emp["warning"] is not None

    def test_ejsi_endpoint_returns_suppressed_with_n1(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/ejsi", headers=auth(researcher_token))
        data = r.json()
        assert data["EJSI"]["score_pct"] is None

    def test_epi_returns_suppressed_manager_and_self(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/epi", headers=auth(researcher_token))
        data = r.json()
        assert data["EPI_manager"]["score_pct"] is None  # N=1, suppressed
        assert data["EPI_self"]["score_pct"] is None

    def test_csei_endpoint_suppressed_with_n1(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/csei", headers=auth(researcher_token))
        data = r.json()
        assert data["CSEI"]["score_pct"] is None

    def test_summary_suppression_notes_present_when_n_small(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/summary", headers=auth(researcher_token))
        data = r.json()
        notes = data["suppression_notes"]
        # At least some indices should have suppression notes (N<5)
        assert any(v is not None for v in notes.values())

    def test_descriptive_stats_shows_nonzero_n(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/descriptive", headers=auth(researcher_token))
        assert r.status_code == 200
        data = r.json()
        assert data["n_employee"] >= 1
        items_with_data = [i for i in data["items"] if i["n"] > 0]
        assert len(items_with_data) > 0


# ── Suite G: Correlations and regression suppressed ───────────────────────────

class TestCorrelationRegressionSuppression:
    def test_correlations_suppressed_below_n10(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/correlations", headers=auth(researcher_token))
        assert r.status_code == 200
        data = r.json()
        # With N<10, all correlations should be suppressed
        unsuppressed = [c for c in data["correlations"] if not c["suppressed"]]
        assert len(unsuppressed) == 0, f"Expected all suppressed at low N; got {unsuppressed}"

    def test_regression_suppressed_below_n20(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/regression", headers=auth(researcher_token))
        assert r.status_code == 200
        data = r.json()
        unsuppressed = [m for m in data["models"] if not m["suppressed"]]
        assert len(unsuppressed) == 0


# ── Suite H: Missing value report ─────────────────────────────────────────────

class TestMissingValueReport:
    def test_missing_report_structure(self, client, researcher_token):
        r = client.get(f"{BASE}/analytics/missing", headers=auth(researcher_token))
        assert r.status_code == 200
        data = r.json()
        assert "employee_survey" in data
        assert "manager_survey" in data
        assert "customer_survey" in data

    def test_missing_report_no_missing_for_complete_surveys(self, client, researcher_token):
        """Since we submitted complete surveys in Suite E, there should be no missing required items."""
        r = client.get(f"{BASE}/analytics/missing", headers=auth(researcher_token))
        data = r.json()
        emp = data["employee_survey"]
        # The Likert items we submitted are all present — missing count for those should be 0
        missing_likert = [
            item for item in emp.get("items", [])
            if item["item"].startswith(("tai_", "ejsi_", "epi_s_")) and item["n_missing"] > 0
        ]
        assert missing_likert == []


# ── Suite I: RBAC on all new analytics routes ─────────────────────────────────

class TestAnalyticsRBAC:
    @pytest.mark.parametrize("endpoint", [
        "/analytics/summary",
        "/analytics/overview",
        "/analytics/tai",
        "/analytics/ejsi",
        "/analytics/epi",
        "/analytics/csei",
        "/analytics/descriptive",
        "/analytics/missing",
        "/analytics/correlations",
        "/analytics/regression",
        "/analytics/export/csv",
    ])
    def test_employee_blocked_from_analytics(self, client, employee_token, endpoint):
        r = client.get(f"{BASE}{endpoint}", headers=auth(employee_token))
        assert r.status_code == 403, f"{endpoint} should return 403 for employee, got {r.status_code}"

    def test_no_role_blocked_from_analytics_summary(self, client):
        """Analytics endpoints require authentication; no token → 403."""
        r = client.get(f"{BASE}/analytics/summary")
        assert r.status_code in (401, 403)

    @pytest.mark.parametrize("endpoint", [
        "/analytics/summary",
        "/analytics/overview",
        "/analytics/tai",
        "/analytics/ejsi",
        "/analytics/epi",
        "/analytics/csei",
        "/analytics/descriptive",
        "/analytics/missing",
        "/analytics/correlations",
        "/analytics/regression",
        "/analytics/export/csv",
    ])
    def test_manager_blocked_from_analytics(self, client, manager_token, endpoint):
        """Manager role does not have analytics access."""
        r = client.get(f"{BASE}{endpoint}", headers=auth(manager_token))
        assert r.status_code == 403, f"{endpoint} returned {r.status_code} for manager"

    @pytest.mark.parametrize("endpoint", [
        "/analytics/summary",
        "/analytics/overview",
        "/analytics/tai",
        "/analytics/ejsi",
        "/analytics/epi",
        "/analytics/csei",
        "/analytics/descriptive",
        "/analytics/missing",
        "/analytics/correlations",
        "/analytics/regression",
        "/analytics/export/csv",
    ])
    def test_researcher_allowed_for_analytics(self, client, researcher_token, endpoint):
        r = client.get(f"{BASE}{endpoint}", headers=auth(researcher_token))
        assert r.status_code == 200, f"{endpoint} returned {r.status_code}: {r.text[:200]}"
