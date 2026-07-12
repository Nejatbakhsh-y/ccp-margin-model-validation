# Ongoing Monitoring Evidence

This directory contains controlled evidence supporting ongoing model
monitoring, threshold assessments, breach investigations, escalation, and
revalidation decisions.

## Required Files

- `monitoring_register.csv`: Central register of approved monitoring metrics.
- `monitoring_breach_register.csv`: Central register of threshold breaches.
- `MON-YYYY-NNN.md`: Completed monitoring-requirement record.
- `BRH-YYYY-NNN.md`: Completed monitoring-breach investigation.
- `MON-YYYY-NNN/`: Supporting calculation and reporting evidence.
- `BRH-YYYY-NNN/`: Supporting breach-investigation evidence.

## Monitoring Identifier

Monitoring requirements must use:

`MON-YYYY-NNN`

Example:

`MON-2026-001`

## Breach Identifier

Monitoring breaches must use:

`BRH-YYYY-NNN`

Example:

`BRH-2026-001`

## Evidence Preservation

Monitoring results, failed calculations, threshold breaches, investigations,
management responses, corrective actions, reruns, validator reviews, and final
dispositions must remain version-controlled.

Original unfavorable results must not be overwritten by corrected or favorable
reruns.

## Escalation

Warning and escalation threshold breaches must be recorded and investigated.

Material breaches must be assessed for:

- Formal finding issuance.
- Model-use restrictions.
- Compensating controls.
- Change assessment.
- Partial or full revalidation.

## Independence

The model owner may perform routine monitoring but cannot independently remove
a breach, change an approved threshold, close a material breach, or determine
that revalidation is unnecessary.

## Relationship to the Monitoring Plan

Detailed operational procedures, assigned owners, reporting frequencies, and
metric-specific thresholds should also be maintained in:

`docs/performance_monitoring_plan.md`
