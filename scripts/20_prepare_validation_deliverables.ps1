[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation",
    [switch]$SkipTests,
    [switch]$Commit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Message
    Write-Host "============================================================"
}

Write-Step "STEP 20 - PREPARE VALIDATION DELIVERABLES"

if (-not (Test-Path -LiteralPath $ProjectRoot)) {
    throw "Project root does not exist: $ProjectRoot"
}

$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project Python interpreter was not found: $Python"
}

$ReportsDir = Join-Path $ProjectRoot "reports"
$EvidenceDir = Join-Path $ReportsDir "evidence"
$TablesDir = Join-Path $ReportsDir "tables"
$ScriptsDir = Join-Path $ProjectRoot "scripts"

New-Item -ItemType Directory -Force -Path $ReportsDir, $EvidenceDir, $TablesDir, $ScriptsDir | Out-Null

$PytestEvidence = Join-Path $EvidenceDir "pytest_step20.txt"
$PytestExitCode = 0

if (-not $SkipTests) {
    Write-Step "Running the automated test suite"
    Push-Location $ProjectRoot
    try {
        & $Python -m pytest -q 2>&1 | Tee-Object -FilePath $PytestEvidence
        $PytestExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($PytestExitCode -ne 0) {
        Write-Warning "The test suite returned exit code $PytestExitCode. The report will disclose this result."
    }
}
else {
    "Test execution skipped by -SkipTests." | Set-Content -LiteralPath $PytestEvidence -Encoding UTF8
    $PytestExitCode = 999
}

Write-Step "Generating the validation report, committee summary, and findings tracker"

$env:CCP_PROJECT_ROOT = $ProjectRoot
$env:CCP_PYTEST_EXIT_CODE = [string]$PytestExitCode

$PythonSource = @'
from __future__ import annotations

import math
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

try:
    from scipy.stats import chi2
except Exception:
    chi2 = None


ROOT = Path(os.environ["CCP_PROJECT_ROOT"]).resolve()
REPORTS = ROOT / "reports"
EVIDENCE = REPORTS / "evidence"
TABLES = REPORTS / "tables"
PROCESSED = ROOT / "data" / "processed"

REPORTS.mkdir(parents=True, exist_ok=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)
TABLES.mkdir(parents=True, exist_ok=True)

TODAY = date.today()
PYTEST_EXIT_CODE = int(os.environ.get("CCP_PYTEST_EXIT_CODE", "999"))

REPORT_PATH = REPORTS / "independent_validation_report.md"
COMMITTEE_PATH = REPORTS / "model_risk_committee_summary.md"
TRACKER_PATH = EVIDENCE / "findings_tracker.csv"
CHECKS_PATH = EVIDENCE / "step20_validation_checks.csv"
METRICS_PATH = TABLES / "step20_validation_metrics.csv"

FINDING_COLUMNS = [
    "finding_id",
    "finding_title",
    "finding_description",
    "severity",
    "affected_component",
    "evidence",
    "recommendation",
    "owner",
    "target_date",
    "status",
    "validation_status",
    "closure_evidence",
]

ALLOWED_SEVERITIES = ["Critical", "High", "Medium", "Low", "Observation"]
SEVERITY_RANK = {"Critical": 5, "High": 4, "Medium": 3, "Low": 2, "Observation": 1}

REQUIRED_REPORT_SECTIONS = [
    "Executive conclusion",
    "Model purpose and business use",
    "Model inventory",
    "Scope and exclusions",
    "Methodology summary",
    "Data assessment",
    "Conceptual-soundness assessment",
    "Implementation-verification results",
    "Backtesting results",
    "Benchmark and challenger comparison",
    "Sensitivity results",
    "Stress-testing results",
    "Procyclicality assessment",
    "Margin-shortfall analysis",
    "Limitations",
    "Findings",
    "Remediation requirements",
    "Validation conclusion",
    "Conditions for use",
    "Monitoring recommendations",
    "Model-risk committee summary",
]


def rel(path: Path | None) -> str:
    if path is None:
        return "Not available"
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def first_existing(candidates: Iterable[str]) -> Path | None:
    for candidate in candidates:
        path = ROOT / candidate
        if path.exists():
            return path
    return None


def read_table(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    suffix = path.suffix.lower()
    try:
        if suffix == ".parquet":
            return pd.read_parquet(path)
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix in {".json", ".jsonl"}:
            return pd.read_json(path, lines=(suffix == ".jsonl"))
    except Exception as exc:
        print(f"WARNING: Could not read {path}: {exc}")
    return pd.DataFrame()


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower_map:
            return lower_map[name.lower()]
    for column in df.columns:
        normalized = str(column).strip().lower().replace(" ", "_")
        for name in candidates:
            if name.lower() in normalized:
                return column
    return None


def numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None or column not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def fmt_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "Not available"
    try:
        if pd.isna(value):
            return "Not available"
    except Exception:
        pass
    try:
        return f"{float(value):,.{decimals}f}"
    except Exception:
        return str(value)


def fmt_percent(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "Not available"
    try:
        if pd.isna(value):
            return "Not available"
    except Exception:
        pass
    try:
        return f"{100.0 * float(value):.{decimals}f}%"
    except Exception:
        return str(value)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    def clean(value: Any) -> str:
        text = "" if value is None else str(value)
        return text.replace("|", "\\|").replace("\n", " ").strip()

    output = [
        "| " + " | ".join(clean(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(clean(v) for v in row) + " |")
    return "\n".join(output)


def load_or_create_findings() -> pd.DataFrame:
    source = first_existing(
        [
            "reports/evidence/findings_tracker.csv",
            "reports/evidence/validation_findings.csv",
            "reports/evidence/findings.csv",
            "data/processed/validation_findings.csv",
        ]
    )

    if source is not None:
        findings = read_table(source)
    else:
        findings = pd.DataFrame()

    if findings.empty:
        findings = pd.DataFrame(
            [
                {
                    "finding_id": "F-001",
                    "finding_title": "Empirical calibration of non-VaR margin components is incomplete",
                    "finding_description": (
                        "Liquidity, concentration, gap-risk, and stress-buffer parameters are documented as "
                        "preliminary placeholders rather than empirically calibrated production parameters."
                    ),
                    "severity": "High",
                    "affected_component": "Margin add-ons and total margin",
                    "evidence": (
                        "configs/project.yaml; src/ccp_margin/margin/liquidity_addon.py; "
                        "src/ccp_margin/margin/concentration_addon.py; "
                        "src/ccp_margin/margin/gap_risk_addon.py; "
                        "src/ccp_margin/margin/stress_buffer.py"
                    ),
                    "recommendation": (
                        "Complete empirical calibration using documented historical and stressed data; establish "
                        "parameter governance, approval thresholds, and periodic recalibration requirements."
                    ),
                    "owner": "Model Development",
                    "target_date": (TODAY + timedelta(days=60)).isoformat(),
                    "status": "Open",
                    "validation_status": "Pending remediation",
                    "closure_evidence": "",
                },
                {
                    "finding_id": "F-002",
                    "finding_title": "Production representativeness is limited by public data and synthetic portfolios",
                    "finding_description": (
                        "The validation uses public market data and deterministic synthetic clearing-member "
                        "portfolios. These are appropriate for framework validation but do not fully evidence "
                        "production-member behavior, intraday exposures, or proprietary liquidity conditions."
                    ),
                    "severity": "Medium",
                    "affected_component": "Data, portfolios, and empirical performance assessment",
                    "evidence": (
                        "docs/scope_and_assumptions.md; data/processed/clearing_member_positions.parquet; "
                        "data/processed/portfolio_exposures.parquet"
                    ),
                    "recommendation": (
                        "Repeat the principal validation tests with governed production or production-like data "
                        "before production approval, subject to confidentiality and data-control requirements."
                    ),
                    "owner": "Model Development and Data Engineering",
                    "target_date": (TODAY + timedelta(days=90)).isoformat(),
                    "status": "Open",
                    "validation_status": "Pending remediation",
                    "closure_evidence": "",
                },
                {
                    "finding_id": "F-003",
                    "finding_title": "Production implementation and operational-control evidence is not complete",
                    "finding_description": (
                        "The repository validates analytical logic, but end-to-end evidence for production job "
                        "scheduling, entitlements, reconciliations, incident handling, and change-management "
                        "controls is outside the current implementation scope."
                    ),
                    "severity": "Medium",
                    "affected_component": "Implementation and operational controls",
                    "evidence": "docs/validation_charter.md; reports/evidence/pytest_step20.txt",
                    "recommendation": (
                        "Complete production parallel testing, source-to-report reconciliation, access-control "
                        "testing, run-book review, and controlled release evidence before production use."
                    ),
                    "owner": "Technology and Model Operations",
                    "target_date": (TODAY + timedelta(days=90)).isoformat(),
                    "status": "Open",
                    "validation_status": "Pending remediation",
                    "closure_evidence": "",
                },
                {
                    "finding_id": "F-004",
                    "finding_title": "Monitoring thresholds and escalation ownership require formal approval",
                    "finding_description": (
                        "Monitoring measures are implemented, but final threshold calibration, breach escalation, "
                        "and committee-approved ownership should be formalized."
                    ),
                    "severity": "Low",
                    "affected_component": "Ongoing monitoring and governance",
                    "evidence": "configs/monitoring; src/ccp_margin/monitoring; data/processed/monitoring_metrics.parquet",
                    "recommendation": (
                        "Approve monitoring thresholds, escalation timeframes, breach disposition standards, and "
                        "periodic reporting responsibilities."
                    ),
                    "owner": "Model Risk Management and Model Owner",
                    "target_date": (TODAY + timedelta(days=120)).isoformat(),
                    "status": "Open",
                    "validation_status": "Pending remediation",
                    "closure_evidence": "",
                },
                {
                    "finding_id": "F-005",
                    "finding_title": "Formal independence testing must continue to use non-overlapping horizons",
                    "finding_description": (
                        "Overlapping multi-day returns are appropriate for margin estimation but can create serial "
                        "dependence in formal exception-independence tests."
                    ),
                    "severity": "Observation",
                    "affected_component": "Multi-day backtesting",
                    "evidence": (
                        "src/ccp_margin/models/primary/multi_day_returns.py; "
                        "src/ccp_margin/validation/christoffersen.py"
                    ),
                    "recommendation": (
                        "Retain non-overlapping observations for formal independence testing and preserve the "
                        "methodological disclosure in validation reporting."
                    ),
                    "owner": "Independent Validation",
                    "target_date": (TODAY + timedelta(days=120)).isoformat(),
                    "status": "Open",
                    "validation_status": "Monitoring item",
                    "closure_evidence": "",
                },
            ],
            columns=FINDING_COLUMNS,
        )
    else:
        rename_map = {
            "id": "finding_id",
            "title": "finding_title",
            "description": "finding_description",
            "component": "affected_component",
            "target": "target_date",
        }
        findings = findings.rename(columns={k: v for k, v in rename_map.items() if k in findings.columns})
        for column in FINDING_COLUMNS:
            if column not in findings.columns:
                findings[column] = ""
        findings = findings[FINDING_COLUMNS].copy()

    findings = findings.fillna("")
    findings["severity"] = findings["severity"].astype(str).str.strip().str.title()
    findings["finding_id"] = findings["finding_id"].astype(str).str.strip()

    invalid = sorted(set(findings["severity"]) - set(ALLOWED_SEVERITIES))
    if invalid:
        raise ValueError(
            f"Invalid finding severities: {invalid}. Allowed values: {ALLOWED_SEVERITIES}"
        )

    if findings["finding_id"].eq("").any():
        raise ValueError("Every findings-tracker row must have a finding_id.")

    duplicates = findings["finding_id"].duplicated().sum()
    if duplicates:
        raise ValueError(f"Duplicate finding_id values detected: {duplicates}")

    findings["_severity_rank"] = findings["severity"].map(SEVERITY_RANK)
    findings = findings.sort_values(
        ["_severity_rank", "finding_id"], ascending=[False, True]
    ).drop(columns=["_severity_rank"])

    findings.to_csv(TRACKER_PATH, index=False)
    return findings


def is_open_status(value: Any) -> bool:
    text = str(value).strip().lower()
    return text not in {"closed", "resolved", "accepted", "complete", "completed", "validated"}


def rating_and_recommendation(findings: pd.DataFrame, tests_failed: bool) -> tuple[str, str]:
    open_findings = findings[findings["status"].map(is_open_status)]
    severities = set(open_findings["severity"])

    if "Critical" in severities:
        return (
            "Unsatisfactory",
            "Do not approve the model for use until all Critical findings are closed and independently validated.",
        )

    if "High" in severities or tests_failed:
        return (
            "Conditionally Satisfactory",
            (
                "Conditional approval only. Production use should require closure of High findings or formally "
                "approved compensating controls, completion of production-data testing, and satisfactory "
                "implementation evidence."
            ),
        )

    if "Medium" in severities:
        return (
            "Satisfactory with Conditions",
            (
                "Approve with conditions, subject to completion of Medium remediation items by their target dates "
                "and continued monitoring."
            ),
        )

    return (
        "Satisfactory",
        "Approve for the documented scope, subject to standard monitoring and change-control requirements.",
    )


def dataset_summary(path: Path | None, df: pd.DataFrame) -> dict[str, Any]:
    if path is None or df.empty:
        return {
            "path": rel(path),
            "rows": 0,
            "columns": 0,
            "date_min": None,
            "date_max": None,
            "members": None,
        }

    date_col = find_column(df, ["date", "as_of_date", "valuation_date", "business_date"])
    member_col = find_column(df, ["member_id", "clearing_member_id", "member"])

    result = {
        "path": rel(path),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "date_min": None,
        "date_max": None,
        "members": None,
    }

    if date_col:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        if dates.notna().any():
            result["date_min"] = dates.min().date().isoformat()
            result["date_max"] = dates.max().date().isoformat()

    if member_col:
        result["members"] = int(df[member_col].nunique(dropna=True))

    return result


def choose_backtest_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if df.empty:
        return df, "No backtesting dataset was available."

    work = df.copy()
    notes: list[str] = []

    model_col = find_column(work, ["model", "model_name", "method"])
    if model_col:
        values = work[model_col].astype(str)
        primary_mask = values.str.contains("primary|historical", case=False, regex=True, na=False)
        if primary_mask.any():
            work = work[primary_mask].copy()
            notes.append(f"Selected primary/historical rows using {model_col}.")

    horizon_col = find_column(work, ["mpor", "horizon", "holding_period", "days"])
    if horizon_col:
        numeric_horizon = pd.to_numeric(work[horizon_col], errors="coerce")
        if (numeric_horizon == 1).any():
            work = work[numeric_horizon == 1].copy()
            notes.append(f"Selected 1-day rows using {horizon_col}.")

    baseline_col = find_column(work, ["is_baseline", "baseline"])
    scenario_col = find_column(work, ["scenario_id", "scenario", "scenario_name"])

    if baseline_col:
        raw = work[baseline_col]
        mask = raw.astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})
        if mask.any():
            work = work[mask].copy()
            notes.append(f"Selected rows flagged as baseline using {baseline_col}.")
            return work, " ".join(notes)

    if scenario_col and work[scenario_col].nunique(dropna=True) > 1:
        labels = work[scenario_col].astype(str)
        baseline_mask = labels.str.contains(r"(^|[_\-\s])(base|baseline)([_\-\s]|$)", case=False, regex=True, na=False)
        if baseline_mask.any():
            chosen = labels[baseline_mask].iloc[0]
            work = work[labels == chosen].copy()
            notes.append(f"Selected baseline scenario {chosen}.")
        else:
            counts = work.groupby(scenario_col, dropna=False).size().sort_values(ascending=False)
            chosen = counts.index[0]
            work = work[work[scenario_col] == chosen].copy()
            notes.append(
                f"No explicit baseline marker was found; scenario {chosen} was used as the backtesting proxy."
            )

    return work, " ".join(notes) if notes else "Used all available backtesting rows."


def exception_series(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, str]:
    exception_col = find_column(df, ["exception", "is_exception", "breach", "shortfall_flag"])
    margin_col = find_column(
        df,
        ["margin", "total_margin", "required_margin", "initial_margin", "base_margin"],
    )
    loss_col = find_column(
        df,
        ["realized_loss", "actual_loss", "loss", "realized_pnl", "portfolio_pnl", "pnl"],
    )

    margin = numeric_series(df, margin_col)
    raw_loss = numeric_series(df, loss_col)
    loss = raw_loss.copy()

    if loss_col and "pnl" in str(loss_col).lower():
        loss = -raw_loss

    if exception_col:
        raw = df[exception_col]
        if pd.api.types.is_bool_dtype(raw):
            exc = raw.fillna(False).astype(bool)
        else:
            text = raw.astype(str).str.strip().str.lower()
            exc = text.isin({"true", "1", "yes", "y", "exception", "breach"})
        note = f"Used explicit exception field {exception_col}."
    elif margin_col and loss_col:
        exc = loss > margin
        note = f"Calculated exceptions as {loss_col} loss greater than {margin_col}."
    else:
        exc = pd.Series(False, index=df.index)
        note = "Required margin and realized-loss fields were not available."

    return exc.astype(bool), margin, loss, note


def safe_log(value: float) -> float:
    return math.log(max(value, 1e-15))


def kupiec_test(exceptions: np.ndarray, p: float = 0.01) -> tuple[float | None, float | None]:
    n = int(len(exceptions))
    x = int(np.sum(exceptions))
    if n == 0:
        return None, None

    phat = x / n
    log_null = (n - x) * safe_log(1 - p) + x * safe_log(p)
    log_alt = (n - x) * safe_log(1 - phat) + x * safe_log(phat)
    lr = max(0.0, -2.0 * (log_null - log_alt))
    p_value = float(chi2.sf(lr, 1)) if chi2 is not None else None
    return lr, p_value


def christoffersen_test(exceptions: np.ndarray) -> tuple[float | None, float | None]:
    if len(exceptions) < 2:
        return None, None

    prev = exceptions[:-1].astype(int)
    curr = exceptions[1:].astype(int)

    n00 = int(np.sum((prev == 0) & (curr == 0)))
    n01 = int(np.sum((prev == 0) & (curr == 1)))
    n10 = int(np.sum((prev == 1) & (curr == 0)))
    n11 = int(np.sum((prev == 1) & (curr == 1)))

    denom0 = n00 + n01
    denom1 = n10 + n11
    total = n00 + n01 + n10 + n11

    if denom0 == 0 or denom1 == 0 or total == 0:
        return None, None

    pi0 = n01 / denom0
    pi1 = n11 / denom1
    pi = (n01 + n11) / total

    log_null = (n00 + n10) * safe_log(1 - pi) + (n01 + n11) * safe_log(pi)
    log_alt = (
        n00 * safe_log(1 - pi0)
        + n01 * safe_log(pi0)
        + n10 * safe_log(1 - pi1)
        + n11 * safe_log(pi1)
    )

    lr = max(0.0, -2.0 * (log_null - log_alt))
    p_value = float(chi2.sf(lr, 1)) if chi2 is not None else None
    return lr, p_value


def traffic_light(exception_count: int) -> str:
    if exception_count <= 4:
        return "Green"
    if exception_count <= 9:
        return "Yellow"
    return "Red"


def backtesting_analysis(df: pd.DataFrame) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "notes": "No usable backtesting data were available.",
        "members": 0,
        "observations": 0,
        "exceptions": 0,
        "exception_rate": None,
        "green": 0,
        "yellow": 0,
        "red": 0,
        "kupiec_pass_rate": None,
        "independence_pass_rate": None,
        "worst_member": None,
        "worst_exceptions": None,
        "shortfall_count": 0,
        "shortfall_total": None,
        "shortfall_mean": None,
        "shortfall_max": None,
        "detail": pd.DataFrame(),
    }

    if df.empty:
        return result

    work, selection_note = choose_backtest_frame(df)
    exc, margin, loss, exception_note = exception_series(work)

    if work.empty or len(exc) == 0:
        result["notes"] = selection_note + " " + exception_note
        return result

    date_col = find_column(work, ["date", "as_of_date", "valuation_date", "business_date"])
    member_col = find_column(work, ["member_id", "clearing_member_id", "member"])

    analysis = work.copy()
    analysis["_exception"] = exc.values
    analysis["_margin"] = margin.values if len(margin) == len(analysis) else np.nan
    analysis["_loss"] = loss.values if len(loss) == len(analysis) else np.nan

    if date_col:
        analysis["_date"] = pd.to_datetime(analysis[date_col], errors="coerce")
    else:
        analysis["_date"] = np.arange(len(analysis))

    if member_col is None:
        analysis["_member"] = "Aggregate"
        member_col = "_member"

    rows: list[dict[str, Any]] = []
    for member, group in analysis.groupby(member_col, dropna=False):
        group = group.sort_values("_date").tail(250)
        exceptions = group["_exception"].astype(bool).to_numpy()
        n = int(len(exceptions))
        x = int(exceptions.sum())
        lr_uc, p_uc = kupiec_test(exceptions)
        lr_ind, p_ind = christoffersen_test(exceptions)

        rows.append(
            {
                "member_id": str(member),
                "observations": n,
                "exceptions": x,
                "exception_rate": x / n if n else np.nan,
                "traffic_light": traffic_light(x) if n else "Not available",
                "kupiec_lr": lr_uc,
                "kupiec_p_value": p_uc,
                "kupiec_pass_5pct": bool(p_uc is not None and p_uc >= 0.05),
                "christoffersen_lr": lr_ind,
                "christoffersen_p_value": p_ind,
                "christoffersen_pass_5pct": bool(p_ind is not None and p_ind >= 0.05),
            }
        )

    detail = pd.DataFrame(rows)
    positive_shortfall = (analysis["_loss"] - analysis["_margin"]).clip(lower=0)
    positive_shortfall = positive_shortfall[positive_shortfall > 0]

    result.update(
        {
            "available": True,
            "notes": f"{selection_note} {exception_note}",
            "members": int(len(detail)),
            "observations": int(detail["observations"].sum()),
            "exceptions": int(detail["exceptions"].sum()),
            "exception_rate": (
                float(detail["exceptions"].sum() / detail["observations"].sum())
                if detail["observations"].sum()
                else None
            ),
            "green": int((detail["traffic_light"] == "Green").sum()),
            "yellow": int((detail["traffic_light"] == "Yellow").sum()),
            "red": int((detail["traffic_light"] == "Red").sum()),
            "kupiec_pass_rate": float(detail["kupiec_pass_5pct"].mean()) if len(detail) else None,
            "independence_pass_rate": (
                float(detail["christoffersen_pass_5pct"].mean()) if len(detail) else None
            ),
            "worst_member": (
                str(detail.sort_values("exceptions", ascending=False).iloc[0]["member_id"])
                if len(detail)
                else None
            ),
            "worst_exceptions": (
                int(detail["exceptions"].max()) if len(detail) else None
            ),
            "shortfall_count": int(len(positive_shortfall)),
            "shortfall_total": (
                float(positive_shortfall.sum()) if len(positive_shortfall) else 0.0
            ),
            "shortfall_mean": (
                float(positive_shortfall.mean()) if len(positive_shortfall) else 0.0
            ),
            "shortfall_max": (
                float(positive_shortfall.max()) if len(positive_shortfall) else 0.0
            ),
            "detail": detail,
        }
    )
    return result


def benchmark_analysis(df: pd.DataFrame) -> dict[str, Any]:
    result = {
        "available": False,
        "observations": 0,
        "primary_mean": None,
        "challenger_mean": None,
        "challenger_to_primary": None,
        "median_abs_difference": None,
        "challenger_higher_share": None,
        "notes": "No directly comparable primary and challenger margin fields were found.",
    }

    if df.empty:
        return result

    primary_col = find_column(
        df,
        ["primary_margin", "historical_margin", "historical_var", "hs_var", "primary_var"],
    )
    challenger_col = find_column(
        df,
        ["challenger_margin", "parametric_margin", "parametric_var", "ewma_var", "challenger_var"],
    )

    comparison = pd.DataFrame()

    if primary_col and challenger_col:
        comparison = pd.DataFrame(
            {
                "primary": numeric_series(df, primary_col),
                "challenger": numeric_series(df, challenger_col),
            }
        ).dropna()
        notes = f"Compared {primary_col} with {challenger_col}."
    else:
        model_col = find_column(df, ["model", "model_name", "method"])
        margin_col = find_column(df, ["margin", "total_margin", "var", "required_margin"])
        date_col = find_column(df, ["date", "as_of_date", "valuation_date"])
        member_col = find_column(df, ["member_id", "clearing_member_id", "member"])

        if model_col and margin_col:
            work = df.copy()
            work["_model_type"] = np.where(
                work[model_col].astype(str).str.contains("primary|historical", case=False, regex=True, na=False),
                "primary",
                np.where(
                    work[model_col].astype(str).str.contains("challenger|parametric|ewma", case=False, regex=True, na=False),
                    "challenger",
                    "other",
                ),
            )
            work = work[work["_model_type"].isin(["primary", "challenger"])]
            keys = [c for c in [date_col, member_col] if c]
            if not keys:
                work["_row"] = work.groupby("_model_type").cumcount()
                keys = ["_row"]
            pivot = work.pivot_table(index=keys, columns="_model_type", values=margin_col, aggfunc="mean")
            if {"primary", "challenger"}.issubset(pivot.columns):
                comparison = pivot[["primary", "challenger"]].dropna().reset_index(drop=True)
                notes = f"Pivoted model rows using {model_col} and {margin_col}."
            else:
                notes = result["notes"]
        else:
            notes = result["notes"]

    if comparison.empty:
        result["notes"] = notes
        return result

    comparison = comparison[(comparison["primary"] > 0) & comparison["challenger"].notna()]
    if comparison.empty:
        result["notes"] = "Comparable rows were found, but no positive primary margin values were available."
        return result

    result.update(
        {
            "available": True,
            "observations": int(len(comparison)),
            "primary_mean": float(comparison["primary"].mean()),
            "challenger_mean": float(comparison["challenger"].mean()),
            "challenger_to_primary": float(
                comparison["challenger"].mean() / comparison["primary"].mean()
            ),
            "median_abs_difference": float(
                (comparison["challenger"] - comparison["primary"]).abs().median()
            ),
            "challenger_higher_share": float(
                (comparison["challenger"] > comparison["primary"]).mean()
            ),
            "notes": notes,
        }
    )
    return result


def sensitivity_analysis(df: pd.DataFrame) -> dict[str, Any]:
    result = {
        "available": False,
        "scenarios": 0,
        "rows": 0,
        "baseline": None,
        "min_change": None,
        "max_change": None,
        "largest_increase_scenario": None,
        "largest_decrease_scenario": None,
        "notes": "No usable sensitivity-scenario data were available.",
    }
    if df.empty:
        return result

    scenario_col = find_column(df, ["scenario_id", "scenario", "scenario_name"])
    margin_col = find_column(df, ["margin", "total_margin", "required_margin", "initial_margin"])
    if not scenario_col or not margin_col:
        return result

    work = df[[scenario_col, margin_col]].copy()
    work[margin_col] = pd.to_numeric(work[margin_col], errors="coerce")
    work = work.dropna(subset=[margin_col])

    means = work.groupby(scenario_col, dropna=False)[margin_col].mean().sort_index()
    if means.empty:
        return result

    labels = means.index.astype(str)
    baseline_candidates = [label for label in labels if re.search(r"(^|[_\-\s])(base|baseline)([_\-\s]|$)", label, re.I)]
    baseline = baseline_candidates[0] if baseline_candidates else str(means.index[0])
    baseline_value = float(means.loc[baseline]) if baseline in means.index else float(means.iloc[0])

    if baseline_value == 0:
        changes = pd.Series(np.nan, index=means.index)
    else:
        changes = means / baseline_value - 1.0

    result.update(
        {
            "available": True,
            "scenarios": int(means.index.nunique()),
            "rows": int(len(work)),
            "baseline": baseline,
            "min_change": float(changes.min()) if changes.notna().any() else None,
            "max_change": float(changes.max()) if changes.notna().any() else None,
            "largest_increase_scenario": str(changes.idxmax()) if changes.notna().any() else None,
            "largest_decrease_scenario": str(changes.idxmin()) if changes.notna().any() else None,
            "notes": (
                "Scenario mean margins were compared with the explicit baseline scenario."
                if baseline_candidates
                else f"No explicit baseline label was found; {baseline} was used as the comparison base."
            ),
        }
    )
    return result


def stress_analysis(df: pd.DataFrame) -> dict[str, Any]:
    result = {
        "available": False,
        "scenarios": 0,
        "rows": 0,
        "worst_scenario": None,
        "worst_loss": None,
        "max_shortfall": None,
        "shortfall_scenarios": 0,
        "notes": "No usable stress-test results were available.",
    }
    if df.empty:
        return result

    scenario_col = find_column(df, ["scenario_id", "scenario", "scenario_name", "stress_scenario"])
    loss_col = find_column(df, ["stressed_loss", "stress_loss", "loss", "pnl", "portfolio_pnl"])
    margin_col = find_column(df, ["margin", "total_margin", "available_margin"])
    shortfall_col = find_column(df, ["shortfall", "margin_shortfall"])

    if scenario_col is None:
        scenario_col = "_scenario"
        df = df.copy()
        df[scenario_col] = "Aggregate"

    work = df.copy()
    loss = numeric_series(work, loss_col)
    if loss_col and "pnl" in str(loss_col).lower():
        loss = -loss
    margin = numeric_series(work, margin_col)
    shortfall = numeric_series(work, shortfall_col)

    if shortfall.empty and not loss.empty and not margin.empty:
        shortfall = (loss - margin).clip(lower=0)

    if loss.empty and shortfall.empty:
        result["notes"] = "Stress data were found, but no stressed-loss or shortfall field was identifiable."
        return result

    work["_loss"] = loss if len(loss) == len(work) else np.nan
    work["_shortfall"] = shortfall if len(shortfall) == len(work) else np.nan

    scenario_summary = work.groupby(scenario_col, dropna=False).agg(
        stressed_loss=("_loss", "max"),
        shortfall=("_shortfall", "max"),
    )

    loss_basis = scenario_summary["stressed_loss"]
    if loss_basis.notna().any():
        worst_scenario = str(loss_basis.idxmax())
        worst_loss = float(loss_basis.max())
    else:
        worst_scenario = str(scenario_summary["shortfall"].idxmax())
        worst_loss = None

    max_shortfall = (
        float(scenario_summary["shortfall"].max())
        if scenario_summary["shortfall"].notna().any()
        else None
    )

    result.update(
        {
            "available": True,
            "scenarios": int(scenario_summary.index.nunique()),
            "rows": int(len(work)),
            "worst_scenario": worst_scenario,
            "worst_loss": worst_loss,
            "max_shortfall": max_shortfall,
            "shortfall_scenarios": int((scenario_summary["shortfall"].fillna(0) > 0).sum()),
            "notes": "Stress scenarios were summarized using maximum stressed loss and margin shortfall.",
        }
    )
    return result


def procyclicality_analysis(monitoring_df: pd.DataFrame, daily_df: pd.DataFrame) -> dict[str, Any]:
    result = {
        "available": False,
        "source": "Not available",
        "daily_max_increase": None,
        "daily_max_decrease": None,
        "weekly_max_increase": None,
        "weekly_max_decrease": None,
        "peak_to_trough": None,
        "jumps_10": None,
        "jumps_20": None,
        "jumps_30": None,
        "member_call_volatility": None,
        "notes": "No usable monitoring or daily-margin data were available.",
    }

    if not monitoring_df.empty:
        metric_col = find_column(monitoring_df, ["metric_name", "metric", "measure"])
        value_col = find_column(monitoring_df, ["metric_value", "value", "result"])
        if metric_col and value_col:
            metrics = {
                str(k).strip().lower(): v
                for k, v in monitoring_df[[metric_col, value_col]].dropna().itertuples(index=False)
            }

            def metric_value(*patterns: str) -> float | None:
                for key, value in metrics.items():
                    if all(pattern in key for pattern in patterns):
                        try:
                            return float(value)
                        except Exception:
                            continue
                return None

            result.update(
                {
                    "available": True,
                    "source": "Prepared monitoring metrics",
                    "daily_max_increase": metric_value("daily", "max", "increase"),
                    "daily_max_decrease": metric_value("daily", "max", "decrease"),
                    "weekly_max_increase": metric_value("weekly", "max", "increase"),
                    "weekly_max_decrease": metric_value("weekly", "max", "decrease"),
                    "peak_to_trough": metric_value("peak", "trough"),
                    "jumps_10": metric_value("jump", "10"),
                    "jumps_20": metric_value("jump", "20"),
                    "jumps_30": metric_value("jump", "30"),
                    "member_call_volatility": metric_value("member", "volatility"),
                    "notes": "Metrics were read from the prepared Step 17 monitoring output.",
                }
            )
            return result

    if daily_df.empty:
        return result

    date_col = find_column(daily_df, ["date", "as_of_date", "valuation_date", "business_date"])
    member_col = find_column(daily_df, ["member_id", "clearing_member_id", "member"])
    margin_col = find_column(
        daily_df,
        ["total_margin", "margin", "required_margin", "initial_margin"],
    )

    if not date_col or not margin_col:
        return result

    work = daily_df.copy()
    work["_date"] = pd.to_datetime(work[date_col], errors="coerce")
    work["_margin"] = pd.to_numeric(work[margin_col], errors="coerce")
    work = work.dropna(subset=["_date", "_margin"])

    daily_total = work.groupby("_date")["_margin"].sum().sort_index()
    daily_change = daily_total.pct_change()
    weekly_change = daily_total.pct_change(5)
    running_peak = daily_total.cummax()
    drawdown = daily_total / running_peak - 1.0

    member_vol = None
    if member_col:
        member_change = (
            work.sort_values([member_col, "_date"])
            .groupby(member_col)["_margin"]
            .pct_change()
        )
        member_vol = float(member_change.groupby(work[member_col]).std().median())

    result.update(
        {
            "available": True,
            "source": "Derived from daily member margin",
            "daily_max_increase": float(daily_change.max()) if daily_change.notna().any() else None,
            "daily_max_decrease": float(daily_change.min()) if daily_change.notna().any() else None,
            "weekly_max_increase": float(weekly_change.max()) if weekly_change.notna().any() else None,
            "weekly_max_decrease": float(weekly_change.min()) if weekly_change.notna().any() else None,
            "peak_to_trough": float(drawdown.min()) if drawdown.notna().any() else None,
            "jumps_10": int((daily_change.abs() > 0.10).sum()),
            "jumps_20": int((daily_change.abs() > 0.20).sum()),
            "jumps_30": int((daily_change.abs() > 0.30).sum()),
            "member_call_volatility": member_vol,
            "notes": (
                "Core change and jump measures were derived from daily member margin. "
                "Use the prepared Step 17 monitoring output for volatility correlation, stressed-to-calm ratio, "
                "and buffer depletion/replenishment measures."
            ),
        }
    )
    return result


def pytest_summary() -> dict[str, Any]:
    path = EVIDENCE / "pytest_step20.txt"
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    passed_match = re.search(r"(\d+)\s+passed", text)
    failed_match = re.search(r"(\d+)\s+failed", text)
    errors_match = re.search(r"(\d+)\s+errors?", text)

    if PYTEST_EXIT_CODE == 999:
        status = "Not run"
    elif PYTEST_EXIT_CODE == 0:
        status = "Passed"
    else:
        status = "Failed"

    return {
        "status": status,
        "exit_code": PYTEST_EXIT_CODE,
        "passed": int(passed_match.group(1)) if passed_match else None,
        "failed": int(failed_match.group(1)) if failed_match else 0,
        "errors": int(errors_match.group(1)) if errors_match else 0,
        "path": rel(path),
    }


findings = load_or_create_findings()

daily_path = first_existing(
    [
        "data/processed/daily_member_margin.parquet",
        "data/processed/daily_margin.parquet",
        "data/processed/member_margin_results.parquet",
    ]
)
daily_df = read_table(daily_path)

backtest_path = first_existing(
    [
        "data/processed/backtesting_results.parquet",
        "data/processed/sensitivity_scenario_results.parquet",
        "reports/tables/backtesting_results.csv",
    ]
)
backtest_df = read_table(backtest_path)

benchmark_path = first_existing(
    [
        "data/processed/benchmark_comparison_results.parquet",
        "data/processed/challenger_model_results.parquet",
        "data/processed/daily_member_margin.parquet",
        "reports/tables/benchmark_comparison.csv",
    ]
)
benchmark_df = read_table(benchmark_path)

sensitivity_path = first_existing(
    [
        "data/processed/sensitivity_scenario_results.parquet",
        "reports/tables/sensitivity_results.csv",
    ]
)
sensitivity_df = read_table(sensitivity_path)

stress_path = first_existing(
    [
        "data/processed/stress_test_results.parquet",
        "reports/tables/stress_test_results.csv",
    ]
)
stress_df = read_table(stress_path)

monitoring_path = first_existing(
    [
        "data/processed/monitoring_metrics.parquet",
        "data/processed/procyclicality_results.parquet",
        "data/processed/procyclicality_metrics.parquet",
        "reports/tables/procyclicality_summary.csv",
    ]
)
monitoring_df = read_table(monitoring_path)

quality_path = first_existing(
    [
        "reports/tables/data_quality_summary.csv",
        "reports/evidence/data_quality_exceptions.csv",
        "data/manifests/market_data_manifest.csv",
    ]
)
quality_df = read_table(quality_path)

daily_summary = dataset_summary(daily_path, daily_df)
backtesting = backtesting_analysis(backtest_df)
benchmark = benchmark_analysis(benchmark_df)
sensitivity = sensitivity_analysis(sensitivity_df)
stress = stress_analysis(stress_df)
procyclicality = procyclicality_analysis(monitoring_df, daily_df)
tests = pytest_summary()

tests_failed = tests["status"] == "Failed"
rating, approval_recommendation = rating_and_recommendation(findings, tests_failed)

open_findings = findings[findings["status"].map(is_open_status)].copy()
high_medium = open_findings[open_findings["severity"].isin(["Critical", "High", "Medium"])].copy()

severity_counts = (
    open_findings.groupby("severity").size().reindex(ALLOWED_SEVERITIES, fill_value=0).to_dict()
)

model_inventory_rows = [
    ["Primary model", "Historical-simulation VaR", "99% loss quantile; configurable lookback; 1-, 3-, and 5-day MPOR", "src/ccp_margin/models/primary"],
    ["Challenger model", "Parametric EWMA VaR", "EWMA covariance; PSD control; Normal and optional Student-t", "src/ccp_margin/models/challenger"],
    ["Margin components", "Base margin plus add-ons", "Liquidity, concentration, gap risk, and stress buffer", "src/ccp_margin/margin"],
    ["Validation tests", "Statistical and implementation validation", "Kupiec, Christoffersen, traffic light, shortfall, sensitivity, implementation checks", "src/ccp_margin/validation"],
    ["Stress testing", "Historical, hypothetical, and reverse stress", "Named public stress periods and extreme-but-plausible shocks", "src/ccp_margin/stress"],
    ["Monitoring", "Procyclicality and stability monitoring", "Margin changes, jumps, volatility relationships, and buffer behavior", "src/ccp_margin/monitoring"],
]

data_rows = [
    ["Daily member margin", daily_summary["path"], daily_summary["rows"], daily_summary["date_min"] or "Not available", daily_summary["date_max"] or "Not available", daily_summary["members"] if daily_summary["members"] is not None else "Not available"],
    ["Backtesting source", rel(backtest_path), len(backtest_df), "", "", ""],
    ["Sensitivity source", rel(sensitivity_path), len(sensitivity_df), "", "", ""],
    ["Stress source", rel(stress_path), len(stress_df), "", "", ""],
    ["Monitoring source", rel(monitoring_path), len(monitoring_df), "", "", ""],
    ["Data-quality evidence", rel(quality_path), len(quality_df), "", "", ""],
]

finding_rows = [
    [
        row.finding_id,
        row.severity,
        row.finding_title,
        row.owner,
        row.target_date,
        row.status,
    ]
    for row in high_medium.itertuples(index=False)
]

if not finding_rows:
    finding_rows = [["None", "None", "No open Critical, High, or Medium findings.", "", "", ""]]

backtesting_rows = [
    ["Members tested", backtesting["members"]],
    ["Most-recent observations assessed", backtesting["observations"]],
    ["Exceptions", backtesting["exceptions"]],
    ["Observed exception rate", fmt_percent(backtesting["exception_rate"])],
    ["Traffic-light status", f"{backtesting['green']} Green; {backtesting['yellow']} Yellow; {backtesting['red']} Red"],
    ["Kupiec pass rate at 5%", fmt_percent(backtesting["kupiec_pass_rate"])],
    ["Christoffersen independence pass rate at 5%", fmt_percent(backtesting["independence_pass_rate"])],
    ["Worst member by exception count", f"{backtesting['worst_member']} ({backtesting['worst_exceptions']} exceptions)"],
]

metrics_rows = [
    ["overall_validation_rating", rating],
    ["open_critical_findings", severity_counts.get("Critical", 0)],
    ["open_high_findings", severity_counts.get("High", 0)],
    ["open_medium_findings", severity_counts.get("Medium", 0)],
    ["open_low_findings", severity_counts.get("Low", 0)],
    ["open_observations", severity_counts.get("Observation", 0)],
    ["pytest_status", tests["status"]],
    ["backtesting_members", backtesting["members"]],
    ["backtesting_observations", backtesting["observations"]],
    ["backtesting_exceptions", backtesting["exceptions"]],
    ["backtesting_exception_rate", backtesting["exception_rate"]],
    ["traffic_green_members", backtesting["green"]],
    ["traffic_yellow_members", backtesting["yellow"]],
    ["traffic_red_members", backtesting["red"]],
    ["sensitivity_scenarios", sensitivity["scenarios"]],
    ["stress_scenarios", stress["scenarios"]],
]
pd.DataFrame(metrics_rows, columns=["metric", "value"]).to_csv(METRICS_PATH, index=False)

report = f"""# Independent Validation Report

**Project:** CCP Margin Model Independent Validation YN26  
**Generated:** {TODAY.isoformat()}  
**Overall validation rating:** **{rating}**  
**Approval recommendation:** **{approval_recommendation}**

## Executive conclusion

Independent validation concludes that the CCP margin-model framework is **{rating.lower()}** for the documented development and validation scope. The framework demonstrates broad methodological coverage: historical-simulation and parametric challenger models, multi-day margin periods of risk, component add-ons, backtesting, statistical coverage tests, sensitivity testing, stress testing, margin-shortfall analysis, and procyclicality monitoring. The principal approval constraint is the open High finding concerning empirical calibration of non-VaR margin components. Production approval also requires production-representative data and operational-control evidence.

## Model purpose and business use

The model estimates daily initial-margin requirements for simulated clearing members. It is intended to cover potential portfolio losses over defined margin periods of risk at a 99% confidence level and to supplement base risk coverage with liquidity, concentration, gap-risk, and stress components. The framework supports independent model validation, benchmark comparison, monitoring, and model-risk governance. It is not, by itself, authorization for live clearing or production use.

## Model inventory

{markdown_table(["Component", "Method", "Principal features", "Implementation"], model_inventory_rows)}

## Scope and exclusions

Validation covers data-quality controls, portfolio generation, primary and challenger risk measurement, total-margin construction, statistical backtesting, implementation verification, sensitivity testing, stress testing, procyclicality, and documented governance. Exclusions include confidential production-member positions, intraday calls, collateral eligibility and haircut engines, default-fund sizing, waterfall allocation, legal enforceability, live system entitlements, production scheduling, cyber controls, and production change-management evidence.

## Methodology summary

The primary model applies current positions to historical risk-factor returns and estimates the 99th-percentile loss using historical simulation. Directly observed overlapping multi-day returns are used for margin estimation; non-overlapping observations are required for formal independence testing. The challenger model uses EWMA covariance estimation with positive-semidefinite controls. Validation applies Kupiec unconditional coverage, Christoffersen independence, conditional-coverage logic, Basel-style traffic-light classification, margin-shortfall analysis, benchmark comparison, controlled parameter sensitivity, historical and hypothetical stress scenarios, reverse stress, and procyclicality measures.

## Data assessment

{markdown_table(["Dataset", "Evidence path", "Rows", "Start date", "End date", "Members"], data_rows)}

The data pipeline is reproducible and includes manifests and quality evidence. Public market data and synthetic portfolios provide transparent test coverage but do not fully represent proprietary member behavior, stressed liquidity, intraday exposure changes, or production data lineage. This limitation is captured in Finding F-002.

## Conceptual-soundness assessment

The core conceptual design is appropriate for a CCP margin framework. Historical simulation avoids strong distributional assumptions and preserves empirical dependence in observed risk-factor returns. The parametric EWMA challenger provides an analytically distinct benchmark. Multi-day horizons, liquidity and concentration effects, stress coverage, and procyclicality controls are conceptually relevant. The material conceptual limitation is that non-VaR add-ons and buffers require completed empirical calibration and governance before production reliance.

## Implementation-verification results

Automated test status: **{tests["status"]}**. Passed: **{tests["passed"] if tests["passed"] is not None else "Not reported"}**; failed: **{tests["failed"]}**; errors: **{tests["errors"]}**. Evidence: `{tests["path"]}`.

The implementation is modular, deterministic, configuration-driven, and organized by data, portfolio, model, margin, validation, stress, and monitoring functions. A passed test suite supports code-level implementation evidence. Production implementation verification remains incomplete until source-to-report reconciliation, access controls, job scheduling, run-book controls, and parallel production testing are evidenced.

## Backtesting results

{markdown_table(["Measure", "Result"], backtesting_rows)}

Method note: {backtesting["notes"]} Basel traffic-light counts use the most recent 250 observations per member where available. Detailed member-level statistics should be retained as validation evidence.

## Benchmark and challenger comparison

Comparison available: **{"Yes" if benchmark["available"] else "No"}**. Comparable observations: **{benchmark["observations"]}**. Mean primary margin: **{fmt_number(benchmark["primary_mean"])}**. Mean challenger margin: **{fmt_number(benchmark["challenger_mean"])}**. Challenger-to-primary mean ratio: **{fmt_number(benchmark["challenger_to_primary"], 4)}**. Median absolute difference: **{fmt_number(benchmark["median_abs_difference"])}**. Challenger higher than primary: **{fmt_percent(benchmark["challenger_higher_share"])}**.

{benchmark["notes"]} Material divergence should be investigated by member, market regime, concentration, and MPOR rather than assessed only through an aggregate ratio.

## Sensitivity results

Prepared scenarios: **{sensitivity["scenarios"]}**; observations: **{sensitivity["rows"]}**; comparison baseline: **{sensitivity["baseline"] or "Not available"}**. Mean-margin change range: **{fmt_percent(sensitivity["min_change"])} to {fmt_percent(sensitivity["max_change"])}**. Largest increase: **{sensitivity["largest_increase_scenario"] or "Not available"}**. Largest decrease: **{sensitivity["largest_decrease_scenario"] or "Not available"}**.

{sensitivity["notes"]} Validation should confirm monotonic and economically intuitive responses for confidence level, lookback, MPOR, EWMA decay, liquidity, concentration, stress buffer, and correlation shocks.

## Stress-testing results

Prepared stress scenarios: **{stress["scenarios"]}**; observations: **{stress["rows"]}**. Worst identified scenario: **{stress["worst_scenario"] or "Not available"}**. Maximum stressed loss: **{fmt_number(stress["worst_loss"])}**. Maximum margin shortfall: **{fmt_number(stress["max_shortfall"])}**. Scenarios with positive shortfall: **{stress["shortfall_scenarios"]}**.

{stress["notes"]} The suite includes historical dislocations, equity, rate, spread, volatility, correlation, liquidity, gap, member-default, and reverse-stress constructs. Scenario governance should establish severity, plausibility, frequency, and breach escalation.

## Procyclicality assessment

Source: **{procyclicality["source"]}**. Maximum daily increase: **{fmt_percent(procyclicality["daily_max_increase"])}**; maximum daily decrease: **{fmt_percent(procyclicality["daily_max_decrease"])}**. Maximum weekly increase: **{fmt_percent(procyclicality["weekly_max_increase"])}**; maximum weekly decrease: **{fmt_percent(procyclicality["weekly_max_decrease"])}**. Peak-to-trough movement: **{fmt_percent(procyclicality["peak_to_trough"])}**. Margin jumps above 10%, 20%, and 30%: **{procyclicality["jumps_10"]}**, **{procyclicality["jumps_20"]}**, and **{procyclicality["jumps_30"]}**. Median member margin-call volatility: **{fmt_percent(procyclicality["member_call_volatility"])}**.

{procyclicality["notes"]} Monitoring should distinguish appropriate risk responsiveness from destabilizing margin amplification and should evaluate volatility floors, stress buffers, depletion, and replenishment behavior.

## Margin-shortfall analysis

Positive shortfalls: **{backtesting["shortfall_count"]}**. Aggregate shortfall: **{fmt_number(backtesting["shortfall_total"])}**. Mean positive shortfall: **{fmt_number(backtesting["shortfall_mean"])}**. Maximum shortfall: **{fmt_number(backtesting["shortfall_max"])}**.

Shortfall analysis should be reviewed by member, date, market regime, portfolio category, MPOR, and cause. Repeated or clustered shortfalls require escalation even when aggregate statistical coverage is acceptable.

## Limitations

The principal limitations are preliminary calibration of non-VaR components, reliance on public and synthetic data, incomplete production operational-control evidence, possible proxy selection when prepared outputs do not explicitly identify baseline rows, and the need for formal governance approval of monitoring thresholds and remediation closure standards.

## Findings

Open findings by severity: Critical **{severity_counts.get("Critical", 0)}**; High **{severity_counts.get("High", 0)}**; Medium **{severity_counts.get("Medium", 0)}**; Low **{severity_counts.get("Low", 0)}**; Observation **{severity_counts.get("Observation", 0)}**.

{markdown_table(["ID", "Severity", "Finding", "Owner", "Target date", "Status"], finding_rows)}

The authoritative tracker is `{rel(TRACKER_PATH)}` and contains the required closure-evidence field.

## Remediation requirements

High findings require closure, independent validation, or formally approved compensating controls before unrestricted production use. Medium findings require dated remediation plans, accountable owners, and committee tracking. Closure packages should include revised methodology, approved calibration evidence, code and configuration changes, test results, production reconciliation, governance approvals, and residual-risk assessment.

## Validation conclusion

The framework is suitable as a comprehensive independent-validation implementation and demonstration environment. It is not yet sufficient evidence for unrestricted production approval because the High calibration finding and production-representativeness limitations remain open. The validation conclusion is therefore **{rating}**.

## Conditions for use

Use is conditioned on: documented scope adherence; approved parameter calibration; satisfactory production-like backtesting; completed production implementation verification; closure or approved acceptance of High and Medium findings; use of non-overlapping observations for formal multi-day independence testing; governed stress and monitoring thresholds; and revalidation after material model, data, portfolio, or infrastructure change.

## Monitoring recommendations

Monitor daily and weekly margin changes, member-level exception counts, Basel traffic-light status, Kupiec and Christoffersen results, margin shortfalls, primary-versus-challenger divergence, concentration and liquidity drivers, stress losses, procyclicality jumps, volatility relationships, floor and buffer utilization, data-quality exceptions, and unresolved findings. Establish explicit warning and breach thresholds, escalation owners, remediation timeframes, and committee reporting cadence.

## Model-risk committee summary

Overall rating: **{rating}**. Principal strengths are comprehensive methodological coverage, reproducible evidence generation, independent challenger comparison, structured stress and sensitivity testing, and explicit procyclicality monitoring. Material limitations are preliminary non-VaR calibration, public and synthetic data, and incomplete production operational-control evidence. Recommendation: **{approval_recommendation}** See `{rel(COMMITTEE_PATH)}` for the approximately two-page committee summary.
"""

committee = f"""# Model-Risk Committee Summary

**Project:** CCP Margin Model Independent Validation YN26  
**Generated:** {TODAY.isoformat()}  
**Overall validation rating:** **{rating}**

## Approval recommendation

**{approval_recommendation}**

The model framework is analytically comprehensive and suitable for continued development, independent validation, controlled testing, and committee review. It should not receive unrestricted production approval while the High calibration finding remains open or while production-data and operational-control evidence is incomplete.

## Principal strengths

1. **Comprehensive model coverage.** The framework includes historical-simulation VaR, a parametric EWMA challenger, one-, three-, and five-day margin periods of risk, liquidity and concentration effects, gap risk, stress buffers, and total-margin aggregation.
2. **Independent validation methods.** Coverage includes Kupiec unconditional coverage, Christoffersen independence, traffic-light classification, margin shortfalls, benchmark comparison, parameter sensitivity, historical and hypothetical stress scenarios, reverse stress, implementation verification, and procyclicality.
3. **Reproducibility and governance.** Configuration files, deterministic portfolio generation, prepared Parquet outputs, test evidence, findings tracking, and documented scope and validation charter support repeatable review.
4. **Monitoring design.** The framework measures margin changes, jump frequencies, member-level volatility, stress performance, challenger divergence, and unresolved findings.

## Material limitations

1. **Non-VaR calibration.** Liquidity, concentration, gap-risk, and stress-buffer parameters remain preliminary and require empirical calibration, governance approval, and periodic recalibration standards.
2. **Data representativeness.** Public market data and synthetic member portfolios do not fully reproduce confidential production positions, intraday calls, collateral dynamics, member behavior, or proprietary liquidity conditions.
3. **Production implementation evidence.** Repository-level testing does not replace production reconciliation, job-control, entitlement, incident-management, change-control, and parallel-run evidence.
4. **Monitoring governance.** Final thresholds, escalation responsibilities, breach disposition, and reporting cadence require formal committee approval.

## High and Medium findings

{markdown_table(["ID", "Severity", "Finding", "Owner", "Remediation deadline", "Status"], finding_rows)}

The complete findings tracker, including recommendations, validation status, and closure evidence, is maintained in `{rel(TRACKER_PATH)}`.

## Validation evidence summary

- Automated test status: **{tests["status"]}**; passed: **{tests["passed"] if tests["passed"] is not None else "Not reported"}**; failed: **{tests["failed"]}**; evidence: `{tests["path"]}`.
- Backtesting: **{backtesting["members"]}** members, **{backtesting["observations"]}** assessed observations, **{backtesting["exceptions"]}** exceptions, and an observed exception rate of **{fmt_percent(backtesting["exception_rate"])}**.
- Traffic-light distribution: **{backtesting["green"]} Green**, **{backtesting["yellow"]} Yellow**, and **{backtesting["red"]} Red** members.
- Kupiec pass rate: **{fmt_percent(backtesting["kupiec_pass_rate"])}**. Christoffersen independence pass rate: **{fmt_percent(backtesting["independence_pass_rate"])}**.
- Sensitivity: **{sensitivity["scenarios"]}** scenarios with mean-margin changes from **{fmt_percent(sensitivity["min_change"])}** to **{fmt_percent(sensitivity["max_change"])}** relative to the selected baseline.
- Stress testing: **{stress["scenarios"]}** scenarios; worst identified scenario **{stress["worst_scenario"] or "Not available"}**; maximum shortfall **{fmt_number(stress["max_shortfall"])}**.
- Margin shortfalls: **{backtesting["shortfall_count"]}** positive shortfalls; maximum **{fmt_number(backtesting["shortfall_max"])}**.
- Procyclicality: maximum daily increase **{fmt_percent(procyclicality["daily_max_increase"])}**; maximum weekly increase **{fmt_percent(procyclicality["weekly_max_increase"])}**; jumps above 10%, 20%, and 30% were **{procyclicality["jumps_10"]}**, **{procyclicality["jumps_20"]}**, and **{procyclicality["jumps_30"]}**.

## Required remediation deadlines

Critical findings, if any, must be closed before any use. High findings should be remediated within approximately 60 days unless the committee approves a shorter deadline or documented compensating controls. Medium findings should be remediated within approximately 90 days. Low findings and observations should be tracked through normal governance and completed within approximately 120 days or the approved monitoring cycle.

Closure requires objective evidence, not only management attestation. Expected evidence includes approved methodology, empirical calibration analysis, governed configurations, code changes, regression tests, production or production-like backtesting, reconciliations, operating procedures, approval records, and independent-validation confirmation.

## Conditions for approval

Any approval should be limited to the documented scope and conditioned on closure or formal acceptance of material findings; satisfactory production-like testing; completed operational-control review; use of non-overlapping observations for formal multi-day independence tests; approved stress and monitoring thresholds; and mandatory revalidation after material changes to data, model methodology, parameters, portfolio population, or technology.

## Committee decision requested

The committee should select one of the following documented outcomes: reject; return for remediation; approve for controlled non-production use; conditionally approve with explicit restrictions and deadlines; or approve for production after all preconditions are satisfied. Based on current evidence, the recommended decision is the approval recommendation stated above.
"""

REPORT_PATH.write_text(report, encoding="utf-8")
COMMITTEE_PATH.write_text(committee, encoding="utf-8")

checks: list[dict[str, str]] = []

def add_check(name: str, passed: bool, detail: str) -> None:
    checks.append(
        {
            "check_name": name,
            "status": "PASS" if passed else "FAIL",
            "detail": detail,
        }
    )

add_check("Independent validation report created", REPORT_PATH.exists() and REPORT_PATH.stat().st_size > 1000, rel(REPORT_PATH))
add_check("Committee summary created", COMMITTEE_PATH.exists() and COMMITTEE_PATH.stat().st_size > 800, rel(COMMITTEE_PATH))
add_check("Findings tracker created", TRACKER_PATH.exists() and TRACKER_PATH.stat().st_size > 100, rel(TRACKER_PATH))
add_check("Findings tracker columns exact", list(findings.columns) == FINDING_COLUMNS, ", ".join(findings.columns))
add_check("Finding IDs unique", findings["finding_id"].is_unique, f"Rows: {len(findings)}")
add_check("Finding severities valid", set(findings["severity"]).issubset(ALLOWED_SEVERITIES), ", ".join(sorted(set(findings["severity"]))))
for section in REQUIRED_REPORT_SECTIONS:
    add_check(f"Report section: {section}", f"## {section}" in report, section)
add_check("Report contains committee rating", rating in report, rating)
add_check("Committee summary includes high/medium findings", "## High and Medium findings" in committee, "Required section present")

checks_df = pd.DataFrame(checks)
checks_df.to_csv(CHECKS_PATH, index=False)

failed_checks = checks_df[checks_df["status"] == "FAIL"]
if not failed_checks.empty:
    print(failed_checks.to_string(index=False))
    raise RuntimeError(f"Step 20 validation failed with {len(failed_checks)} failed checks.")

print("")
print("STEP 20 DELIVERABLES CREATED")
print(f"Report:            {REPORT_PATH}")
print(f"Committee summary: {COMMITTEE_PATH}")
print(f"Findings tracker:  {TRACKER_PATH}")
print(f"Validation checks: {CHECKS_PATH}")
print(f"Metrics summary:   {METRICS_PATH}")
print(f"Overall rating:    {rating}")
'@

$TemporaryPython = Join-Path $ScriptsDir ".step20_generate_deliverables_tmp.py"
Set-Content -LiteralPath $TemporaryPython -Value $PythonSource -Encoding UTF8

try {
    & $Python $TemporaryPython
    if ($LASTEXITCODE -ne 0) {
        throw "The Step 20 Python generator returned exit code $LASTEXITCODE."
    }
}
finally {
    if (Test-Path -LiteralPath $TemporaryPython) {
        Remove-Item -LiteralPath $TemporaryPython -Force
    }
}

Write-Step "Verifying required Step 20 files"

$RequiredFiles = @(
    (Join-Path $ReportsDir "independent_validation_report.md"),
    (Join-Path $ReportsDir "model_risk_committee_summary.md"),
    (Join-Path $EvidenceDir "findings_tracker.csv"),
    (Join-Path $EvidenceDir "step20_validation_checks.csv"),
    (Join-Path $TablesDir "step20_validation_metrics.csv")
)

foreach ($File in $RequiredFiles) {
    if (-not (Test-Path -LiteralPath $File)) {
        throw "Required deliverable was not created: $File"
    }
    Write-Host "PASS: $File"
}

$CheckResults = Import-Csv -LiteralPath (Join-Path $EvidenceDir "step20_validation_checks.csv")
$Failed = @($CheckResults | Where-Object { $_.status -ne "PASS" })

if ($Failed.Count -gt 0) {
    $Failed | Format-Table -AutoSize
    throw "Step 20 contains failed validation checks."
}

if ($Commit) {
    Write-Step "Committing Step 20 deliverables to Git"
    Push-Location $ProjectRoot
    try {
        git add `
            "scripts/20_prepare_validation_deliverables.ps1" `
            "reports/independent_validation_report.md" `
            "reports/model_risk_committee_summary.md" `
            "reports/evidence/findings_tracker.csv" `
            "reports/evidence/pytest_step20.txt" `
            "reports/evidence/step20_validation_checks.csv" `
            "reports/tables/step20_validation_metrics.csv"

        git commit -m "Complete Step 20 validation deliverables"
    }
    finally {
        Pop-Location
    }
}

Write-Step "STEP 20 COMPLETED SUCCESSFULLY"

Write-Host "Created:"
Write-Host "  reports\independent_validation_report.md"
Write-Host "  reports\model_risk_committee_summary.md"
Write-Host "  reports\evidence\findings_tracker.csv"
Write-Host "  reports\evidence\pytest_step20.txt"
Write-Host "  reports\evidence\step20_validation_checks.csv"
Write-Host "  reports\tables\step20_validation_metrics.csv"
Write-Host ""
Write-Host "Review the proposed finding owners, target dates, and approval recommendation before committee use."
