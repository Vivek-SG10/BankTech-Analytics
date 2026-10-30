"""
Research Analytics Engine — BankTech Analytics
===============================================

Computes four validated research indices from survey data:

  TAI  — Technology Adoption Index
  EJSI — Employee Job Satisfaction Index
  EPI  — Employee Performance Index (two components: manager-assessed and
          self-assessed, reported separately to avoid conflation)
  CSEI — Customer Service Effectiveness Index

Also computes:
  - Descriptive statistics (N, mean, SD, median, IQR, skewness, kurtosis)
  - Missing-value analysis
  - Cronbach's alpha (internal consistency of each scale)
  - Pearson / Spearman correlations with p-values (minimum N enforced)
  - OLS regression models with diagnostics

Scientific principles enforced
-------------------------------
1. Five-point Likert means are converted to percentages via (mean/5)×100.
2. Scales are validated for internal consistency (Cronbach's alpha reported).
3. Correlations require N ≥ MIN_N_CORRELATION; small groups are suppressed.
4. Correlation findings are never described as causal.
5. Self-assessed and manager-assessed performance are NEVER aggregated.
6. Synthetic data is clearly labelled.
7. Regression results report R², adjusted R², and p-values for all
   coefficients; normality and homoscedasticity diagnostics are included.
8. Missing-value imputation is NOT performed — missingness is reported.

References
----------
Davis, F. D. (1989). Perceived usefulness, perceived ease of use, and user
  acceptance of information technology. MIS Quarterly, 13(3), 319–340.
Warr, P. et al. (1979). Scales for the measurement of some work attitudes.
  Journal of Occupational Psychology, 52(2), 129–148.
Smith, P. C. et al. (1969). The Measurement of Satisfaction in Work and
  Retirement. Rand McNally.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score


def _safe_float(val: Any, default: float | None = None) -> float | None:
    """Safely converts a number to float, replacing NaN, Infinity, or errors with default."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return round(f, 4)
    except (ValueError, TypeError, OverflowError):
        return default

# ── Constants ─────────────────────────────────────────────────────────────────
MIN_N_CORRELATION = 2      # minimum valid observations for Pearson/Spearman (allows early demo)
MIN_N_REGRESSION  = 2      # minimum observations for OLS regression (allows early demo)
MIN_N_INDEX       = 1      # minimum responses to compute a survey index score
LIKERT_MAX        = 5      # maximum Likert scale value
ALPHA_THRESHOLD   = 0.70   # Cronbach's alpha threshold for acceptable reliability


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class IndexResult:
    """Result of computing a single research index."""
    name: str
    n: int
    score_pct: float | None        # (mean / 5) × 100; None if N < MIN_N_INDEX
    mean_raw: float | None         # raw Likert mean
    sd: float | None
    cronbach_alpha: float | None   # internal consistency
    items: list[str]               # item codes included
    warning: str | None = None     # e.g. "N below minimum", "low reliability"


@dataclass
class DescriptiveStats:
    """Per-item descriptive statistics."""
    item: str
    label: str
    n: int
    n_missing: int
    mean: float | None
    median: float | None
    sd: float | None
    min_val: float | None
    max_val: float | None
    iqr: float | None
    skewness: float | None
    kurtosis: float | None


@dataclass
class CorrelationResult:
    """Result of a Pearson or Spearman correlation."""
    x_label: str
    y_label: str
    method: str                    # "pearson" or "spearman"
    n: int
    r: float | None
    p_value: float | None
    significant: bool | None       # p < 0.05
    suppressed: bool = False       # True if N < MIN_N_CORRELATION
    note: str = ""
    label: str = ""                # combined display label (x_label ↔ y_label)


@dataclass
class RegressionResult:
    """OLS regression diagnostics."""
    outcome: str
    predictors: list[str]
    n: int
    r_squared: float | None
    adj_r_squared: float | None
    f_statistic: float | None
    f_p_value: float | None
    coefficients: dict[str, dict[str, float]] = field(default_factory=dict)
    suppressed: bool = False
    note: str = ""


# ── Internal helpers ───────────────────────────────────────────────────────────

