# Independent Validation Charter

## 1. Purpose

This charter establishes the authority, scope, responsibilities, independence
controls, evidence requirements, finding classifications, approval criteria,
and revalidation requirements for independent validation of the CCP margin
model.

The objective of independent validation is to determine whether the model is:

- Conceptually sound.
- Implemented correctly.
- Supported by suitable and sufficiently reliable data.
- Performing within documented expectations.
- Appropriate for its intended use.
- Subject to clearly documented limitations and compensating controls.
- Supported by reproducible and independently generated evidence.

Validation must not be performed merely to confirm the model owner's
calculations, conclusions, or preferred approval outcome.

---

## 2. Governance Roles

### 2.1 Model Owner

The model owner is responsible for the primary model design, development,
implementation, maintenance, and documentation.

Responsibilities include:

- Defining the model's intended use.
- Defining the products, portfolios, markets, and risks covered by the model.
- Documenting model methodology, assumptions, parameters, and limitations.
- Implementing and maintaining the primary model.
- Maintaining primary-model configuration files.
- Performing model-development testing.
- Producing model outputs.
- Maintaining model-development documentation.
- Documenting known limitations and compensating controls.
- Responding to independent-validation questions and findings.
- Implementing approved remediation.
- Reporting material model changes to the validation authority.

Primary model-development code must remain under:

```text
src/ccp_margin/models/
```

The model owner may provide factual clarification and supporting evidence but
may not direct, suppress, rewrite, or remove independent-validation conclusions.

The model owner may not approve their own model or close validation findings
without independent-validator review.

### 2.2 Independent Validator

The independent validator is responsible for conducting an objective assessment
of the margin model and issuing conclusions independently from the model owner.

The validator must not rely solely on the primary model's calculations,
development tests, documentation, or conclusions.

The independent validator may request clarification, documentation, data,
configuration files, model outputs, and test evidence from the model owner.
However, the validator retains responsibility for validation methods, test
designs, findings, severity classifications, closure decisions, and approval
recommendations.

#### Independent Validator Responsibilities

The independent validator is responsible for:

- Reviewing the conceptual soundness of the model.
- Challenging methodology, assumptions, parameters, and model choices.
- Challenging confidence levels and margin periods of risk.
- Challenging volatility, liquidity, concentration, and gap-risk treatments.
- Reviewing portfolio-aggregation methodology.
- Independently reproducing core model calculations.
- Assessing data completeness, accuracy, consistency, timeliness, and lineage.
- Testing data transformations and risk-factor construction.
- Testing implementation accuracy against documented specifications.
- Reconciling independent results with primary-model outputs.
- Investigating and documenting unexplained differences.
- Conducting backtesting and exception analysis.
- Performing benchmark-model and challenger-model comparisons.
- Conducting parameter-sensitivity and stability testing.
- Evaluating normal-period and stressed-period performance.
- Conducting extreme-but-plausible stress testing.
- Evaluating margin shortfall.
- Evaluating portfolio concentration.
- Assessing procyclicality.
- Evaluating excluded risks and known model limitations.
- Evaluating whether compensating controls are adequate.
- Identifying, documenting, classifying, and tracking findings.
- Preserving failed tests, exceptions, negative results, and unfavorable
  comparisons.
- Reviewing remediation evidence.
- Determining whether findings may be closed.
- Recommending approval, conditional approval, remediation, or rejection.

#### Independent Validation Conclusions

The independent validator must reach conclusions based on documented and
reproducible evidence.

The validator must not alter validation conclusions merely because the model
owner disagrees with them.

The model owner may respond to findings and provide additional evidence, but
the model owner may not:

- Suppress a validation result.
- Remove an unfavorable test.
- Rewrite the validator's conclusion.
- Downgrade finding severity without validator agreement.
- Change validation thresholds after observing results merely to create a
  passing outcome.
- Require the validator to use the primary model's internal implementation as
  the independent benchmark.

#### Validation Code Separation

All independent-validation code must remain under:

```text
src/ccp_margin/validation/
```

Primary model-development code must remain under:

```text
src/ccp_margin/models/
```

The independent-validation package must not import private functions, internal
helpers, or undocumented implementation details from the primary model for the
purpose of reproducing the same result.

