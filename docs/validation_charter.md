# Independent Validation Charter

## 1. Purpose

This charter establishes the authority, scope, standards, independence controls, evidence requirements, finding classifications, and approval criteria for independent validation of the CCP margin model.

The objective of independent validation is to determine whether the model is:

- Conceptually sound.
- Implemented correctly.
- Supported by suitable and sufficiently reliable data.
- Performing within documented expectations.
- Appropriate for its intended use.
- Subject to clearly documented limitations and compensating controls.

Validation must not be performed merely to confirm the model owner's conclusions.

## 2. Governance Roles

### 2.1 Model Owner

The model owner is responsible for the primary model implementation.

Responsibilities include:

- Defining the intended model use.
- Documenting model methodology and assumptions.
- Implementing the primary model.
- Maintaining primary-model configuration files.
- Performing model-development testing.
- Producing model outputs.
- Documenting known limitations.
- Responding to independent-validation findings.
- Implementing approved remediation.

Primary model-development code must remain under:

`src/ccp_margin/models/`

### 2.2 Independent Validator

The independent validator is responsible for independently assessing the model without relying solely on the model owner's calculations or conclusions.

Responsibilities include:

- Reviewing conceptual soundness.
- Independently reproducing core calculations.
- Assessing data quality and data lineage.
- Conducting implementation verification.
- Performing backtesting and benchmarking.
- Performing sensitivity and stability analysis.
- Evaluating stressed-period performance.
- Assessing procyclicality and margin shortfall.
- Recording findings and negative results.
- Recommending approval, conditional approval, or rejection.

Independent-validation code must remain under:

`src/ccp_margin/validation/`

The validation package must not import private internal functions from the primary model merely to reproduce the same result.

At minimum, the following calculations must be independently reimplemented:

- Value-at-Risk calculations.
- Backtesting exception calculations.
- Exception-rate calculations.
- Kupiec unconditional-coverage test.
- Christoffersen independence test.
- Christoffersen conditional-coverage test.
- Basel traffic-light classification.

## 3. Validation Authority

The independent validator has authority to:

- Request model documentation, data, assumptions, configuration files, and test evidence.
- Challenge methodology, implementation, assumptions, parameters, and limitations.
- Execute independent tests.
- Require investigation of unexplained differences.
- Raise formal validation findings.
- Recommend remediation or compensating controls.
- Reject model approval when material weaknesses remain unresolved.
- Preserve failed tests and negative results as validation evidence.

The model owner may provide factual clarification but may not suppress, rewrite, or remove independent-validation conclusions.

## 4. Validation Scope

The validation scope includes:

- Historical-simulation VaR.
- Parametric VaR.
- One-day and multi-day margin periods of risk.
- Volatility adjustments.
- Liquidity adjustments.
- Concentration-risk components.
- Gap-risk components.
- Portfolio aggregation.
- Benchmark and challenger models.
- Backtesting exception analysis.
- Kupiec coverage testing.
- Christoffersen independence and conditional-coverage testing.
- Basel traffic-light analysis.
- Parameter sensitivity.
- Stability testing.
- Stressed-period analysis.
- Extreme but plausible stress scenarios.
- Margin shortfall analysis.
- Portfolio concentration testing.
- Procyclicality measurement.
- Data-quality verification.
- Configuration verification.
- Implementation verification.
- Documentation and governance review.
- Model limitations and compensating controls.

Items outside the approved scope must be identified explicitly as exclusions or limitations.

## 5. Evidence Standards

Validation conclusions must be supported by reproducible evidence.

Acceptable evidence includes:

- Version-controlled source code.
- Version-controlled configuration files.
- Unit-test and integration-test results.
- Independent calculation outputs.
- Data manifests and lineage records.
- Reconciliation tables.
- Statistical-test outputs.
- Benchmark comparisons.
- Sensitivity-analysis results.
- Stress-test results.
- Charts and tables generated from reproducible scripts.
- Documented reviewer judgments.
- Preserved logs of failed tests and negative results.

Evidence must identify:

- The code version.
- Data version or data extraction date.
- Configuration used.
- Execution date.
- Test owner.
- Expected result.
- Actual result.
- Pass, fail, warning, or not-applicable status.

Screenshots alone are not sufficient evidence when a reproducible machine-readable result can be produced.

## 6. Finding Severity Definitions

### 6.1 Critical

A critical finding indicates that the model is materially unreliable or unsafe for its intended use.

Examples include:

- Materially incorrect margin calculations.
- Serious implementation defects.
- Severe under-margining.
- Invalid core methodology.
- Missing or unreliable critical data.
- Evidence of result manipulation.
- Failure of independence controls.

