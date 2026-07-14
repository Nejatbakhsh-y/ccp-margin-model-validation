# Model-Risk Committee Summary

**Project:** CCP Margin Model Independent Validation YN26  
**Generated:** 2026-07-13  
**Overall validation rating:** **Conditionally Satisfactory**

## Approval recommendation

**Conditional approval only. Production use should require closure of High findings or formally approved compensating controls, completion of production-data testing, and satisfactory implementation evidence.**

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

| ID | Severity | Finding | Owner | Remediation deadline | Status |
| --- | --- | --- | --- | --- | --- |
| F-001 | High | Empirical calibration of non-VaR margin components is incomplete | Model Development | 2026-09-11 | Open |
| F-002 | Medium | Production representativeness is limited by public data and synthetic portfolios | Model Development and Data Engineering | 2026-10-11 | Open |
| F-003 | Medium | Production implementation and operational-control evidence is not complete | Technology and Model Operations | 2026-10-11 | Open |

The complete findings tracker, including recommendations, validation status, and closure evidence, is maintained in `reports/evidence/findings_tracker.csv`.

## Validation evidence summary

- Automated test status: **Passed**; passed: **Not reported**; failed: **0**; evidence: `reports/evidence/pytest_step20.txt`.
- Backtesting: **30** members, **7500** assessed observations, **0** exceptions, and an observed exception rate of **0.00%**.
- Traffic-light distribution: **30 Green**, **0 Yellow**, and **0 Red** members.
- Kupiec pass rate: **0.00%**. Christoffersen independence pass rate: **0.00%**.
- Sensitivity: **20** scenarios with mean-margin changes from **-18.94%** to **38.68%** relative to the selected baseline.
- Stress testing: **20** scenarios; worst identified scenario **HIST_2008_GFC**; maximum shortfall **358,333,835.54**.
- Margin shortfalls: **0** positive shortfalls; maximum **0.00**.
- Procyclicality: maximum daily increase **Not available**; maximum weekly increase **Not available**; jumps above 10%, 20%, and 30% were **0**, **0**, and **0**.

## Required remediation deadlines

Critical findings, if any, must be closed before any use. High findings should be remediated within approximately 60 days unless the committee approves a shorter deadline or documented compensating controls. Medium findings should be remediated within approximately 90 days. Low findings and observations should be tracked through normal governance and completed within approximately 120 days or the approved monitoring cycle.

Closure requires objective evidence, not only management attestation. Expected evidence includes approved methodology, empirical calibration analysis, governed configurations, code changes, regression tests, production or production-like backtesting, reconciliations, operating procedures, approval records, and independent-validation confirmation.

## Conditions for approval

Any approval should be limited to the documented scope and conditioned on closure or formal acceptance of material findings; satisfactory production-like testing; completed operational-control review; use of non-overlapping observations for formal multi-day independence tests; approved stress and monitoring thresholds; and mandatory revalidation after material changes to data, model methodology, parameters, portfolio population, or technology.

## Committee decision requested

The committee should select one of the following documented outcomes: reject; return for remediation; approve for controlled non-production use; conditionally approve with explicit restrictions and deadlines; or approve for production after all preconditions are satisfied. Based on current evidence, the recommended decision is the approval recommendation stated above.