Public model interfaces, documented input schemas, approved configuration
files, saved model outputs, and documented data products may be used as
validation inputs.

At minimum, the following calculations must be independently implemented within
the validation package:

- Historical-simulation Value-at-Risk.
- Parametric Value-at-Risk benchmarks.
- Multi-day margin-period-of-risk scaling.
- Portfolio profit-and-loss calculations used for validation.
- Backtesting exception identification.
- Exception-rate calculations.
- Kupiec unconditional-coverage testing.
- Christoffersen independence testing.
- Christoffersen conditional-coverage testing.
- Basel traffic-light classification.
- Benchmark and challenger comparisons.
- Sensitivity calculations.
- Stress-test calculations.
- Margin-shortfall calculations.
- Concentration tests.

The independent implementation does not need to use identical source code,
function structures, algorithms, or numerical libraries. It must use a
documented and conceptually valid methodology capable of providing an
independent comparison.

#### Independent Validation Evidence

The independent validator must preserve:

- Validation datasets.
- Validation configuration files.
- Data manifests and lineage records.
- Independent calculation outputs.
- Reconciliation results.
- Statistical-test outputs.
- Test execution logs.
- Failed tests.
- Negative results.
- Backtesting exceptions.
- Benchmark and challenger results.
- Sensitivity results.
- Stability results.
- Stress-test results.
- Findings and supporting evidence.
- Management responses.
- Remediation evidence.
- Finding-closure assessments.
- Final validation conclusions.
- Final approval recommendations.

Validation evidence must be reproducible from version-controlled code,
documented configurations, identified data versions, and recorded execution
information.

---

## 3. Validation Authority

The independent validator has authority to:

- Request model documentation.
- Request source data and processed data.
- Request data-lineage documentation.
- Request assumptions and parameter rationales.
- Request configuration files.
- Request model-development test evidence.
- Request model outputs.
- Challenge methodology.
- Challenge assumptions.
- Challenge parameter choices.
- Challenge implementation decisions.
- Challenge model limitations.
- Execute independent tests.
- Develop independent benchmark implementations.
- Require investigation of unexplained differences.
- Raise formal validation findings.
- Assign finding severity.
- Recommend remediation.
- Recommend compensating controls.
- Define conditions for temporary or restricted use.
- Reject model approval when material weaknesses remain unresolved.
- Preserve failed tests and negative results as validation evidence.
- Require revalidation following material model changes.

The model owner may provide factual clarification and additional evidence but
may not suppress, rewrite, remove, or override independent-validation
conclusions.

Material disagreements between the model owner and independent validator must be
documented and escalated to the validation authority.

---

## 4. Validation Scope

The validation scope includes:

### 4.1 Conceptual Soundness

- Intended model use.
- Product and market scope.
- Clearing-member assumptions.
- Position and portfolio assumptions.
- Base currency.
- Confidence level.
- Margin periods of risk.
- Risk-factor selection.
- Historical observation windows.
- Rebalancing assumptions.
- Treatment of missing prices.
- Treatment of corporate actions.
- Treatment of non-trading days.
- Excluded risks.
- Known limitations.

### 4.2 Margin Methodology

- Historical-simulation VaR.
- Parametric VaR.
- One-day margin periods of risk.
- Multi-day margin periods of risk.
- Volatility adjustments.
- Liquidity adjustments.
- Concentration-risk components.
- Gap-risk components.
- Portfolio aggregation.
- Diversification assumptions.
- Floors, caps, buffers, and add-ons.
- Total margin calculation.

### 4.3 Quantitative Validation

- Backtesting exception analysis.
- Kupiec unconditional-coverage testing.
- Christoffersen independence testing.
- Christoffersen conditional-coverage testing.
- Basel traffic-light analysis.
- Benchmark-model comparison.
- Challenger-model comparison.
- Parameter-sensitivity analysis.
- Stability testing.
- Stressed-period analysis.
- Extreme-but-plausible stress scenarios.
- Margin-shortfall analysis.
- Portfolio-concentration testing.
- Procyclicality measurement.

### 4.4 Data and Implementation Validation