Critical findings prevent approval.

### 6.2 High

A high finding indicates a significant weakness that could materially affect model output, risk measurement, or governance.

Examples include:

- Significant backtesting failure.
- Material benchmark-model underperformance.
- Unstable output under reasonable parameter changes.
- Inadequate stressed-period performance.
- Missing controls over important assumptions.
- Material undocumented limitations.

High findings normally prevent approval unless a formally approved compensating control and remediation plan exist.

### 6.3 Moderate

A moderate finding indicates a weakness that does not immediately invalidate the model but requires remediation.

Examples include:

- Incomplete documentation.
- Limited sensitivity evidence.
- Minor reconciliation differences.
- Weak monitoring thresholds.
- Non-material implementation inconsistencies.

Moderate findings may permit conditional approval with defined owners and deadlines.

### 6.4 Low

A low finding indicates a minor weakness with limited impact.

Examples include:

- Minor documentation inconsistencies.
- Naming or formatting defects.
- Non-material code-quality issues.
- Minor evidence-packaging deficiencies.

Low findings do not normally prevent approval.

### 6.5 Observation

An observation is an improvement opportunity that is not considered a formal deficiency.

Observations do not prevent approval but must remain documented.

## 7. Approval Criteria

The independent validator may recommend one of the following outcomes:

### Approved

Approval requires:

- No unresolved critical findings.
- No unresolved high findings without formally accepted compensating controls.
- Core calculations independently reproduced within documented tolerances.
- Required backtesting completed.
- Required statistical tests completed.
- Material data-quality issues resolved.
- Model limitations documented.
- Monitoring requirements defined.
- Validation evidence preserved and reproducible.

### Conditionally Approved

Conditional approval may be granted when:

- No unresolved critical finding exists.
- Remaining weaknesses are understood and controlled.
- Compensating controls are documented.
- Remediation owners and due dates are assigned.
- Temporary use restrictions are documented where necessary.

### Not Approved

The model must not be approved when:

- A critical finding remains unresolved.
- Core calculations cannot be independently reproduced.
- Material under-margining is unexplained.
- Data are unsuitable for the intended use.
- Validation independence has been compromised.
- Required evidence is missing or unreliable.
- The model is outside approved risk appetite or intended use.

## 8. Prohibition on Validation-Driven Tuning

The model must not be tuned merely to pass validation tests.

Parameter changes must have:

- A documented conceptual or empirical rationale.
- Approval through model-change governance.
- Separate development and validation evidence.
- Assessment of overfitting risk.
- Assessment across normal and stressed periods.
- Re-execution of all materially affected validation tests.

Validation thresholds must not be changed after results are observed solely to convert a failure into a pass.

## 9. Preservation of Failed Tests and Negative Results

All failed tests, unexpected outcomes, unfavorable benchmark comparisons, and negative results must be preserved.

They must not be:

- Deleted.
- Hidden.
- Reclassified without explanation.
- Replaced by only favorable reruns.
- Excluded from the validation report without documented justification.

When a failed test is corrected and rerun, both the original failure and subsequent result must remain in the evidence record.

## 10. Independence Control

Independent validation must remain organizationally and technically separate from primary model development.

The following controls apply:

- Primary model code remains under `src/ccp_margin/models/`.
- Independent-validation code remains under `src/ccp_margin/validation/`.
- Core validation calculations are independently implemented.
- Validation does not import private primary-model functions to duplicate model results.
- Differences between primary and independent implementations are investigated and documented.
- The model owner cannot approve their own model.
- The model owner cannot close validation findings without validator review.
- Material changes require validation reassessment.
- Validation conclusions must remain traceable to independently generated evidence.

## 11. Finding Management

Every formal finding must contain:

- Unique finding identifier.
- Finding title.
- Severity.
- Affected model component.
- Description of the issue.
- Supporting evidence.
- Potential impact.
- Required remediation.
- Responsible owner.
- Target completion date.
- Current status.
- Validator closure assessment.

A finding is closed only after the validator confirms that remediation is complete and adequately evidenced.

## 12. Change and Revalidation Triggers

Revalidation is required when material changes occur, including:

- Methodology changes.
- Parameter changes.
- New products or markets.
- Changes to margin period of risk.
- Material data-source changes.
- Material code changes.
- Significant backtesting deterioration.
- New regulatory expectations.
- Changes to model use.
- Identification of a material implementation defect.
- Significant changes in portfolio composition or market behavior.

## 13. Charter Enforcement

This charter applies throughout model development, validation, remediation, approval, and monitoring.

Deviations from this charter must be documented, justified, approved by the validation authority, and retained as part of the model-governance evidence.
