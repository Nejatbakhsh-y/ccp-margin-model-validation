# Change and Revalidation Evidence

This directory contains controlled records for material model changes,
change-impact assessments, revalidation decisions, testing, and final
validation conclusions.

## Required Files

- `change_revalidation_register.csv`: Central register of change and
  revalidation assessments.
- `CHG-YYYY-NNN.md`: Completed assessment record for each documented change.
- `CHG-YYYY-NNN/`: Supporting evidence directory, when needed.

## Change Identifier

Each change must use the following format:

`CHG-YYYY-NNN`

Example:

`CHG-2026-001`

The corresponding assessment file should be named:

`CHG-2026-001.md`

Supporting evidence should be stored under:

`CHG-2026-001/`

## Required Evidence

Depending on the change and validator-determined scope, evidence may include:

- Change request.
- Change-impact assessment.
- Revised methodology.
- Revised source code.
- Configuration comparison.
- Data-source assessment.
- Data reconciliation.
- Independent recalculation.
- Backtesting results.
- Statistical-test results.
- Benchmark comparisons.
- Sensitivity and stress testing.
- Margin-shortfall analysis.
- Procyclicality analysis.
- Implementation testing.
- Model-use restrictions.
- Temporary controls.
- Validator conclusion.
- Validation-authority approval.

## Independence Requirement

The model owner may propose a materiality classification or revalidation scope,
but the independent validator determines the final scope and required depth of
review.

## Evidence Preservation

Original assessments, failed tests, prior results, revised files, rerun
results, decisions, restrictions, and approvals must remain version-controlled.

Prior evidence must not be overwritten or deleted.

## Production Restriction

A material change must not enter unrestricted production use until the required
independent validation is complete, unless a documented and authorized
temporary exception has been approved.