- Data-source suitability.
- Data completeness.
- Data accuracy.
- Data consistency.
- Data timeliness.
- Data lineage.
- Missing-value treatment.
- Duplicate-record testing.
- Corporate-action treatment.
- Non-trading-day treatment.
- Risk-factor construction.
- Configuration verification.
- Formula verification.
- Code implementation verification.
- Reconciliation against independent calculations.
- Reproducibility testing.
- Unit-test review.
- Integration-test review.

### 4.5 Governance Validation

- Documentation completeness.
- Model-use controls.
- Change-management controls.
- Model-monitoring requirements.
- Limitation management.
- Compensating controls.
- Finding management.
- Validation independence.
- Approval governance.

Items outside the approved validation scope must be identified explicitly as
scope exclusions or model limitations.

---

## 5. Evidence Standards

Validation conclusions must be supported by sufficient, relevant, reliable, and
reproducible evidence.

Acceptable evidence includes:

- Version-controlled source code.
- Version-controlled configuration files.
- Unit-test results.
- Integration-test results.
- Independent calculation outputs.
- Data manifests.
- Data-lineage records.
- Reconciliation tables.
- Statistical-test outputs.
- Benchmark comparisons.
- Challenger comparisons.
- Sensitivity-analysis results.
- Stability-analysis results.
- Stress-test results.
- Margin-shortfall results.
- Procyclicality results.
- Charts and tables generated from reproducible scripts.
- Documented reviewer judgments.
- Preserved logs of failed tests.
- Preserved negative results.
- Finding records.
- Remediation evidence.

Each material validation result must identify, where applicable:

- Model name and version.
- Code version or Git commit.
- Data source.
- Data version or extraction date.
- Configuration used.
- Execution date.
- Test identifier.
- Test owner.
- Test objective.
- Expected result.
- Actual result.
- Applicable tolerance or threshold.
- Pass, fail, warning, or not-applicable status.
- Location of supporting evidence.

Screenshots alone are not sufficient evidence when a reproducible,
machine-readable result can reasonably be produced.

Manual judgment must be documented with the rationale, reviewer identity,
review date, and supporting evidence.

---

## 6. Finding Severity Definitions

### 6.1 Critical

A critical finding indicates that the model is materially unreliable, invalid,
or unsafe for its intended use.

Examples include:

- Materially incorrect margin calculations.
- Serious implementation defects.
- Severe or systematic under-margining.
- Invalid core methodology.
- Missing or unreliable critical data.
- Material calculation non-reproducibility.
- Evidence manipulation.
- Suppression of failed tests.
- Compromise of validation independence.
- Use of the model outside its intended scope without appropriate controls.

Critical findings prevent approval.

### 6.2 High

A high finding indicates a significant weakness that could materially affect
model output, risk measurement, margin adequacy, or governance.

Examples include:

- Significant backtesting failure.
- Material benchmark-model underperformance.
- Material unexplained reconciliation differences.
- Unstable output under reasonable parameter changes.
- Inadequate stressed-period performance.
- Significant procyclicality.
- Material margin shortfall.
- Missing controls over important assumptions.
- Material undocumented limitations.
- Significant data-quality weaknesses.

High findings normally prevent approval unless formally accepted compensating
controls, use restrictions, and remediation plans are established.

### 6.3 Moderate

A moderate finding indicates a weakness that does not immediately invalidate
the model but requires remediation.

Examples include:

- Incomplete documentation.
- Limited sensitivity evidence.
- Non-material reconciliation differences.
- Weak monitoring thresholds.
- Non-material implementation inconsistencies.
- Incomplete data-lineage documentation.
- Inadequate evidence packaging.
- Weaknesses in change-management controls.

Moderate findings may permit conditional approval when owners, deadlines, and
interim controls are documented.

### 6.4 Low

A low finding indicates a minor weakness with limited impact.

Examples include:

- Minor documentation inconsistencies.
- Naming or formatting defects.
- Non-material code-quality issues.
- Minor evidence-packaging deficiencies.
- Minor test-coverage gaps with limited model impact.

Low findings do not normally prevent approval.

### 6.5 Observation

An observation identifies an improvement opportunity that is not considered a
formal deficiency.

Observations do not prevent approval but must remain documented.

---

## 7. Approval Criteria

The independent validator may recommend one of the following outcomes:

- Approved.
- Conditionally approved.
- Not approved.

### 7.1 Approved

Approval requires:

- No unresolved critical findings.
- No unresolved high findings without formally accepted compensating controls.
- Core calculations independently reproduced within documented tolerances.
- Material reconciliation differences resolved.
- Required backtesting completed.
- Required statistical tests completed.
- Required benchmark and challenger analysis completed.
- Required sensitivity and stress testing completed.
- Material data-quality issues resolved.
- Material implementation issues resolved.
- Model limitations documented.
- Compensating controls documented.
- Monitoring requirements defined.
- Model-use restrictions documented where applicable.
- Validation evidence preserved and reproducible.

### 7.2 Conditionally Approved

Conditional approval may be recommended when:

- No unresolved critical finding exists.
- Remaining weaknesses are understood.
- Remaining risks are controlled.
- Compensating controls are documented.
- Use restrictions are documented where necessary.
- Remediation actions are defined.
- Remediation owners are assigned.
- Target completion dates are established.
- Follow-up validation requirements are documented.

Conditional approval must identify:

- The conditions of approval.
- Applicable use restrictions.
- Required remediation.
- Required monitoring.
- Escalation thresholds.
- The conditional-approval expiration or review date.

### 7.3 Not Approved

The model must not be approved when:

- A critical finding remains unresolved.
- Core calculations cannot be independently reproduced.
- Material reconciliation differences remain unexplained.
- Material under-margining remains unexplained.
- Required backtesting is incomplete or materially deficient.
- Required statistical tests are missing.
- Data are unsuitable for the intended use.
- Material implementation defects remain unresolved.
- Validation independence has been compromised.
- Required evidence is missing or unreliable.
- The model is outside its approved intended use.
- The model exceeds approved risk appetite.
- Compensating controls are inadequate.

## 8. Prohibition on Validation-Driven Tuning

The model must not be tuned merely to pass validation tests.

Model development, calibration, and modification decisions must be based on
sound conceptual, empirical, operational, and risk-management considerations.
Validation results must not be used to reverse-engineer a passing outcome.

Any model change made after reviewing validation results must have:

- A documented conceptual rationale.
- A documented empirical rationale.
- A clear description of the identified deficiency or limitation.
- Approval through the applicable model-change governance process.
- Separate model-development evidence.
- Separate independent-validation evidence.
- An assessment of model-selection and overfitting risk.
- An assessment across normal market periods.
- An assessment across stressed market periods.
- An assessment across relevant products and portfolios.
- An assessment of the effect on margin adequacy.
- An assessment of the effect on procyclicality.
- An assessment of the effect on model stability.
- Re-execution of all materially affected validation tests.
- Preservation of the original model results and validation evidence.
- Documentation of the model version, configuration, data period, and code
  version associated with the change.

The following practices are prohibited:

- Changing model parameters solely because a validation test failed.
- Repeatedly adjusting parameters until a statistical test produces a passing
  result.
- Selecting a favorable calibration period after reviewing validation results.
- Selecting a favorable backtesting period after reviewing validation results.
- Excluding unfavorable portfolios without documented conceptual
  justification.
- Excluding unfavorable clearing members without documented justification.
- Removing unfavorable stress scenarios.
- Reducing stress severity solely to obtain favorable results.
- Changing validation thresholds after observing the results solely to obtain
  a passing classification.
- Changing exception definitions solely to improve backtesting performance.
- Changing data-cleaning rules solely to eliminate unfavorable observations.
- Reporting only the most favorable model specification.
- Reporting only favorable benchmark comparisons.
- Suppressing unfavorable sensitivity or stability results.
- Replacing failed results without preserving the original evidence.
- Allowing the model owner to select validation methods solely to improve the
  likelihood of approval.
- Allowing the model owner to alter independent-validation conclusions.

When model changes are proposed following a failed or unfavorable validation
result, the model owner must document:

- The original model specification.
- The original validation result.
- The reason the result was considered deficient.
- The proposed model change.
- The conceptual basis for the change.
- The empirical evidence supporting the change.
- Alternative changes considered.
- The expected effect of the change.
- The potential unintended consequences.
- The approval authority for the change.
- The model version in which the change was implemented.

The independent validator must determine whether the proposed change:

- Addresses the underlying model weakness.
- Is conceptually justified.
- Is supported by sufficient empirical evidence.
- Creates new model risk.
- Increases overfitting or model-selection risk.
- Remains appropriate across normal and stressed conditions.
- Remains appropriate across the intended product and portfolio universe.
- Requires partial or full revalidation.

Parameter changes must be treated as formal model changes when they materially
affect model output, risk sensitivity, margin adequacy, backtesting,
procyclicality, stability, or intended use.

A successful result obtained after model modification does not invalidate or
replace the original failed result. Both the original result and the revised
result must remain preserved in the validation evidence.

Material validation-driven tuning, manipulation of validation evidence, or
suppression of unfavorable results may result in:

- A formal validation finding.
- Escalation to the validation authority.
- A requirement for additional independent review.
- Partial or full revalidation.
- Conditional approval.
- Withdrawal of conditional approval.
- A not-approved validation conclusion.

---

## 9. Preservation of Failed Tests and Negative Results

All failed tests, unexpected outcomes, exceptions, unfavorable benchmark
comparisons, and negative results must be preserved.

They must not be:

- Deleted.
- Hidden.
- Suppressed.
- Reclassified without explanation.
- Replaced by only favorable reruns.
- Excluded from the validation report without documented justification.
- Removed from version-controlled evidence.
- Overwritten without retaining the original result.

When a failed test is corrected and rerun, the evidence record must preserve:

- The original failed result.
- The cause of the failure.
- The corrective action.
- The revised code or configuration version.
- The rerun result.
- The validator's assessment of whether the issue is resolved.

A successful rerun does not erase the original failure.

---

## 10. Independence Control


Independent validation must remain organizationally, procedurally, and technically separate from primary model development throughout the model lifecycle.

The following independence controls apply:

* Primary model code must remain under `src/ccp_margin/models/`.
* Independent-validation code must remain under `src/ccp_margin/validation/`.
* Core validation calculations, including VaR reproduction, backtesting exceptions, statistical tests, benchmark comparisons, and reconciliation calculations, must be independently implemented.
* Validation code must not import private functions, internal implementation utilities, or intermediate results from the primary model merely to reproduce the primary model output.
* Shared public data schemas, approved configuration values, and documented interfaces may be used where necessary, provided they do not compromise independent calculation.
* Validation methodology, test design, materiality thresholds, benchmark selection, challenger selection, sampling decisions, and conclusions must be determined by the independent validator.
* Differences between primary-model and independent-validation results must be investigated, reconciled where possible, and documented.
* The model owner cannot approve their own model.
* The model owner cannot assign or reduce validation-finding severity.
* The model owner cannot close a validation finding without independent-validator review and documented closure approval.
* Failed tests, exceptions, unexpected outcomes, and negative results cannot be deleted, suppressed, overwritten, or removed by the model owner.
* Material model, data, methodology, parameter, configuration, or implementation changes require validation reassessment.
* Validation conclusions must remain traceable to independently generated code, calculations, tests, evidence, and professional judgment.
* Material disagreements between the model owner and independent validator must be documented and escalated to the designated validation authority.
* Validation personnel must disclose any actual, potential, or perceived conflict of interest that could impair independence.
* Validation evidence must remain under version control and must clearly identify the validator, execution date, code version, configuration version, data version, results, and conclusions.

Development assistance may be provided to the independent validator for administrative, environment-configuration, infrastructure, data-access, or technical-support purposes. Such assistance must be documented when material and must not determine or influence:

* Validation methodology.
* Test selection.
* Test implementation.
* Finding classification.
* Finding severity.
* Interpretation of results.
* Remediation acceptance.
* Approval recommendations.
* Final validation conclusions.

Any situation that could compromise validation independence must be disclosed, documented, assessed, and escalated before the affected validation conclusion is issued.

---

## 11. Finding Management



Every formal validation finding must be recorded, tracked, reviewed, and retained from initial identification through final disposition.

Each finding record must contain:

* Unique finding identifier.
* Finding title.
* Severity.
* Affected model component.
* Date identified.
* Description of the issue.
* Supporting evidence.
* Root cause, when known.
* Potential impact.
* Required remediation.
* Recommended compensating controls.
* Responsible owner.
* Target completion date.
* Current status.
* Management response.
* Validator review notes.
* Validator closure assessment.
* Closure date, when applicable.

