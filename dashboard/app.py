from __future__ import annotations
import re

import math
import sqlite3

import duckdb
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import chi2

st.set_page_config(
    page_title="CCP Margin Model Independent Validation",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).resolve().parents[1]

DATASETS = {
    "daily_margin": [
        "data/processed/daily_member_margin.parquet",
        "data/processed/daily_member_margin.csv",
        "reports/tables/daily_member_margin.csv",
    ],
    "backtesting": [
        "data/processed/backtesting_results.parquet",
        "data/processed/backtesting_results.csv",
        "reports/tables/backtesting_results.csv",
        "reports/evidence/backtesting_results.csv",
    ],
    "validation_tests": [
        "data/processed/validation_test_results.parquet",
        "data/processed/validation_test_results.csv",
        "reports/tables/validation_test_results.csv",
        "reports/tables/backtesting_test_results.csv",
        "reports/evidence/validation_test_results.csv",
    ],
    "sensitivity": [
        "data/processed/sensitivity_scenario_results.parquet",
        "data/processed/sensitivity_scenario_results.csv",
        "reports/tables/sensitivity_scenario_results.csv",
    ],
    "stress": [
        "data/processed/stress_test_results.parquet",
        "data/processed/stress_test_results.csv",
        "reports/tables/stress_test_results.csv",
        "reports/evidence/stress_test_results.csv",
    ],
    "procyclicality": [
        "data/processed/monitoring_metrics.parquet",
        "data/processed/monitoring_metrics.csv",
        "data/processed/procyclicality_metrics.parquet",
        "data/processed/procyclicality_metrics.csv",
        "reports/tables/procyclicality_summary.csv",
        "reports/evidence/procyclicality_metrics.csv",
    ],
    "findings": [
        "data/processed/validation_findings.parquet",
        "data/processed/validation_findings.csv",
        "reports/evidence/findings.csv",
        "reports/findings_tracker.csv",
        "reports/evidence/validation_findings.csv",
        "reports/tables/validation_findings.csv",
    ],
}

SQL_TABLES = {
    "daily_margin": ["daily_margin"],
    "backtesting": ["backtesting_results"],
    "validation_tests": ["validation_test_results", "backtesting_test_results"],
    "sensitivity": ["sensitivity_results", "sensitivity_scenario_results"],
    "stress": ["stress_results", "stress_test_results"],
    "procyclicality": ["monitoring_metrics", "procyclicality_metrics"],
    "findings": ["validation_findings", "findings"],
}


def _database_candidates() -> list[Path]:
    preferred = [
        ROOT / "data/processed/ccp_margin_validation.duckdb",
        ROOT / "data/processed/ccp_margin_model_validation.duckdb",
        ROOT / "data/processed/ccp_margin.duckdb",
        ROOT / "data/processed/validation_results.duckdb",
        ROOT / "data/processed/ccp_validation.duckdb",
        ROOT / "sql/ccp_margin_validation.duckdb",
        ROOT / "data/processed/ccp_margin_validation.db",
        ROOT / "data/processed/ccp_margin.db",
        ROOT / "data/processed/validation_results.db",
        ROOT / "data/processed/ccp_validation.db",
        ROOT / "sql/ccp_margin_validation.db",
    ]
    discovered = (
        list((ROOT / "data").rglob("*.duckdb"))
        + list((ROOT / "sql").rglob("*.duckdb"))
        + list((ROOT / "data").rglob("*.db"))
        + list((ROOT / "data").rglob("*.sqlite"))
        + list((ROOT / "sql").rglob("*.db"))
        + list((ROOT / "sql").rglob("*.sqlite"))
    )
    ordered: list[Path] = []
    for path in preferred + discovered:
        if path.exists() and path not in ordered:
            ordered.append(path)
    return ordered