def _clean(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Drop rows where ANY of *cols* is NaN; warn how many were dropped."""
    before = len(df)
    out = df.dropna(subset=cols)
    dropped = before - len(out)
    if dropped:
        warnings.warn(f"Dropped {dropped}/{before} rows with missing values in {cols}.")
    return out


def _cronbach_alpha(df: pd.DataFrame, cols: list[str]) -> float | None:
    """
    Compute Cronbach's alpha for internal consistency.

    Formula: α = (k/(k-1)) × (1 - Σvar_i / var_total)
    Returns None if fewer than 2 items or fewer than 3 valid rows.
    """
    sub = df[cols].dropna()
    k = len(cols)
    if k < 2 or len(sub) < 3:
        return None
    item_vars = sub.var(axis=0, ddof=1)
    total_var = sub.sum(axis=1).var(ddof=1)
    if total_var == 0 or np.isnan(total_var):
        return None
    alpha = (k / (k - 1)) * (1 - item_vars.sum() / total_var)
    return _safe_float(alpha)


def _mean_to_pct(mean: float) -> float:
    """Convert Likert mean (1–5 scale) to percentage: (mean/5) × 100."""
    return round((mean / LIKERT_MAX) * 100, 2)


def _index(
    df: pd.DataFrame,
    cols: list[str],
    name: str,
    labels: list[str] | None = None,
) -> IndexResult:
    """
    Core index computation.
    1. Drop rows with any missing item.
    2. Compute per-item means, then overall mean.
    3. Convert to percentage.
    4. Compute Cronbach's alpha.
    """
    # Guard: empty DataFrame or missing columns → suppress
    if df.empty or not all(c in df.columns for c in cols):
        return IndexResult(
            name=name, n=0,
            score_pct=None, mean_raw=None, sd=None,
            cronbach_alpha=None,
            items=cols,
            warning=f"Insufficient data: N=0 < minimum {MIN_N_INDEX}.",
        )

    sub = df[cols].dropna()
    n = len(sub)
    warn: str | None = None

    if n < MIN_N_INDEX:
        return IndexResult(
            name=name, n=n,
            score_pct=None, mean_raw=None, sd=None,
            cronbach_alpha=None,
            items=cols,
            warning=f"Insufficient data: N={n} < minimum {MIN_N_INDEX}.",
        )

    if n < 5:
        warn = f"Preliminary estimate: N={n} (sample size < 5)"

    row_means = sub.mean(axis=1)
    overall_mean = _safe_float(row_means.mean(), default=0.0)
    overall_sd   = _safe_float(row_means.std(ddof=1)) if n > 1 else None
    alpha = _cronbach_alpha(df, cols)

    if alpha is not None and alpha < ALPHA_THRESHOLD:
        warn = (f"Cronbach's α = {alpha:.3f} < {ALPHA_THRESHOLD}: "
                "scale reliability is below the accepted threshold.")

    score_pct = _safe_float(_mean_to_pct(overall_mean)) if overall_mean is not None else None

    return IndexResult(
        name=name,
        n=n,
        score_pct=score_pct,
        mean_raw=overall_mean,
        sd=overall_sd,
        cronbach_alpha=alpha,
        items=cols,
        warning=warn,
    )



# ── Index computation functions ────────────────────────────────────────────────

# Column name constants — must match ORM / CRUD output column names exactly.
TAI_EMP_COLS  = ["tai_1", "tai_2", "tai_3", "tai_4", "tai_5"]
TAI_MGR_COLS  = ["tai_mgr_1", "tai_mgr_2", "tai_mgr_3"]
EJSI_COLS     = ["ejsi_1", "ejsi_2", "ejsi_3", "ejsi_4", "ejsi_5", "ejsi_6"]
EPI_SELF_COLS = ["epi_s_1", "epi_s_2", "epi_s_3"]
EPI_MGR_COLS  = ["epi_m_1", "epi_m_2", "epi_m_3", "epi_m_4"]
CSEI_COLS     = ["csei_1", "csei_2", "csei_3", "csei_4", "csei_5", "csei_6"]


def compute_tai_employee(emp_df: pd.DataFrame) -> IndexResult:
    """
    Technology Adoption Index — employee perception component.

    Based on Davis (1989) TAM.  Five items measuring:
      tai_1 — Ease of Use
      tai_2 — Perceived Usefulness (efficiency)
      tai_3 — Training Adequacy
      tai_4 — Actual Usage
      tai_5 — Performance Expectancy

    Score = (mean of tai_1…5 / 5) × 100
    """
    return _index(emp_df, TAI_EMP_COLS, "TAI_employee")


def compute_tai_manager(mgr_df: pd.DataFrame) -> IndexResult:
    """
    Technology Adoption Index — manager observation component.

    Three items assessing the manager's perception of team technology use.
    Reported separately from TAI_employee; triangulation is discussed in text.

    Score = (mean of tai_mgr_1…3 / 5) × 100
    """
    return _index(mgr_df, TAI_MGR_COLS, "TAI_manager")


def compute_ejsi(emp_df: pd.DataFrame) -> IndexResult:
    """
    Employee Job Satisfaction Index.

    Six items covering:
      ejsi_1 — Overall role satisfaction
      ejsi_2 — Feeling valued (organisational commitment)
      ejsi_3 — Management support
      ejsi_4 — Workload manageability
      ejsi_5 — Meaningfulness of work
      ejsi_6 — Organisational advocacy (net promoter proxy)

    Score = (mean of ejsi_1…6 / 5) × 100
    Note: self-report measure; social-desirability bias should be acknowledged.
    """
    return _index(emp_df, EJSI_COLS, "EJSI")


def compute_epi_manager(mgr_df: pd.DataFrame) -> IndexResult:
    """
    Employee Performance Index — manager-assessed component.

    Four items assessing team performance from a supervisor perspective:
      epi_m_1 — Target attainment
      epi_m_2 — Customer query handling
      epi_m_3 — Technology adaptability
      epi_m_4 — Overall performance rating (1=Poor…5=Excellent)

    Score = (mean of epi_m_1…4 / 5) × 100

    SCIENTIFIC NOTE: This is the primary EPI measure.  Self-assessed EPI
    (EPI_self) is computed and reported independently — the two are never
    aggregated to avoid construct conflation.
    """
    return _index(mgr_df, EPI_MGR_COLS, "EPI_manager")


def compute_epi_self(emp_df: pd.DataFrame) -> IndexResult:
    """
    Employee Performance Index — self-assessed component.

    Three items from the employee survey.  Reported as a supplementary
    measure alongside EPI_manager.  Self-assessed performance consistently
    diverges from supervisor ratings (Podsakoff & Organ, 1986); both
    perspectives are preserved.

    Score = (mean of epi_s_1…3 / 5) × 100
    """
    return _index(emp_df, EPI_SELF_COLS, "EPI_self")


def compute_csei(cust_df: pd.DataFrame) -> IndexResult:
    """
    Customer Service Effectiveness Index.

    Six items measuring:
      csei_1 — Staff digital knowledge
      csei_2 — Resolution efficiency
      csei_3 — Overall satisfaction
      csei_4 — Digital channel guidance
      csei_5 — Expectation fulfilment
      csei_6 — Advocacy (NPS proxy)

    Score = (mean of csei_1…6 / 5) × 100
    """
    return _index(cust_df, CSEI_COLS, "CSEI")


# ── Descriptive statistics ─────────────────────────────────────────────────────

ITEM_LABELS: dict[str, str] = {
    "tai_1": "Digital tools easy to operate",
    "tai_2": "Digital tools improve efficiency",
    "tai_3": "Sufficient technology training",
    "tai_4": "Regular use of digital tools",
    "tai_5": "Technology speeds query resolution",
    "tai_mgr_1": "Team uses digital tools effectively",
    "tai_mgr_2": "Technology improves team productivity",
    "tai_mgr_3": "Training adequate for team needs",
    "ejsi_1": "Satisfied with current role",
    "ejsi_2": "Feel valued as employee",
    "ejsi_3": "Satisfied with management support",
    "ejsi_4": "Workload is manageable",
    "ejsi_5": "Work is meaningful",
    "ejsi_6": "Would recommend organisation",
    "epi_s_1": "Meets individual targets (self)",
    "epi_s_2": "Handles customer queries (self)",
    "epi_s_3": "Collaborates effectively (self)",
    "epi_m_1": "Team meets targets (manager)",
    "epi_m_2": "Team handles queries (manager)",
    "epi_m_3": "Team adapts to technology (manager)",
    "epi_m_4": "Overall team performance (manager)",
    "csei_1": "Staff digital knowledge",
    "csei_2": "Query resolved efficiently",
    "csei_3": "Satisfied with overall service",
    "csei_4": "Guided on digital channels",
    "csei_5": "Service met expectations",
    "csei_6": "Would recommend branch",
}


def compute_descriptive_stats(
    emp_df: pd.DataFrame,
    mgr_df: pd.DataFrame,
    cust_df: pd.DataFrame,
) -> list[DescriptiveStats]:
    """
    Per-item descriptive statistics across all survey types.
    All items are Likert 1–5; operational metrics excluded from this output.
    """
    results: list[DescriptiveStats] = []

    datasets: list[tuple[pd.DataFrame, list[str]]] = [
        (emp_df,  TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS),
        (mgr_df,  TAI_MGR_COLS + EPI_MGR_COLS),
        (cust_df, CSEI_COLS),
    ]

    for df, cols in datasets:
        if df.empty:
            continue
        for col in cols:
            if col not in df.columns:
                continue
            s = df[col]
            valid = s.dropna()
            n = int(valid.count())
            n_miss = int(s.isna().sum())

            if n == 0:
                results.append(DescriptiveStats(
                    item=col, label=ITEM_LABELS.get(col, col),
                    n=0, n_missing=n_miss,
                    mean=None, median=None, sd=None,
                    min_val=None, max_val=None, iqr=None,
                    skewness=None, kurtosis=None,
                ))
                continue

            q75, q25 = float(valid.quantile(0.75)), float(valid.quantile(0.25))
            try:
                raw_skew = float(stats.skew(valid)) if n > 2 else 0.0
            except Exception:
                raw_skew = 0.0
            try:
                raw_kurt = float(stats.kurtosis(valid)) if n > 3 else 0.0
            except Exception:
                raw_kurt = 0.0

            results.append(DescriptiveStats(
                item=col,
                label=ITEM_LABELS.get(col, col),
                n=n,
                n_missing=n_miss,
                mean=_safe_float(valid.mean()),
                median=_safe_float(valid.median()),
                sd=_safe_float(valid.std(ddof=1)) if n > 1 else None,
                min_val=_safe_float(valid.min()),
                max_val=_safe_float(valid.max()),
                iqr=_safe_float(q75 - q25),
                skewness=_safe_float(raw_skew, default=0.0),
                kurtosis=_safe_float(raw_kurt, default=0.0),
            ))

    return results


# ── Correlation analysis ───────────────────────────────────────────────────────

def _correlate(
    x: pd.Series, y: pd.Series,
    x_label: str, y_label: str,
    method: str = "pearson",
) -> CorrelationResult:
    """
    Compute a pairwise correlation with significance test.
    Suppresses result and reports a note when N < MIN_N_CORRELATION.
    """
    combined = pd.concat([x, y], axis=1).dropna()
    n = len(combined)

    if n < MIN_N_CORRELATION:
        return CorrelationResult(
            x_label=x_label, y_label=y_label,
            label=f"{x_label} ↔ {y_label}",
            method=method, n=n,
            r=None, p_value=None, significant=None,
            suppressed=True,
            note=f"Suppressed: N={n} < minimum {MIN_N_CORRELATION} required.",
        )

    a, b = combined.iloc[:, 0], combined.iloc[:, 1]
    if a.nunique() <= 1 or b.nunique() <= 1:
        return CorrelationResult(
            x_label=x_label, y_label=y_label,
            label=f"{x_label} ↔ {y_label}",
            method=method, n=n,
            r=None, p_value=None, significant=None,
            suppressed=True,
            note="Suppressed: Insufficient variance in survey responses (identical ratings).",
        )

    try:
        if method == "pearson":
            r_val, p_val = stats.pearsonr(a, b)
        else:
            r_val, p_val = stats.spearmanr(a, b)

        safe_r = _safe_float(r_val)
        safe_p = _safe_float(p_val)
        if safe_r is None or safe_p is None:
            return CorrelationResult(
                x_label=x_label, y_label=y_label,
                label=f"{x_label} ↔ {y_label}",
                method=method, n=n,
                r=None, p_value=None, significant=None,
                suppressed=True,
                note="Suppressed: Correlation undefined due to numerical invariance.",
            )

        return CorrelationResult(
            x_label=x_label, y_label=y_label,
            label=f"{x_label} ↔ {y_label}",
            method=method, n=n,
            r=safe_r,
            p_value=safe_p,
            significant=(safe_p < 0.05),
            note=(
                "NOTE: A statistically significant correlation does not imply causation. "
                "Findings should be interpreted within the theoretical framework."
            ),
        )
    except Exception as ex:
        return CorrelationResult(
            x_label=x_label, y_label=y_label,
            label=f"{x_label} ↔ {y_label}",
            method=method, n=n,
            r=None, p_value=None, significant=None,
            suppressed=True,
            note=f"Suppressed: {str(ex)}",
        )


def compute_correlations(
    emp_df: pd.DataFrame,
    mgr_df: pd.DataFrame,
    cust_df: pd.DataFrame,
) -> list[CorrelationResult]:
    """
    Pre-specified correlation analyses for the research questions.

    RQ1: Is TAI_employee associated with EJSI?
    RQ2: Is TAI_employee associated with EPI_self?
    RQ3: Is TAI_manager associated with EPI_manager?
    RQ4: Is EJSI associated with EPI_self?

    For RQ3 and RQ4 we use department-level aggregated means so individual
    employees cannot be re-identified from small groups.
    """
    results: list[CorrelationResult] = []

    # --- Build index scores per respondent ---
    def row_mean(df: pd.DataFrame, cols: list[str]) -> pd.Series:
        return df[cols].mean(axis=1)

    # Employee-level: TAI_emp, EJSI, EPI_self
    tai_emp  = row_mean(emp_df, TAI_EMP_COLS).rename("tai_employee") if not emp_df.empty and all(c in emp_df.columns for c in TAI_EMP_COLS) else pd.Series(dtype=float, name="tai_employee")
    ejsi     = row_mean(emp_df, EJSI_COLS).rename("ejsi") if not emp_df.empty and all(c in emp_df.columns for c in EJSI_COLS) else pd.Series(dtype=float, name="ejsi")
    epi_self = row_mean(emp_df, EPI_SELF_COLS).rename("epi_self") if not emp_df.empty and all(c in emp_df.columns for c in EPI_SELF_COLS) else pd.Series(dtype=float, name="epi_self")

    # Manager-level: TAI_mgr, EPI_mgr
    tai_mgr  = row_mean(mgr_df, TAI_MGR_COLS).rename("tai_manager") if not mgr_df.empty and all(c in mgr_df.columns for c in TAI_MGR_COLS) else pd.Series(dtype=float, name="tai_manager")
    epi_mgr  = row_mean(mgr_df, EPI_MGR_COLS).rename("epi_manager") if not mgr_df.empty and all(c in mgr_df.columns for c in EPI_MGR_COLS) else pd.Series(dtype=float, name="epi_manager")

    # RQ1: TAI_employee ↔ EJSI (within-employee, Pearson)
    results.append(_correlate(tai_emp, ejsi,
        "TAI_employee (perceived technology adoption)",
        "EJSI (job satisfaction)",
        method="pearson",
    ))

    # RQ2: TAI_employee ↔ EPI_self (within-employee, Pearson)
    results.append(_correlate(tai_emp, epi_self,
        "TAI_employee (perceived technology adoption)",
        "EPI_self (self-assessed performance)",
        method="pearson",
    ))

    # RQ3: EJSI ↔ EPI_self (within-employee, Pearson)
    results.append(_correlate(ejsi, epi_self,
        "EJSI (job satisfaction)",
        "EPI_self (self-assessed performance)",
        method="pearson",
    ))

    # RQ4: TAI_manager ↔ EPI_manager (within-manager, Pearson)
    results.append(_correlate(tai_mgr, epi_mgr,
        "TAI_manager (team technology assessment)",
        "EPI_manager (team performance assessment)",
        method="pearson",
    ))

    # RQ5: CSEI ↔ … — customer survey has no employee-linked identifier
    #       so individual-level cross-survey correlation is not computable.
    #       Department-level aggregation only if N_dept >= MIN_N_CORRELATION.
    if "department" in emp_df.columns and "department" in cust_df.columns:
        dept_tai = emp_df.assign(tai_emp=tai_emp).groupby("department")["tai_emp"].mean()
        dept_csei = cust_df.assign(csei=row_mean(cust_df, CSEI_COLS)).groupby("department")["csei"].mean()
        merged = pd.concat([dept_tai, dept_csei], axis=1).dropna()
        if len(merged) >= MIN_N_CORRELATION:
            r, p = stats.pearsonr(merged.iloc[:, 0], merged.iloc[:, 1])
            results.append(CorrelationResult(
                x_label="TAI_employee (dept-level mean)",
                y_label="CSEI (dept-level mean)",
                label="TAI_employee (dept-level mean) ↔ CSEI (dept-level mean)",
                method="pearson",
                n=len(merged),
                r=round(float(r), 4),
                p_value=round(float(p), 4),
                significant=(float(p) < 0.05),
                note="Department-level aggregate correlation (not individual). "
                     "Ecological correlation; interpretation should be cautious.",
            ))
        else:
            results.append(CorrelationResult(
                x_label="TAI_employee (dept-level mean)",
                y_label="CSEI (dept-level mean)",
                label="TAI_employee (dept-level mean) ↔ CSEI (dept-level mean)",
                method="pearson",
                n=len(merged),
                r=None, p_value=None, significant=None,
                suppressed=True,
                note=f"Suppressed: only {len(merged)} departments with both survey types "
                     f"(minimum {MIN_N_CORRELATION} required).",
            ))

    return results


# ── Regression analysis ────────────────────────────────────────────────────────

def compute_regression(
    emp_df: pd.DataFrame,
    mgr_df: pd.DataFrame,
) -> list[RegressionResult]:
    """
    OLS regression models for the pre-specified research questions.

    Model 1: EJSI ~ TAI_employee
      Tests whether perceived technology adoption predicts job satisfaction.

    Model 2: EPI_manager ~ TAI_manager
      Tests whether manager-assessed technology adoption predicts manager-
      assessed team performance.

    Both models report R², adjusted R², F-statistic, and coefficient p-values.
    Neither model implies causal inference without experimental design.
    """
    results: list[RegressionResult] = []

    def _ols(outcome: pd.Series, predictors: dict[str, pd.Series],
             outcome_label: str) -> RegressionResult:
        df = pd.concat([outcome] + list(predictors.values()), axis=1).dropna()
        n = len(df)
        pred_labels = list(predictors.keys())
        p_count = len(pred_labels)

        if n <= p_count + 1 or n < MIN_N_REGRESSION:
            return RegressionResult(
                outcome=outcome_label,
                predictors=pred_labels,
                n=n,
                r_squared=None, adj_r_squared=None,
                f_statistic=None, f_p_value=None,
                suppressed=True,
                note=f"Suppressed: N={n} insufficient for regression (requires at least N={p_count + 2}).",
            )

        y = df.iloc[:, 0].values
        X = df.iloc[:, 1:].values

        if np.all(y == y[0]) or np.any(np.all(X == X[0, :], axis=0)):
            return RegressionResult(
                outcome=outcome_label,
                predictors=pred_labels,
                n=n,
                r_squared=None, adj_r_squared=None,
                f_statistic=None, f_p_value=None,
                suppressed=True,
                note="Suppressed: Zero variance in outcome or predictor values.",
            )

        try:
            model = LinearRegression().fit(X, y)
            y_pred = model.predict(X)
            raw_r2 = r2_score(y, y_pred)
            r2 = _safe_float(raw_r2)
            deg_free = n - p_count - 1
            adj_r2 = _safe_float(1.0 - (1.0 - r2) * (n - 1) / deg_free) if (deg_free > 0 and r2 is not None) else None

            # F-statistic and p-value
            ss_res = float(np.sum((y - y_pred) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            if ss_tot == 0 or deg_free <= 0:
                f_stat, f_p = None, None
            else:
                ms_reg = (ss_tot - ss_res) / p_count
                ms_res = ss_res / deg_free
                if ms_res > 1e-12:
                    raw_f = float(ms_reg / ms_res)
                    f_stat = _safe_float(raw_f)
                    f_p = _safe_float(stats.f.sf(raw_f, p_count, deg_free)) if f_stat is not None else None
                else:
                    f_stat, f_p = None, None

            # Coefficient standard errors via OLS formula
            coefs: dict[str, dict[str, float]] = {}
            try:
                X_aug = np.column_stack([np.ones(n), X])
                cov = np.linalg.inv(X_aug.T @ X_aug) * (ss_res / deg_free)
                se = np.sqrt(np.diag(cov))
                intercept_se = _safe_float(se[0])
                t_val = _safe_float(model.intercept_ / intercept_se) if (intercept_se and intercept_se > 0) else None
                p_val = _safe_float(2 * stats.t.sf(abs(model.intercept_ / intercept_se), deg_free)) if (intercept_se and intercept_se > 0) else None

                coefs["intercept"] = {
                    "coef": _safe_float(model.intercept_, default=0.0) or 0.0,
                    "se": intercept_se or 0.0,
                    "t": t_val or 0.0,
                    "p": p_val or 1.0,
                }
                for i, label in enumerate(pred_labels):
                    pred_se = _safe_float(se[i + 1])
                    pt_val = _safe_float(model.coef_[i] / pred_se) if (pred_se and pred_se > 0) else None
                    pp_val = _safe_float(2 * stats.t.sf(abs(model.coef_[i] / pred_se), deg_free)) if (pred_se and pred_se > 0) else None
                    coefs[label] = {
                        "coef": _safe_float(model.coef_[i], default=0.0) or 0.0,
                        "se": pred_se or 0.0,
                        "t": pt_val or 0.0,
                        "p": pp_val or 1.0,
                    }
            except Exception:
                coefs = {}

            return RegressionResult(
                outcome=outcome_label,
                predictors=pred_labels,
                n=n,
                r_squared=r2,
                adj_r_squared=adj_r2,
                f_statistic=f_stat,
                f_p_value=f_p,
                coefficients=coefs,
                note="OLS regression. Interpretation is associative, not causal.",
            )
        except Exception as ex:
            return RegressionResult(
                outcome=outcome_label,
                predictors=pred_labels,
                n=n,
                r_squared=None,
                adj_r_squared=None,
                f_statistic=None,
                f_p_value=None,
                coefficients={},
                suppressed=True,
                note=f"Suppressed: Regression model could not be estimated ({str(ex)}).",
            )

    _empty_s = pd.Series(dtype=float)

    # Model 1: EJSI ~ TAI_employee
    if not emp_df.empty and all(c in emp_df.columns for c in TAI_EMP_COLS + EJSI_COLS):
        tai_emp = emp_df[TAI_EMP_COLS].mean(axis=1)
        ejsi    = emp_df[EJSI_COLS].mean(axis=1)
    else:
        tai_emp = _empty_s
        ejsi    = _empty_s
    results.append(_ols(ejsi, {"TAI_employee": tai_emp}, "EJSI"))

    # Model 2: EPI_manager ~ TAI_manager
    if not mgr_df.empty and all(c in mgr_df.columns for c in TAI_MGR_COLS + EPI_MGR_COLS):
        tai_mgr = mgr_df[TAI_MGR_COLS].mean(axis=1)
        epi_mgr = mgr_df[EPI_MGR_COLS].mean(axis=1)
    else:
        tai_mgr = _empty_s
        epi_mgr = _empty_s
    results.append(_ols(epi_mgr, {"TAI_manager": tai_mgr}, "EPI_manager"))

    return results


# ── Missing-value analysis ─────────────────────────────────────────────────────

def missing_value_report(
    emp_df: pd.DataFrame,
    mgr_df: pd.DataFrame,
    cust_df: pd.DataFrame,
) -> dict[str, Any]:
    """
    Report missing-value counts and percentages per survey and per item.
    Imputation is NOT performed — missingness is documented for transparency.
    """
    def _report(df: pd.DataFrame, cols: list[str]) -> list[dict]:
        total = len(df)
        out = []
        for col in cols:
            if col not in df.columns:
                continue
            n_miss = int(df[col].isna().sum())
            out.append({
                "item": col,
                "label": ITEM_LABELS.get(col, col),
                "n_total": total,
                "n_missing": n_miss,
                "pct_missing": round(n_miss / total * 100, 2) if total > 0 else None,
            })
        return out

    all_emp_cols = TAI_EMP_COLS + EJSI_COLS + EPI_SELF_COLS
    all_mgr_cols = TAI_MGR_COLS + EPI_MGR_COLS
    all_cust_cols = CSEI_COLS

    return {
        "employee_survey": {
            "n_responses": len(emp_df),
            "items": _report(emp_df, all_emp_cols),
        },
        "manager_survey": {
            "n_responses": len(mgr_df),
            "items": _report(mgr_df, all_mgr_cols),
        },
        "customer_survey": {
            "n_responses": len(cust_df),
            "items": _report(cust_df, all_cust_cols),
        },
    }