Finding identifiers must use the following format:

`FIND-YYYY-NNN`

where:

* `YYYY` is the year in which the finding was identified.
* `NNN` is a sequential three-digit number.

Examples include:

* `FIND-2026-001`
* `FIND-2026-002`
* `FIND-2026-003`

Permitted severity classifications are:

* Critical.
* High.
* Moderate.
* Low.
* Observation.

Permitted finding statuses are:

* Open.
* Remediation in progress.
* Pending validation review.
* Risk accepted.
* Closed.
* Overdue.

Finding statuses must be applied as follows:

* **Open** means that the finding has been issued and remediation has not been completed.
* **Remediation in progress** means that the responsible owner is actively implementing corrective action.
* **Pending validation review** means that management has submitted remediation evidence for independent-validator assessment.
* **Risk accepted** means that authorized management has formally accepted the residual risk instead of completing full remediation. Risk acceptance does not constitute validation closure.
* **Closed** means that the independent validator has confirmed that all closure requirements have been satisfied.
* **Overdue** means that the target completion date has passed and the finding has not been closed.

A finding may be closed only after the independent validator confirms that:

* Required remediation is complete.
* Supporting evidence is sufficient.
* Relevant tests have been rerun.
* Original failed results remain preserved.
* Rerun results are documented.
* The identified issue has been resolved.
* No material residual risk remains unaddressed.
* Any required compensating controls have been implemented.
* The closure conclusion is supported by independently reviewed evidence.

The model owner or remediation owner may request closure but cannot independently close a validation finding.

Management acceptance of risk does not automatically constitute validation closure. A risk-accepted finding must remain separately identifiable, supported by documented approval, and subject to monitoring, escalation, reassessment, or expiration requirements established by the validation authority.

Any change to a finding's severity, status, target date, remediation requirement, or disposition must be documented with:

* Date of the change.
* Previous value.
* Revised value.
* Reason for the change.
* Person requesting the change.
* Independent-validator review.
* Approval authority, when applicable.

Finding evidence must remain version-controlled and traceable. Previous finding records, management responses, failed tests, remediation submissions, and validator assessments must not be overwritten or deleted.

Closed findings must remain in the permanent validation record.

---

## 12. Change and Revalidation Triggers

Partial or full revalidation is required when a material change, deterioration,
defect, control failure, or change in model use could affect the model's
conceptual soundness, implementation integrity, performance, limitations, or
risk profile.

Revalidation triggers include:

- Methodology changes.
- Parameter changes.
- Confidence-level changes.
- Margin-period-of-risk changes.
- New products.
- New markets.
- New asset classes.
- Changes to portfolio aggregation.
- Changes to volatility adjustments.
- Changes to liquidity adjustments.
- Changes to concentration methodology.
- Changes to gap-risk methodology.
- Material data-source changes.
- Material data-processing changes.
- Material code changes.
- Material configuration changes.
- Significant backtesting deterioration.
- Significant benchmark deterioration.
- Significant margin shortfall.
- Significant procyclicality.
- New regulatory expectations.
- Changes to intended model use.
- Identification of a material implementation defect.
- Significant changes in portfolio composition.
- Significant changes in market behavior.
- Failure of a compensating control.
- Expiration of conditional approval.

Additional revalidation triggers include:

- Changes to model assumptions or limitations.
- Changes to valuation or pricing methods.
- Changes to risk-factor mappings.
- Changes to data-quality controls.
- Changes to missing-data treatment.
- Changes to corporate-action treatment.
- Changes to holiday or non-trading-day treatment.
- Changes to portfolio netting or offset rules.
- Changes to stressed-period selection.
- Changes to model calibration windows.
- Changes to model thresholds or materiality limits.
- Changes to model dependencies or software libraries that could affect results.
- Migration to a new platform, operating environment, database, or execution
  infrastructure.
- Changes to production interfaces, scheduling, orchestration, or downstream
  consumption.
- Repeated operational incidents or unexplained calculation differences.
- Discovery that validation evidence is incomplete, inaccurate, or not
  reproducible.
- Failure to complete required remediation by an approved deadline.
- Material findings issued by internal audit, external audit, regulators, or
  other independent reviewers.
- Changes that invalidate previously approved compensating controls.
- Model performance outside approved monitoring thresholds.
- Model use outside the previously validated scope.

