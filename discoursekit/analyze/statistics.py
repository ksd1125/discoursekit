"""Optional statistical tests for discourse analysis designs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StatTestResult:
    """Serializable result from a statistical model."""

    test_name: str
    summary: dict[str, Any]
    full_output: str
    significant: bool


def run_did(df, outcome_col: str, treat_col: str, post_col: str) -> StatTestResult:
    """Run a Difference-in-Differences OLS model."""
    sm = _statsmodels()
    data = df.copy()
    data["interaction"] = data[treat_col] * data[post_col]
    x = sm.add_constant(data[[treat_col, post_col, "interaction"]])
    y = data[outcome_col]
    model = sm.OLS(y, x).fit()
    p_value = float(model.pvalues.get("interaction", 1.0))
    return StatTestResult(
        test_name="DiD (OLS)",
        summary={
            "beta_interaction": float(model.params.get("interaction", 0.0)),
            "p_interaction": p_value,
            "r_squared": float(model.rsquared),
            "n_obs": int(model.nobs),
        },
        full_output=str(model.summary()),
        significant=p_value < 0.05,
    )


def run_its(df, outcome_col: str, time_col: str, intervention_col: str) -> StatTestResult:
    """Run an Interrupted Time Series OLS model."""
    sm = _statsmodels()
    data = df.copy().sort_values(time_col).reset_index(drop=True)
    data["time_idx"] = range(len(data))
    data["time_after"] = data["time_idx"] * data[intervention_col]
    x = sm.add_constant(data[["time_idx", intervention_col, "time_after"]])
    y = data[outcome_col]
    model = sm.OLS(y, x).fit()
    p_value = float(model.pvalues.get(intervention_col, 1.0))
    return StatTestResult(
        test_name="ITS (OLS)",
        summary={
            "beta_intervention": float(model.params.get(intervention_col, 0.0)),
            "beta_time_after": float(model.params.get("time_after", 0.0)),
            "p_intervention": p_value,
            "r_squared": float(model.rsquared),
            "n_obs": int(model.nobs),
        },
        full_output=str(model.summary()),
        significant=p_value < 0.05,
    )


def run_ppml(df, outcome_col: str, feature_cols: list[str]) -> StatTestResult:
    """Run a Poisson pseudo-maximum likelihood count model."""
    sm = _statsmodels()
    x = sm.add_constant(df[feature_cols])
    y = df[outcome_col]
    model = sm.GLM(y, x, family=sm.families.Poisson()).fit()
    main_p = float(model.pvalues.iloc[1]) if len(model.pvalues) > 1 else 1.0
    return StatTestResult(
        test_name="PPML (Poisson GLM)",
        summary={
            "coefficients": {str(k): float(v) for k, v in model.params.items()},
            "p_values": {str(k): float(v) for k, v in model.pvalues.items()},
            "aic": float(model.aic),
            "n_obs": int(model.nobs),
        },
        full_output=str(model.summary()),
        significant=main_p < 0.05,
    )


def _statsmodels():
    try:
        import statsmodels.api as sm
    except ImportError as exc:
        raise ImportError(
            "statsmodels is required for statistical tests. "
            "Install discoursekit with statistics dependencies enabled."
        ) from exc
    return sm

