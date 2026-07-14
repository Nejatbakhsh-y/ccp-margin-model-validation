# Independent Validation Report

**Project:** CCP Margin Model Independent Validation YN26  
**Generated:** 2026-07-13  
**Overall validation rating:** **Conditionally Satisfactory**  
**Approval recommendation:** **Conditional approval only. Production use should require closure of High findings or formally approved compensating controls, completion of production-data testing, and satisfactory implementation evidence.**

## Executive conclusion

Independent validation concludes that the CCP margin-model framework is **conditionally satisfactory** for the documented development and validation scope. The framework demonstrates broad methodological coverage: historical-simulation and parametric challenger models, multi-day margin periods of risk, component add-ons, backtesting, statistical coverage tests, sensitivity testing, stress testing, margin-shortfall analysis, and procyclicality monitoring. The principal approval constraint is the open High finding concerning empirical calibration of non-VaR margin components. Production approval also requires production-representative data and operational-control evidence.

## Model purpose and business use

The model estimates daily initial-margin requirements for simulated clearing members. It is intended to cover potential portfolio losses over defined margin periods of risk at a 99% confidence level and to supplement base risk coverage with liquidity, concentration, gap-risk, and stress components. The framework supports independent model validation, benchmark comparison, monitoring, and model-risk governance. It is not, by itself, authorization for live clearing or production use.

## Model inventory

| Component | Method | Principal features | Implementation |
| --- | --- | --- | --- |
| Primary model | Historical-simulation VaR | 99% loss quantile; configurable lookback; 1-, 3-, and 5-day MPOR | src/ccp_margin/models/primary |
| Challenger model | Parametric EWMA VaR | EWMA covariance; PSD control; Normal and optional Student-t | src/ccp_margin/models/challenger |
| Margin components | Base margin plus add-ons | Liquidity, concentration, gap risk, and stress buffer | src/ccp_margin/margin |
| Validation tests | Statistical and implementation validation | Kupiec, Christoffersen, traffic light, shortfall, sensitivity, implementation checks | src/ccp_margin/validation |
| Stress testing | Historical, hypothetical, and reverse stress | Named public stress periods and extreme-but-plausible shocks | src/ccp_margin/stress |
| Monitoring | Procyclicality and stability monitoring | Margin changes, jumps, volatility relationships, and buffer behavior | src/ccp_margin/monitoring |

## Scope and exclusions

Validation covers data-quality controls, portfolio generation, primary and challenger risk measurement, total-margin construction, statistical backtesting, implementation verification, sensitivity testing, stress testing, procyclicality, and documented governance. Exclusions include confidential production-member positions, intraday calls, collateral eligibility and haircut engines, default-fund sizing, waterfall allocation, legal enforceability, live system entitlements, production scheduling, cyber controls, and production change-management evidence.

## Methodology summary

The primary model applies current positions to historical risk-factor returns and estimates the 99th-percentile loss using historical simulation. Directly observed overlapping multi-day returns are used for margin estimation; non-overlapping observations are required for formal independence testing. The challenger model uses EWMA covariance estimation with positive-semidefinite controls. Validation applies Kupiec unconditional coverage, Christoffersen independence, conditional-coverage logic, Basel-style traffic-light classification, margin-shortfall analysis, benchmark comparison, controlled parameter sensitivity, historical and hypothetical stress scenarios, reverse stress, and procyclicality measures.

## Data assessment

| Dataset | Evidence path | Rows | Start date | End date | Members |
| --- | --- | --- | --- | --- | --- |
| Daily member margin | data/processed/daily_member_margin.parquet | 30 | 2026-07-10 | 2026-07-10 | 30 |
| Backtesting source | data/processed/sensitivity_scenario_results.parquet | 150000 |  |  |  |
| Sensitivity source | data/processed/sensitivity_scenario_results.parquet | 150000 |  |  |  |
| Stress source | data/processed/stress_test_results.parquet | 571 |  |  |  |
| Monitoring source | Not available | 0 |  |  |  |
| Data-quality evidence | reports/tables/data_quality_summary.csv | 14 |  |  |  |

The data pipeline is reproducible and includes manifests and quality evidence. Public market data and synthetic portfolios provide transparent test coverage but do not fully represent proprietary member behavior, stressed liquidity, intraday exposure changes, or production data lineage. This limitation is captured in Finding F-002.

## Conceptual-soundness assessment

The core conceptual design is appropriate for a CCP margin framework. Historical simulation avoids strong distributional assumptions and preserves empirical dependence in observed risk-factor returns. The parametric EWMA challenger provides an analytically distinct benchmark. Multi-day horizons, liquidity and concentration effects, stress coverage, and procyclicality controls are conceptually relevant. The material conceptual limitation is that non-VaR add-ons and buffers require completed empirical calibration and governance before production reliance.

## Implementation-verification results

Automated test status: **Passed**. Passed: **Not reported**; failed: **0**; errors: **0**. Evidence: `reports/evidence/pytest_step20.txt`.

The implementation is modular, deterministic, configuration-driven, and organized by data, portfolio, model, margin, validation, stress, and monitoring functions. A passed test suite supports code-level implementation evidence. Production implementation verification remains incomplete until source-to-report reconciliation, access controls, job scheduling, run-book controls, and parallel production testing are evidenced.

## Backtesting results

| Measure | Result |
| --- | --- |
| Members tested | 30 |
| Most-recent observations assessed | 7500 |
| Exceptions | 0 |
| Observed exception rate | 0.00% |
| Traffic-light status | 30 Green; 0 Yellow; 0 Red |
| Kupiec pass rate at 5% | 0.00% |
| Christoffersen independence pass rate at 5% | 0.00% |
| Worst member by exception count | CM001 (0 exceptions) |