Every proposed or completed material change must be documented through a
change-impact assessment.

The change-impact assessment must contain:

- Unique change identifier.
- Change title.
- Date identified or proposed.
- Requesting party.
- Responsible implementation owner.
- Description of the change.
- Business or risk rationale.
- Affected model components.
- Affected data, code, configuration, assumptions, and documentation.
- Expected impact on margin calculations.
- Expected impact on model risk.
- Applicable revalidation triggers.
- Materiality assessment.
- Proposed revalidation scope.
- Required testing.
- Required evidence.
- Implementation date.
- Independent-validator review.
- Validation decision.
- Required conditions or restrictions.
- Final approval or escalation record.

Change identifiers must use the following format:

`CHG-YYYY-NNN`

where:

- `YYYY` is the year in which the change was identified.
- `NNN` is a sequential three-digit number.

Examples include:

- `CHG-2026-001`
- `CHG-2026-002`
- `CHG-2026-003`

The independent validator must classify the required response as one of the
following:

- No additional validation required.
- Targeted validation review.
- Partial revalidation.
- Full revalidation.
- Immediate model-use restriction or suspension pending review.

A targeted validation review may be appropriate when the change is limited,
well understood, and does not materially alter the model methodology, risk
profile, or approved use.

Partial revalidation may include selected activities such as:

- Independent recalculation.
- Code review.
- Data reconciliation.
- Configuration review.
- Backtesting.
- Benchmark comparison.
- Sensitivity testing.
- Stress testing.
- Margin-shortfall analysis.
- Procyclicality analysis.
- Implementation testing.
- Documentation review.
- Review of compensating controls.

Full revalidation may be required when:

- Core model methodology changes.
- The model's approved purpose or scope changes materially.
- A new material asset class, market, or product is introduced.
- A material implementation defect affects historical or current results.
- Performance deterioration is significant or persistent.
- Multiple related changes collectively alter the model risk profile.
- Prior validation conclusions are no longer reliable.
- Conditional approval expires without satisfactory remediation.
- Regulatory or validation authority requirements mandate full revalidation.

The independent validator determines the required depth and scope of
revalidation based on:

- Nature of the change.
- Magnitude of the change.
- Components affected.
- Model-risk significance.
- Portfolio and financial impact.
- Implementation complexity.
- Performance implications.
- Data implications.
- Regulatory implications.
- Operational dependencies.
- Existing findings.
- Effectiveness of compensating controls.
- Reliability of available evidence.
- Cumulative impact of related changes.

The model owner may propose a revalidation scope but cannot make the final
revalidation determination.

A material change must not be placed into unrestricted production use before
the required independent review is completed, unless an authorized exception
is documented with:

- Business justification.
- Risk assessment.
- Temporary controls.
- Model-use restrictions.
- Approval authority.
- Expiration date.
- Required follow-up validation.

All revalidation decisions, testing, evidence, conclusions, conditions, and
approvals must remain version-controlled and traceable.

Completion of implementation testing does not by itself constitute completion
of independent revalidation.

---

## 13. Ongoing Monitoring Expectations

The validation conclusion must define ongoing monitoring requirements,
including, where applicable:

- Daily or periodic backtesting.
- Exception-rate monitoring.
- Traffic-light classification.
- Margin-shortfall monitoring.
- Benchmark-model comparison.
- Sensitivity monitoring.
- Stability monitoring.
- Procyclicality monitoring.
- Concentration monitoring.
- Data-quality monitoring.
- Configuration-change monitoring.
- Model-performance thresholds.
- Escalation thresholds.
- Required management reporting.
- Revalidation triggers.

Monitoring results that breach approved thresholds must be documented,
investigated, and escalated.

---

## 14. Charter Enforcement

This charter applies throughout:

- Model design.
- Model development.
- Model testing.
- Independent validation.
- Finding remediation.
- Model approval.
- Model implementation.
- Ongoing monitoring.
- Model change.
- Revalidation.
- Model retirement.

Deviations from this charter must be:

- Documented.
- Justified.
- Risk assessed.
- Approved by the validation authority.
- Retained as part of the model-governance evidence.

Unapproved deviations may result in a formal validation finding and may prevent
model approval.
