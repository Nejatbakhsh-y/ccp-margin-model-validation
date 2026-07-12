# Validation Findings Evidence

This directory contains the controlled finding register and evidence associated
with formal independent-validation findings.

## Required Files

- `finding_register.csv`: Central register of all formal findings.
- `FIND-YYYY-NNN.md`: Complete record for each formal finding.
- `FIND-YYYY-NNN/`: Supporting evidence directory for the finding, when needed.

## Required Naming Convention

Each formal finding must use the format:

`FIND-YYYY-NNN`

Example:

`FIND-2026-001`

A finding file should be named:

`FIND-2026-001.md`

Supporting evidence should be stored under:

`FIND-2026-001/`

## Evidence Preservation

Finding records, original failed tests, management responses, remediation
submissions, rerun results, validator assessments, and closure evidence must
remain version-controlled.

Existing evidence must not be overwritten or deleted. Revised evidence must be
saved as a new version with a clear execution date or version identifier.

## Closure Authority

Only the independent validator may confirm validation closure.

Management risk acceptance does not automatically close a validation finding.