Method note: Selected rows flagged as baseline using is_baseline. Calculated exceptions as realized_loss loss greater than margin. Basel traffic-light counts use the most recent 250 observations per member where available. Detailed member-level statistics should be retained as validation evidence.

## Benchmark and challenger comparison

Comparison available: **No**. Comparable observations: **0**. Mean primary margin: **Not available**. Mean challenger margin: **Not available**. Challenger-to-primary mean ratio: **Not available**. Median absolute difference: **Not available**. Challenger higher than primary: **Not available**.

No directly comparable primary and challenger margin fields were found. Material divergence should be investigated by member, market regime, concentration, and MPOR rather than assessed only through an aggregate ratio.

## Sensitivity results

Prepared scenarios: **20**; observations: **150000**; comparison baseline: **baseline**. Mean-margin change range: **-18.94% to 38.68%**. Largest increase: **mpor_days__5**. Largest decrease: **lookback_days__153**.

Scenario mean margins were compared with the explicit baseline scenario. Validation should confirm monotonic and economically intuitive responses for confidence level, lookback, MPOR, EWMA decay, liquidity, concentration, stress buffer, and correlation shocks.

## Stress-testing results

Prepared stress scenarios: **20**; observations: **571**. Worst identified scenario: **HIST_2008_GFC**. Maximum stressed loss: **604,880,052.33**. Maximum margin shortfall: **358,333,835.54**. Scenarios with positive shortfall: **11**.

Stress scenarios were summarized using maximum stressed loss and margin shortfall. The suite includes historical dislocations, equity, rate, spread, volatility, correlation, liquidity, gap, member-default, and reverse-stress constructs. Scenario governance should establish severity, plausibility, frequency, and breach escalation.

## Procyclicality assessment

Source: **Derived from daily member margin**. Maximum daily increase: **Not available**; maximum daily decrease: **Not available**. Maximum weekly increase: **Not available**; maximum weekly decrease: **Not available**. Peak-to-trough movement: **0.00%**. Margin jumps above 10%, 20%, and 30%: **0**, **0**, and **0**. Median member margin-call volatility: **Not available**.

Core change and jump measures were derived from daily member margin. Use the prepared Step 17 monitoring output for volatility correlation, stressed-to-calm ratio, and buffer depletion/replenishment measures. Monitoring should distinguish appropriate risk responsiveness from destabilizing margin amplification and should evaluate volatility floors, stress buffers, depletion, and replenishment behavior.

## Margin-shortfall analysis

Positive shortfalls: **0**. Aggregate shortfall: **0.00**. Mean positive shortfall: **0.00**. Maximum shortfall: **0.00**.

Shortfall analysis should be reviewed by member, date, market regime, portfolio category, MPOR, and cause. Repeated or clustered shortfalls require escalation even when aggregate statistical coverage is acceptable.

## Limitations

The principal limitations are preliminary calibration of non-VaR components, reliance on public and synthetic data, incomplete production operational-control evidence, possible proxy selection when prepared outputs do not explicitly identify baseline rows, and the need for formal governance approval of monitoring thresholds and remediation closure standards.

## Findings

Open findings by severity: Critical **0**; High **1**; Medium **2**; Low **1**; Observation **1**.

| ID | Severity | Finding | Owner | Target date | Status |
| --- | --- | --- | --- | --- | --- |
| F-001 | High | Empirical calibration of non-VaR margin components is incomplete | Model Development | 2026-09-11 | Open |
| F-002 | Medium | Production representativeness is limited by public data and synthetic portfolios | Model Development and Data Engineering | 2026-10-11 | Open |
| F-003 | Medium | Production implementation and operational-control evidence is not complete | Technology and Model Operations | 2026-10-11 | Open |

The authoritative tracker is `reports/evidence/findings_tracker.csv` and contains the required closure-evidence field.

## Remediation requirements

High findings require closure, independent validation, or formally approved compensating controls before unrestricted production use. Medium findings require dated remediation plans, accountable owners, and committee tracking. Closure packages should include revised methodology, approved calibration evidence, code and configuration changes, test results, production reconciliation, governance approvals, and residual-risk assessment.

## Validation conclusion

The framework is suitable as a comprehensive independent-validation implementation and demonstration environment. It is not yet sufficient evidence for unrestricted production approval because the High calibration finding and production-representativeness limitations remain open. The validation conclusion is therefore **Conditionally Satisfactory**.

## Conditions for use

Use is conditioned on: documented scope adherence; approved parameter calibration; satisfactory production-like backtesting; completed production implementation verification; closure or approved acceptance of High and Medium findings; use of non-overlapping observations for formal multi-day independence testing; governed stress and monitoring thresholds; and revalidation after material model, data, portfolio, or infrastructure change.

## Monitoring recommendations

Monitor daily and weekly margin changes, member-level exception counts, Basel traffic-light status, Kupiec and Christoffersen results, margin shortfalls, primary-versus-challenger divergence, concentration and liquidity drivers, stress losses, procyclicality jumps, volatility relationships, floor and buffer utilization, data-quality exceptions, and unresolved findings. Establish explicit warning and breach thresholds, escalation owners, remediation timeframes, and committee reporting cadence.

## Model-risk committee summary

Overall rating: **Conditionally Satisfactory**. Principal strengths are comprehensive methodological coverage, reproducible evidence generation, independent challenger comparison, structured stress and sensitivity testing, and explicit procyclicality monitoring. Material limitations are preliminary non-VaR calibration, public and synthetic data, and incomplete production operational-control evidence. Recommendation: **Conditional approval only. Production use should require closure of High findings or formally approved compensating controls, completion of production-data testing, and satisfactory implementation evidence.** See `reports/model_risk_committee_summary.md` for the approximately two-page committee summary.