@st.cache_data(show_spinner=False)
def _read_file(path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    path = Path(path_text)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported dashboard data format: {suffix}")


@st.cache_data(show_spinner=False)
def _read_sqlite(path_text: str, table: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    with sqlite3.connect(path_text) as connection:
        return pd.read_sql_query(f'SELECT * FROM "{table}"', connection)


@st.cache_data(show_spinner=False)
def _read_duckdb(path_text: str, table: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    with duckdb.connect(path_text, read_only=True) as connection:
        return connection.execute(f'SELECT * FROM "{table}"').df()


def _sqlite_tables(path: Path) -> set[str]:
    try:
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        return {str(row[0]) for row in rows}
    except sqlite3.Error:
        return set()


def _duckdb_tables(path: Path) -> set[str]:
    try:
        with duckdb.connect(str(path), read_only=True) as connection:
            rows = connection.execute("SHOW TABLES").fetchall()
        return {str(row[0]) for row in rows}
    except Exception:
        return set()


def _load_database_dataset(name: str) -> tuple[pd.DataFrame, str]:
    for database in _database_candidates():
        suffix = database.suffix.lower()
        if suffix == ".duckdb":
            tables = _duckdb_tables(database)
            reader = _read_duckdb
        else:
            tables = _sqlite_tables(database)
            reader = _read_sqlite

        for table in SQL_TABLES.get(name, []):
            if table not in tables:
                continue

            try:
                label = f"{database.relative_to(ROOT)} :: {table}"
            except ValueError:
                label = f"{database} :: {table}"

            try:
                frame = reader(str(database), table, database.stat().st_mtime_ns)
                return frame, label
            except Exception as exc:
                st.warning(f"Could not read {label}: {exc}")

    return pd.DataFrame(), "Not found"


def load_dataset(name: str) -> tuple[pd.DataFrame, str]:
    database_frame, database_source = _load_database_dataset(name)
    if not database_frame.empty:
        return database_frame, database_source

    for relative in DATASETS[name]:
        path = ROOT / relative
        if path.exists():
            try:
                return _read_file(str(path), path.stat().st_mtime_ns), relative
            except Exception as exc:
                st.warning(f"Could not read {relative}: {exc}")

    return pd.DataFrame(), "Not found"


def find_col(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lookup = {str(column).strip().lower(): str(column) for column in df.columns}
    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    return None


def date_col(df: pd.DataFrame) -> str | None:
    return find_col(
        df,
        [
            "date",
            "valuation_date",
            "as_of_date",
            "business_date",
            "test_date",
            "observation_date",
        ],
    )


def member_col(df: pd.DataFrame) -> str | None:
    return find_col(df, ["member_id", "clearing_member_id", "member", "portfolio_id"])


def margin_col(df: pd.DataFrame) -> str | None:
    recognized = find_col(
        df,
        [
            "total_margin",
            "total_initial_margin",
            "margin",
            "initial_margin",
            "margin_amount",
            "required_margin",
            "total_required_margin",
            "margin_requirement",
            "aggregate_margin",
            "base_margin",
        ],
    )
    if recognized:
        return recognized

    for column in df.columns:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(column).strip().lower()).strip("_")
        if "margin" in normalized and any(
            token in normalized
            for token in (
                "total",
                "initial",
                "required",
                "requirement",
                "amount",
                "aggregate",
            )
        ):
            return str(column)

    return None


def realized_loss_col(df: pd.DataFrame) -> str | None:
    return find_col(
        df,
        [
            "realized_loss",
            "loss",
            "realized_portfolio_loss",
            "forward_loss",
            "pnl_loss",
        ],
    )


def scenario_col(df: pd.DataFrame) -> str | None:
    return find_col(df, ["scenario_id", "scenario", "scenario_name", "stress_scenario"])


def parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    output = df.copy()
    column = date_col(output)
    if column:
        output[column] = pd.to_datetime(output[column], errors="coerce")
    return output


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def money(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    if absolute >= 1_000:
        return f"${value / 1_000:,.2f}K"
    return f"${value:,.2f}"


def pct(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.2%}"


def source_caption(source: str, rows: int) -> None:
    st.caption(f"Prepared source: {source} | Rows loaded: {rows:,}")


def missing_panel(dataset: str, expected: list[str] | None = None) -> None:
    st.error(f"No prepared {dataset} dataset was found.")
    if expected:
        st.code("\n".join(expected), language="text")
    st.info(
        "Run the corresponding completed model or validation generator first. "
        "The dashboard intentionally does not download raw data or rebuild the analytical pipeline."
    )


def filter_members(df: pd.DataFrame, key: str) -> pd.DataFrame:
    column = member_col(df)
    if not column:
        return df
    values = sorted(df[column].dropna().astype(str).unique().tolist())
    selected = st.multiselect("Clearing members", values, default=values, key=key)
    if not selected:
        return df.iloc[0:0]
    return df[df[column].astype(str).isin(selected)]


def filter_dates(df: pd.DataFrame, key: str) -> pd.DataFrame:
    column = date_col(df)
    if not column or df[column].dropna().empty:
        return df
    start = df[column].min().date()
    end = df[column].max().date()
    selected = st.date_input(
        "Date range",
        value=(start, end),
        min_value=start,
        max_value=end,
        key=key,
    )
    if isinstance(selected, tuple) and len(selected) == 2:
        lower = pd.Timestamp(selected[0])
        upper = pd.Timestamp(selected[1]) + pd.Timedelta(days=1)
        return df[(df[column] >= lower) & (df[column] < upper)]
    return df


def prepare_backtesting(df: pd.DataFrame) -> pd.DataFrame:
    output = parse_dates(df)
    sc = scenario_col(output)
    if sc:
        text = output[sc].astype(str).str.lower()
        baseline = output[text.str.contains("base|baseline", regex=True, na=False)]
        if not baseline.empty:
            output = baseline
        elif output[sc].nunique(dropna=True) > 1:
            first = sorted(output[sc].dropna().astype(str).unique().tolist())[0]
            output = output[output[sc].astype(str) == first]

    margin = margin_col(output)
    loss = realized_loss_col(output)
    exception = find_col(
        output, ["exception", "is_exception", "breach", "margin_breach"]
    )
    if margin:
        output[margin] = to_numeric(output[margin])
    if loss:
        output[loss] = to_numeric(output[loss])
    if exception:
        if output[exception].dtype == bool:
            output["_exception"] = output[exception]
        else:
            output["_exception"] = (
                output[exception]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin({"1", "true", "yes", "y", "exception", "breach"})
            )
    elif margin and loss:
        output["_exception"] = output[loss] > output[margin]
    else:
        output["_exception"] = False

    if margin and loss:
        output["_shortfall"] = (output[loss] - output[margin]).clip(lower=0)
    else:
        shortfall = find_col(
            output, ["margin_shortfall", "shortfall", "shortfall_amount"]
        )
        output["_shortfall"] = (
            to_numeric(output[shortfall]).clip(lower=0) if shortfall else 0.0
        )
    return output


def kupiec_test(
    exceptions: pd.Series, target_probability: float = 0.01
) -> dict[str, float | int | bool]:
    values = exceptions.fillna(False).astype(bool)
    n = int(len(values))
    x = int(values.sum())
    if n == 0:
        return {
            "n": 0,
            "x": 0,
            "rate": np.nan,
            "lr": np.nan,
            "p_value": np.nan,
            "pass": False,
        }
    observed = x / n
    eps = 1e-12
    p = min(max(target_probability, eps), 1 - eps)
    phat = min(max(observed, eps), 1 - eps)
    log_null = (n - x) * math.log(1 - p) + x * math.log(p)
    log_alt = (n - x) * math.log(1 - phat) + x * math.log(phat)
    lr = max(0.0, -2.0 * (log_null - log_alt))
    p_value = float(chi2.sf(lr, 1))
    return {
        "n": n,
        "x": x,
        "rate": observed,
        "lr": lr,
        "p_value": p_value,
        "pass": p_value >= 0.05,
    }


def christoffersen_test(exceptions: pd.Series) -> dict[str, float | int | bool]:
    values = exceptions.fillna(False).astype(int).to_numpy()
    if len(values) < 2:
        return {
            "n00": 0,
            "n01": 0,
            "n10": 0,
            "n11": 0,
            "lr": np.nan,
            "p_value": np.nan,
            "pass": False,
        }
    previous = values[:-1]
    current = values[1:]
    n00 = int(((previous == 0) & (current == 0)).sum())
    n01 = int(((previous == 0) & (current == 1)).sum())
    n10 = int(((previous == 1) & (current == 0)).sum())
    n11 = int(((previous == 1) & (current == 1)).sum())
    eps = 1e-12

    pi0 = n01 / max(n00 + n01, 1)
    pi1 = n11 / max(n10 + n11, 1)
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    pi0 = min(max(pi0, eps), 1 - eps)
    pi1 = min(max(pi1, eps), 1 - eps)
    pi = min(max(pi, eps), 1 - eps)

    log_null = (n00 + n10) * math.log(1 - pi) + (n01 + n11) * math.log(pi)
    log_alt = (
        n00 * math.log(1 - pi0)
        + n01 * math.log(pi0)
        + n10 * math.log(1 - pi1)
        + n11 * math.log(pi1)
    )
    lr = max(0.0, -2.0 * (log_null - log_alt))
    p_value = float(chi2.sf(lr, 1))
    return {
        "n00": n00,
        "n01": n01,
        "n10": n10,
        "n11": n11,
        "lr": lr,
        "p_value": p_value,
        "pass": p_value >= 0.05,
    }


def traffic_light_label(exceptions: int, observations: int) -> str:
    if observations <= 0:
        return "Insufficient data"
    scaled = exceptions * 250 / observations
    if scaled <= 4:
        return "Green"
    if scaled <= 9:
        return "Yellow"
    return "Red"


def page_executive_summary() -> None:
    st.title("Executive Summary")
    st.write(
        "Independent validation dashboard for margin adequacy, backtesting, stress performance, "
        "sensitivity, procyclicality, and finding remediation."
    )

    daily, daily_source = load_dataset("daily_margin")
    backtest, back_source = load_dataset("backtesting")
    validation, validation_source = load_dataset("validation_tests")
    sensitivity, sensitivity_source = load_dataset("sensitivity")
    stress, stress_source = load_dataset("stress")
    procyclicality, procyclicality_source = load_dataset("procyclicality")
    findings, findings_source = load_dataset("findings")

    latest_total = np.nan
    members = np.nan
    if not daily.empty:
        daily = parse_dates(daily)
        dc, mc, mm = date_col(daily), member_col(daily), margin_col(daily)
        if mm:
            daily[mm] = to_numeric(daily[mm])
            latest = daily[daily[dc] == daily[dc].max()] if dc else daily
            latest_total = latest[mm].sum()
            members = latest[mc].nunique() if mc else len(latest)

    exceptions = np.nan
    exception_rate = np.nan
    if not backtest.empty:
        prepared = prepare_backtesting(backtest)
        exceptions = int(prepared["_exception"].sum())
        exception_rate = (
            float(prepared["_exception"].mean()) if len(prepared) else np.nan
        )

    open_high = 0 if findings_source != "Not found" else np.nan
    if not findings.empty:
        severity = find_col(findings, ["severity", "rating", "risk_rating"])
        status = find_col(findings, ["status", "finding_status", "remediation_status"])
        mask = pd.Series(True, index=findings.index)
        if severity:
            mask &= (
                findings[severity].astype(str).str.lower().isin(["critical", "high"])
            )
        if status:
            mask &= ~findings[status].astype(str).str.lower().isin(
                ["closed", "resolved", "complete", "completed"]
            )
        open_high = int(mask.sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest total margin", money(latest_total))
    c2.metric("Active members", "N/A" if pd.isna(members) else f"{int(members):,}")
    c3.metric(
        "Backtesting exceptions",
        "N/A" if pd.isna(exceptions) else f"{int(exceptions):,}",
        pct(exception_rate),
    )
    c4.metric(
        "Open Critical/High findings",
        "N/A" if pd.isna(open_high) else f"{int(open_high):,}",
    )

    if not daily.empty:
        dc, mm = date_col(daily), margin_col(daily)
        if dc and mm:
            trend = (
                daily.dropna(subset=[dc])
                .groupby(dc, as_index=True)[mm]
                .sum()
                .sort_index()
                .rename("Total margin")
            )
            st.subheader("Aggregate margin trend")
            st.line_chart(trend)

    st.subheader("Prepared-data readiness")
    readiness = pd.DataFrame(
        [
            {
                "Area": "Daily member margin",
                "Status": "Ready" if not daily.empty else "Missing",
                "Source": daily_source,
                "Rows": len(daily),
            },
            {
                "Area": "Backtesting",
                "Status": "Ready" if not backtest.empty else "Missing",
                "Source": back_source,
                "Rows": len(backtest),
            },
            {
                "Area": "Validation tests",
                "Status": "Ready"
                if (not validation.empty or not backtest.empty)
                else "Missing",
                "Source": validation_source
                if not validation.empty
                else (
                    f"Derived from {back_source}" if not backtest.empty else "Not found"
                ),
                "Rows": len(validation) if not validation.empty else len(backtest),
            },
            {
                "Area": "Sensitivity analysis",
                "Status": "Ready" if not sensitivity.empty else "Missing",
                "Source": sensitivity_source,
                "Rows": len(sensitivity),
            },
            {
                "Area": "Stress testing",
                "Status": "Ready" if not stress.empty else "Missing",
                "Source": stress_source,
                "Rows": len(stress),
            },
            {
                "Area": "Procyclicality",
                "Status": "Ready" if not procyclicality.empty else "Missing",
                "Source": procyclicality_source,
                "Rows": len(procyclicality),
            },
            {
                "Area": "Findings",
                "Status": "Ready" if findings_source != "Not found" else "Missing",
                "Source": findings_source,
                "Rows": len(findings),
            },
        ]
    )
    st.dataframe(readiness, width="stretch", hide_index=True)

    st.info(
        "This application reads prepared DuckDB, SQLite, Parquet, or CSV outputs only. "
        "It does not download market data, regenerate portfolios, or rerun margin models at startup."
    )


def page_daily_member_margin() -> None:
    st.title("Daily Member Margin")
    df, source = load_dataset("daily_margin")
    if df.empty:
        missing_panel("daily member margin", DATASETS["daily_margin"])
        return
    df = parse_dates(df)
    source_caption(source, len(df))
    df = filter_dates(df, "daily_date")
    df = filter_members(df, "daily_member")

    dc, mc, mm = date_col(df), member_col(df), margin_col(df)
    if not mm:
        st.error("A recognized margin column is required.")
        st.dataframe(df, width="stretch")
        return
    df[mm] = to_numeric(df[mm])
    latest = df[df[dc] == df[dc].max()] if dc and not df.empty else df
    c1, c2, c3 = st.columns(3)
    c1.metric("Latest selected margin", money(latest[mm].sum()))
    c2.metric("Average daily member margin", money(df[mm].mean()))
    c3.metric("Selected members", f"{df[mc].nunique():,}" if mc else "N/A")

    if dc and mc:
        pivot = df.pivot_table(
            index=dc, columns=mc, values=mm, aggfunc="sum"
        ).sort_index()
        st.line_chart(pivot)
    elif dc:
        st.line_chart(df.groupby(dc)[mm].sum().sort_index())
    st.dataframe(
        df.sort_values(dc, ascending=False) if dc else df,
        width="stretch",
        hide_index=True,
    )


def page_backtesting_exceptions() -> None:
    st.title("Backtesting Exceptions")
    raw, source = load_dataset("backtesting")
    if raw.empty:
        missing_panel("backtesting", DATASETS["backtesting"])
        return
    df = prepare_backtesting(raw)
    source_caption(source, len(df))
    df = filter_dates(df, "bt_date")
    df = filter_members(df, "bt_member")

    margin, loss = margin_col(df), realized_loss_col(df)
    c1, c2, c3 = st.columns(3)
    c1.metric("Observations", f"{len(df):,}")
    c2.metric("Exceptions", f"{int(df['_exception'].sum()):,}")
    c3.metric("Exception rate", pct(df["_exception"].mean() if len(df) else np.nan))

    if margin and loss:
        chart_df = df[[margin, loss]].apply(pd.to_numeric, errors="coerce")
        st.scatter_chart(chart_df, x=margin, y=loss)
    exceptions = df[df["_exception"]].copy()
    st.subheader("Exception observations")
    st.dataframe(exceptions, width="stretch", hide_index=True)


def page_traffic_light() -> None:
    st.title("Basel Traffic-Light Status")
    raw, source = load_dataset("backtesting")
    if raw.empty:
        missing_panel("backtesting", DATASETS["backtesting"])
        return
    df = prepare_backtesting(raw)
    source_caption(source, len(df))
    mc = member_col(df)
    groups = df.groupby(mc, dropna=False) if mc else [("All members", df)]
    records = []
    for member, group in groups:
        n = len(group)
        x = int(group["_exception"].sum())
        records.append(
            {
                "Member": str(member),
                "Observations": n,
                "Exceptions": x,
                "Exception rate": x / n if n else np.nan,
                "250-day equivalent exceptions": x * 250 / n if n else np.nan,
                "Traffic light": traffic_light_label(x, n),
            }
        )
    result = pd.DataFrame(records)
    counts = result["Traffic light"].value_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("Green", int(counts.get("Green", 0)))
    c2.metric("Yellow", int(counts.get("Yellow", 0)))
    c3.metric("Red", int(counts.get("Red", 0)))
    st.caption(
        "Classification uses 250-observation equivalent exception counts: Green 0-4, Yellow 5-9, Red 10 or more."
    )
    st.dataframe(
        result.style.format(
            {"Exception rate": "{:.2%}", "250-day equivalent exceptions": "{:.2f}"}
        ),
        width="stretch",
        hide_index=True,
    )


def page_validation_tests() -> None:
    st.title("Kupiec and Christoffersen Results")
    existing, existing_source = load_dataset("validation_tests")
    if not existing.empty:
        source_caption(existing_source, len(existing))
        st.dataframe(existing, width="stretch", hide_index=True)
        st.divider()

    raw, source = load_dataset("backtesting")
    if raw.empty:
        if existing.empty:
            missing_panel(
                "validation-test or backtesting",
                DATASETS["validation_tests"] + DATASETS["backtesting"],
            )
        return

    df = prepare_backtesting(raw)
    source_caption(source, len(df))
    mc, dc = member_col(df), date_col(df)
    groups = df.groupby(mc, dropna=False) if mc else [("All members", df)]
    rows = []
    for member, group in groups:
        if dc:
            group = group.sort_values(dc)
        kupiec = kupiec_test(group["_exception"])
        independence = christoffersen_test(group["_exception"])
        conditional_lr = (
            float(kupiec["lr"]) + float(independence["lr"])
            if not pd.isna(kupiec["lr"]) and not pd.isna(independence["lr"])
            else np.nan
        )
        conditional_p = (
            float(chi2.sf(conditional_lr, 2)) if not pd.isna(conditional_lr) else np.nan
        )
        rows.append(
            {
                "Member": str(member),
                "Observations": kupiec["n"],
                "Exceptions": kupiec["x"],
                "Observed exception rate": kupiec["rate"],
                "Kupiec LR": kupiec["lr"],
                "Kupiec p-value": kupiec["p_value"],
                "Kupiec pass": kupiec["pass"],
                "Christoffersen LR": independence["lr"],
                "Christoffersen p-value": independence["p_value"],
                "Independence pass": independence["pass"],
                "Conditional coverage LR": conditional_lr,
                "Conditional coverage p-value": conditional_p,
                "Conditional coverage pass": bool(conditional_p >= 0.05)
                if not pd.isna(conditional_p)
                else False,
            }
        )
    result = pd.DataFrame(rows)
    st.dataframe(
        result.style.format(
            {
                "Observed exception rate": "{:.2%}",
                "Kupiec LR": "{:.4f}",
                "Kupiec p-value": "{:.4f}",
                "Christoffersen LR": "{:.4f}",
                "Christoffersen p-value": "{:.4f}",
                "Conditional coverage LR": "{:.4f}",
                "Conditional coverage p-value": "{:.4f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )


def page_margin_shortfalls() -> None:
    st.title("Margin Shortfalls")
    raw, source = load_dataset("backtesting")
    if raw.empty:
        missing_panel("backtesting", DATASETS["backtesting"])
        return
    df = prepare_backtesting(raw)
    source_caption(source, len(df))
    df = filter_dates(df, "shortfall_date")
    df = filter_members(df, "shortfall_member")

    shortfall = to_numeric(df["_shortfall"]).fillna(0)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total shortfall", money(shortfall.sum()))
    c2.metric("Maximum shortfall", money(shortfall.max() if len(shortfall) else np.nan))
    c3.metric(
        "Shortfall frequency", pct((shortfall > 0).mean() if len(shortfall) else np.nan)
    )

    dc, mc = date_col(df), member_col(df)
    if dc:
        trend = (
            df.assign(_shortfall=shortfall).groupby(dc)["_shortfall"].sum().sort_index()
        )
        st.line_chart(trend)
    columns = [
        column
        for column in [dc, mc, margin_col(df), realized_loss_col(df), "_shortfall"]
        if column
    ]
    st.dataframe(
        df.loc[shortfall > 0, columns].sort_values("_shortfall", ascending=False),
        width="stretch",
        hide_index=True,
    )


def page_sensitivity() -> None:
    st.title("Sensitivity Analysis")
    df, source = load_dataset("sensitivity")
    if df.empty:
        missing_panel("sensitivity", DATASETS["sensitivity"])
        return
    df = parse_dates(df)
    source_caption(source, len(df))
    sc, mm, mc = scenario_col(df), margin_col(df), member_col(df)
    if not sc or not mm:
        st.error(
            "Sensitivity data must contain recognized scenario and margin columns."
        )
        st.dataframe(df, width="stretch")
        return
    df[mm] = to_numeric(df[mm])
    members = sorted(df[mc].dropna().astype(str).unique().tolist()) if mc else []
    if members:
        selected = st.multiselect(
            "Clearing members", members, default=members, key="sens_member"
        )
        df = df[df[mc].astype(str).isin(selected)]

    scenario_summary = (
        df.groupby(sc, dropna=False)[mm]
        .agg(["count", "mean", "median", "max"])
        .reset_index()
        .rename(
            columns={
                "count": "Observations",
                "mean": "Mean margin",
                "median": "Median margin",
                "max": "Maximum margin",
            }
        )
    )
    scenario_text = scenario_summary[sc].astype(str).str.lower()
    baseline_rows = scenario_summary[
        scenario_text.str.contains("base|baseline", regex=True, na=False)
    ]
    baseline = (
        float(baseline_rows["Mean margin"].iloc[0])
        if not baseline_rows.empty
        else float(scenario_summary["Mean margin"].iloc[0])
    )
    scenario_summary["Change versus baseline"] = (
        scenario_summary["Mean margin"] / baseline - 1 if baseline else np.nan
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Scenarios", f"{scenario_summary[sc].nunique():,}")
    c2.metric("Largest mean margin", money(scenario_summary["Mean margin"].max()))
    c3.metric(
        "Largest increase versus baseline",
        pct(scenario_summary["Change versus baseline"].max()),
    )
    st.bar_chart(scenario_summary.set_index(sc)["Change versus baseline"])
    st.dataframe(
        scenario_summary.style.format(
            {
                "Mean margin": "${:,.2f}",
                "Median margin": "${:,.2f}",
                "Maximum margin": "${:,.2f}",
                "Change versus baseline": "{:.2%}",
            }
        ),
        width="stretch",
        hide_index=True,
    )


def page_stress() -> None:
    st.title("Stress Testing")
    df, source = load_dataset("stress")
    if df.empty:
        missing_panel("stress testing", DATASETS["stress"])
        return
    df = parse_dates(df)
    source_caption(source, len(df))
    sc = scenario_col(df)
    mc = member_col(df)
    loss = find_col(
        df, ["stress_loss", "loss", "scenario_loss", "stressed_loss", "realized_loss"]
    )
    shortfall = find_col(df, ["margin_shortfall", "shortfall", "stress_shortfall"])
    margin = margin_col(df)
    if sc:
        selected = st.multiselect(
            "Stress scenarios",
            sorted(df[sc].dropna().astype(str).unique().tolist()),
            default=sorted(df[sc].dropna().astype(str).unique().tolist()),
            key="stress_scenario",
        )
        df = df[df[sc].astype(str).isin(selected)]
    if mc:
        df = filter_members(df, "stress_member")
    for column in [loss, shortfall, margin]:
        if column:
            df[column] = to_numeric(df[column])
    if not shortfall and loss and margin:
        df["_stress_shortfall"] = (df[loss] - df[margin]).clip(lower=0)
        shortfall = "_stress_shortfall"

    c1, c2, c3 = st.columns(3)
    c1.metric("Scenarios selected", f"{df[sc].nunique():,}" if sc else "N/A")
    c2.metric("Maximum stress loss", money(df[loss].max()) if loss else "N/A")
    c3.metric(
        "Maximum stress shortfall", money(df[shortfall].max()) if shortfall else "N/A"
    )
    if sc and loss:
        summary = df.groupby(sc)[loss].sum().sort_values(ascending=False)
        st.bar_chart(summary)
    sort_column = shortfall or loss
    st.dataframe(
        df.sort_values(sort_column, ascending=False) if sort_column else df,
        width="stretch",
        hide_index=True,
    )


def page_procyclicality() -> None:
    st.title("Procyclicality")
    metrics, source = load_dataset("procyclicality")
    if not metrics.empty:
        metrics = parse_dates(metrics)
        source_caption(source, len(metrics))
        numeric_columns = metrics.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_columns:
            selected_metric = st.selectbox(
                "Prepared monitoring metric", numeric_columns
            )
            dc = date_col(metrics)
            if dc:
                trend = (
                    metrics.dropna(subset=[dc])
                    .groupby(dc)[selected_metric]
                    .mean()
                    .sort_index()
                )
                st.line_chart(trend)
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Latest",
                f"{to_numeric(metrics[selected_metric]).dropna().iloc[-1]:,.4f}"
                if to_numeric(metrics[selected_metric]).notna().any()
                else "N/A",
            )
            c2.metric("Maximum", f"{to_numeric(metrics[selected_metric]).max():,.4f}")
            c3.metric("Minimum", f"{to_numeric(metrics[selected_metric]).min():,.4f}")
        st.dataframe(metrics, width="stretch", hide_index=True)
        return

    daily, daily_source = load_dataset("daily_margin")
    if daily.empty:
        missing_panel("procyclicality monitoring", DATASETS["procyclicality"])
        return
    daily = parse_dates(daily)
    dc, mm = date_col(daily), margin_col(daily)
    if not dc or not mm:
        st.error("Prepared daily margin data lacks recognized date or margin columns.")
        return
    source_caption(f"{daily_source} (fallback summary)", len(daily))
    daily[mm] = to_numeric(daily[mm])
    aggregate = (
        daily.groupby(dc)[mm].sum().sort_index().rename("Total margin").to_frame()
    )
    aggregate["Daily change"] = aggregate["Total margin"].pct_change()
    aggregate["Weekly change"] = aggregate["Total margin"].pct_change(5)
    running_max = aggregate["Total margin"].cummax()
    aggregate["Drawdown"] = aggregate["Total margin"] / running_max - 1
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Maximum daily increase", pct(aggregate["Daily change"].max()))
    c2.metric("Peak-to-trough movement", pct(aggregate["Drawdown"].min()))
    c3.metric("Jumps above 10%", int((aggregate["Daily change"] > 0.10).sum()))
    c4.metric("Jumps above 20%", int((aggregate["Daily change"] > 0.20).sum()))
    st.line_chart(aggregate[["Daily change", "Weekly change"]])
    st.dataframe(aggregate.reset_index(), width="stretch", hide_index=True)
    st.warning(
        "The prepared monitoring/procyclicality output was not found. "
        "This page is showing a limited summary calculated from prepared daily margin only."
    )


def page_findings() -> None:
    st.title("Findings and Remediation")
    df, source = load_dataset("findings")
    if df.empty:
        if source != "Not found":
            source_caption(source, 0)
            st.success("No validation findings are currently recorded.")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Selected findings", 0)
            c2.metric("Open findings", 0)
            c3.metric("Open Critical/High", 0)
            c4.metric("Overdue remediation", 0)
            st.dataframe(df, width="stretch", hide_index=True)
            return

        missing_panel("validation findings", DATASETS["findings"])
        return
    source_caption(source, len(df))
    severity = find_col(df, ["severity", "rating", "risk_rating"])
    status = find_col(df, ["status", "finding_status", "remediation_status"])
    owner = find_col(df, ["owner", "finding_owner", "remediation_owner"])
    due = find_col(df, ["due_date", "target_date", "remediation_due_date"])
    if due:
        df[due] = pd.to_datetime(df[due], errors="coerce")
    if severity:
        values = sorted(df[severity].dropna().astype(str).unique().tolist())
        selected = st.multiselect("Severity", values, default=values)
        df = df[df[severity].astype(str).isin(selected)]
    if status:
        values = sorted(df[status].dropna().astype(str).unique().tolist())
        selected = st.multiselect("Status", values, default=values)
        df = df[df[status].astype(str).isin(selected)]

    open_mask = pd.Series(True, index=df.index)
    if status:
        open_mask = ~df[status].astype(str).str.lower().isin(
            ["closed", "resolved", "complete", "completed"]
        )
    overdue = pd.Series(False, index=df.index)
    if due:
        overdue = (
            open_mask & df[due].notna() & (df[due] < pd.Timestamp.today().normalize())
        )
    high = pd.Series(False, index=df.index)
    if severity:
        high = df[severity].astype(str).str.lower().isin(["critical", "high"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected findings", len(df))
    c2.metric("Open findings", int(open_mask.sum()))
    c3.metric("Open Critical/High", int((open_mask & high).sum()))
    c4.metric("Overdue remediation", int(overdue.sum()))
    if owner:
        st.subheader("Open findings by owner")
        st.bar_chart(df.loc[open_mask, owner].astype(str).value_counts())
    st.dataframe(df, width="stretch", hide_index=True)


def main() -> None:
    st.sidebar.title("CCP Margin Validation")
    st.sidebar.caption("Independent validation evidence dashboard")
    pages = [
        st.Page(page_executive_summary, title="Executive summary", default=True),
        st.Page(page_daily_member_margin, title="Daily member margin"),
        st.Page(page_backtesting_exceptions, title="Backtesting exceptions"),
        st.Page(page_traffic_light, title="Basel traffic-light status"),
        st.Page(page_validation_tests, title="Kupiec and Christoffersen"),
        st.Page(page_margin_shortfalls, title="Margin shortfalls"),
        st.Page(page_sensitivity, title="Sensitivity analysis"),
        st.Page(page_stress, title="Stress testing"),
        st.Page(page_procyclicality, title="Procyclicality"),
        st.Page(page_findings, title="Findings and remediation"),
    ]
    navigation = st.navigation(pages)
    navigation.run()


if __name__ == "__main__":
    main()
