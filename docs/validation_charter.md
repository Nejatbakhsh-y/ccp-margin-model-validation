# Independent Validation Charter

## Document Metadata

* **Repository:** `ccp-margin-model-validation`
* **Document:** Independent Validation Charter
* **Repository location:** `docs/validation_charter.md`
* **Charter version:** 1.0
* **Effective date:** July 12, 2026
* **Document status:** Approved for repository implementation
* **Review frequency:** At least annually and upon any material model, data, methodology, configuration, implementation, scope, or governance change
* **Related document:** `docs/scope_and_assumptions.md`

---

## 1. Purpose

This charter establishes the authority, scope, responsibilities, independence
controls, evidence requirements, finding classifications, approval criteria,
monitoring expectations, change controls, and revalidation requirements for
independent validation of the CCP margin model.

The objective of independent validation is to determine whether the model is:

* Conceptually sound.
* Implemented correctly.
* Supported by suitable and sufficiently reliable data.
* Performing within documented expectations.
* Appropriate for its documented intended use.
* Subject to clearly documented limitations and compensating controls.
* Supported by reproducible and independently generated evidence.
* Governed through transparent findings, approval, monitoring, and revalidation
  processes.

Validation must not be performed merely to confirm the model owner's
calculations, conclusions, model choices, or preferred approval outcome.

### 1.1 Research Repository Context

This charter governs a research implementation and independent-validation
framework.

The repository does not represent:

* An actual central counterparty.
* A clearinghouse.
* A financial institution.
* A regulatory approval process.
* A production model-risk management program.
* Authorization for live margin collection.
* Authorization for trading, investment, capital, or regulatory use.

References to model owners, independent validators, approval authorities,
management responses, monitoring owners, governance committees, production
controls, model-use restrictions, or risk acceptance represent documented
research-governance roles and controls unless an actual institutional role is
explicitly identified.

Approval under this charter is limited to the documented research use.

Approval under this charter does not constitute approval for:

* Live clearing.
* Regulatory capital.
* Customer or clearing-member margining.
* Investment decisions.
* Trading decisions.
* Production risk management.
* Regulatory reporting.
* Institutional deployment.
* Any use outside the documented research scope.

Any future operational or production implementation would require separate:

* Institutional governance.
* Legal review.
* Compliance review.
* Technology controls.
* Information-security controls.
* Regulatory assessment.
* Operational-risk assessment.
* Independent model validation.
* Formal production approval.

The authoritative description of the model's intended research use, product
scope, market universe, portfolio assumptions, data period, exclusions, and
limitations must be maintained in:

```text
docs/scope_and_assumptions.md
```

---

## 2. Governance Roles

### 2.1 Model Owner

The model owner is responsible for the primary model design, development,
implementation, maintenance, testing, and documentation.

Responsibilities include:

* Defining the model's intended use.
* Defining the products, portfolios, markets, and risks covered by the model.
* Documenting the methodology.
* Documenting model assumptions.
* Documenting parameter choices.
* Documenting configuration values.
* Documenting model limitations.
* Implementing and maintaining the primary model.
* Maintaining primary-model configuration files.
* Performing model-development testing.
* Producing primary-model outputs.
* Maintaining model-development documentation.
* Documenting known limitations.
* Documenting compensating controls.
* Responding to independent-validation questions.
* Responding to validation findings.
* Implementing approved remediation.
* Reporting material model changes.
* Reporting material data changes.
* Reporting material implementation changes.
* Reporting material configuration changes.
* Reporting changes to the intended model use.
* Supporting reproducibility of the primary model.

Primary model-development code must remain under:

```text
src/ccp_margin/models/
```

The model owner may provide:

* Factual clarification.
* Supporting documentation.
* Source data.
* Processed data.
* Configuration files.
* Model outputs.
* Development-test evidence.
* Remediation evidence.

The model owner may not:

* Direct independent-validation conclusions.
* Suppress an independent-validation result.
* Rewrite the validator's conclusion.
* Remove an unfavorable result.
* Delete failed tests.
* Alter validation evidence.
* Assign validation-finding severity.
* Reduce finding severity without independent-validator agreement.
* Close a validation finding without independent-validator review.
* Approve their own model.
* Determine the final validation conclusion for their own model.
* Require the validator to use the primary model's private implementation as
  the independent benchmark.
* Tune the model merely to obtain a favorable validation outcome.

### 2.2 Independent Validator

The independent validator is responsible for conducting an objective assessment
of the margin model and issuing conclusions independently from the model owner.

The independent validator must not rely solely on:

* Primary-model calculations.
* Model-development tests.
* Model-owner documentation.
* Model-owner conclusions.
* Primary-model private functions.
* Primary-model internal helpers.
* Undocumented intermediate calculations.

The independent validator may request:

* Clarification.
* Methodology documentation.
* Data documentation.
* Source data.
* Processed data.
* Configuration files.
* Model outputs.
* Test evidence.
* Data-lineage records.
* Model-change records.
* Monitoring results.
* Remediation evidence.

The independent validator retains responsibility for:

* Validation methodology.
* Validation test design.
* Benchmark selection.
* Challenger selection.
* Sampling decisions.
* Materiality criteria.
* Reconciliation tolerances.
* Statistical test implementation.
* Finding identification.
* Finding severity.
* Finding-closure decisions.
* Validation conclusions.
* Approval recommendations.
* Revalidation recommendations.

#### Independent Validator Responsibilities

The independent validator is responsible for:

* Reviewing the conceptual soundness of the model.
* Challenging methodology.
* Challenging assumptions.
* Challenging parameter choices.
* Challenging model choices.
* Challenging confidence levels.
* Challenging margin periods of risk.
* Challenging historical observation windows.
* Challenging volatility treatment.
* Challenging liquidity treatment.
* Challenging concentration-risk treatment.
* Challenging gap-risk treatment.
* Reviewing portfolio-aggregation methodology.
* Reviewing diversification assumptions.
* Independently reproducing core model calculations.
* Assessing data completeness.
* Assessing data accuracy.
* Assessing data consistency.
* Assessing data timeliness.
* Assessing data suitability.
* Assessing data lineage.
* Testing data transformations.
* Testing risk-factor construction.
* Testing implementation accuracy against documented specifications.
* Reconciling independent results with primary-model outputs.
* Investigating unexplained differences.
* Documenting reconciliation differences.
* Conducting backtesting.
* Conducting exception analysis.
* Performing benchmark-model comparisons.
* Performing challenger-model comparisons.
* Conducting parameter-sensitivity testing.
* Conducting stability testing.
* Evaluating normal-period performance.
* Evaluating stressed-period performance.
* Conducting extreme-but-plausible stress testing.
* Evaluating margin shortfall.
* Evaluating portfolio concentration.
* Assessing procyclicality.
* Evaluating excluded risks.
* Evaluating known limitations.
* Evaluating compensating controls.
* Identifying validation findings.
* Documenting validation findings.
* Assigning finding severity.
* Tracking findings.
* Preserving failed tests.
* Preserving exceptions.
* Preserving negative results.
* Preserving unfavorable comparisons.
* Reviewing remediation evidence.
* Determining whether findings may be closed.
* Defining ongoing monitoring expectations.
* Determining whether partial or full revalidation is required.
* Recommending approval, conditional approval, non-approval, or a
  validation-incomplete conclusion.

#### Independent Validation Conclusions

The independent validator must reach conclusions based on documented,
sufficient, relevant, reliable, and reproducible evidence.

The validator must not alter validation conclusions merely because the model
owner disagrees with them.

The model owner may respond to findings and provide additional evidence, but
the model owner may not:

* Suppress a validation result.
* Remove an unfavorable test.
* Rewrite the validator's conclusion.
* Downgrade finding severity without validator agreement.
* Change validation thresholds after observing results merely to create a
  passing outcome.
* Require the validator to use the primary model's private implementation as
  the independent benchmark.
* Remove validation scope merely because a test is unfavorable.
* Prevent preservation of original failed results.

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
files, saved model outputs, documented data products, and public utility
interfaces may be used as validation inputs when their use does not compromise
independence.

At minimum, the following calculations must be independently implemented within
the validation package:

* Historical-simulation Value-at-Risk.
* Parametric Value-at-Risk benchmarks.
* Multi-day margin-period-of-risk scaling.
* Portfolio profit-and-loss calculations used for validation.
* Backtesting exception identification.
* Exception-rate calculations.
* Kupiec unconditional-coverage testing.
* Christoffersen independence testing.
* Christoffersen conditional-coverage testing.
* Basel traffic-light classification.
* Benchmark-model comparisons.
* Challenger-model comparisons.
* Sensitivity calculations.
* Stability calculations.
* Stress-test calculations.
* Margin-shortfall calculations.
* Concentration tests.
* Material reconciliation calculations.

The independent implementation does not need to use identical:

* Source code.
* Function structures.
* Algorithms.
* Numerical libraries.
* Data structures.
* Intermediate calculations.

It must use a documented and conceptually valid methodology capable of
providing an independent comparison.

#### Independent Validation Evidence

The independent validator must preserve:

* Validation datasets.
* Validation configuration files.
* Data manifests.
* Data-lineage records.
* Independent calculation outputs.
* Reconciliation results.
* Statistical-test outputs.
* Test execution logs.
* Failed tests.
* Negative results.
* Backtesting exceptions.
* Benchmark-model results.
* Challenger-model results.
* Sensitivity results.
* Stability results.
* Stress-test results.
* Margin-shortfall results.
* Concentration results.
* Procyclicality results.
* Findings.
* Supporting evidence.
* Management or model-owner responses.
* Remediation evidence.
* Finding-closure assessments.
* Monitoring requirements.
* Revalidation decisions.
* Final validation conclusions.
* Final approval recommendations.

Validation evidence must be reproducible from:

* Version-controlled code.
* Documented configurations.
* Identified data versions.
* Recorded execution information.
* Documented environment information.
* Preserved dependency information.

### 2.3 Approval Authority

For this research repository, approval authority is represented through a
documented validation conclusion rather than an actual institutional model-risk
committee, executive-management function, central counterparty approval body,
or regulatory authority.

The approval authority is responsible for determining the final documented
validation status after considering:

* The independent validator's conclusion.
* The independent validator's recommendation.
* The nature and severity of validation findings.
* The sufficiency of validation evidence.
* The reliability of validation evidence.
* The reproducibility of validation evidence.
* The model's documented research use.
* Model limitations.
* Compensating controls.
* Model-use restrictions.
* Required remediation.
* Ongoing monitoring requirements.
* Revalidation requirements.
* Unresolved disagreements.
* Any approved deviations from this charter.

The final validation conclusion must be one of:

* Approved for the documented research use.
* Conditionally approved for the documented research use.
* Not approved.
* Validation incomplete.

The approval authority may reject the model even where individual statistical
tests pass when the totality of evidence indicates material:

* Conceptual weakness.
* Implementation risk.
* Data risk.
* Performance weakness.
* Governance weakness.
* Reproducibility weakness.
* Model-use risk.
* Validation-independence concern.

The model owner may not act as the approval authority for their own model.

The independent validator may recommend a conclusion, but the documented final
approval-authority record must state the final conclusion and supporting
rationale.

For this repository, the documented validation conclusion and its supporting
evidence constitute the approval-authority record.

This arrangement is a research-governance representation and does not
constitute institutional, regulatory, production, or clearinghouse approval.

---

## 3. Independent Validator Authority

The independent validator has authority to:

* Request model documentation.
* Request methodology documentation.
* Request source data.
* Request processed data.
* Request data-lineage documentation.
* Request assumptions.
* Request parameter rationales.
* Request configuration files.
* Request model-development test evidence.
* Request model outputs.
* Request change records.
* Request monitoring records.
* Request remediation evidence.
* Challenge methodology.
* Challenge assumptions.
* Challenge parameter choices.
* Challenge implementation decisions.
* Challenge data treatment.
* Challenge model limitations.
* Challenge compensating controls.
* Execute independent tests.
* Develop independent benchmark implementations.
* Develop independent challenger implementations.
* Establish validation test designs.
* Establish validation sampling approaches.
* Establish reconciliation tolerances.
* Establish validation thresholds before applicable results are observed.
* Require investigation of unexplained differences.
* Raise formal validation findings.
* Assign finding severity.
* Recommend remediation.
* Recommend compensating controls.
* Define conditions for temporary or restricted research use.
* Recommend that approval be denied.
* Preserve failed tests and negative results.
* Review remediation.
* Determine finding closure.
* Require validation reassessment following material model changes.
* Recommend partial revalidation.
* Recommend full revalidation.
* Recommend model-use restriction or suspension.

The model owner may provide factual clarification and additional evidence but
may not suppress, rewrite, remove, or override independent-validation
conclusions.

Material disagreements between the model owner and independent validator must
be:

* Documented.
* Supported by the relevant evidence.
* Assessed for model-risk impact.
* Escalated to the documented approval authority.
* Preserved in the validation record.

---

## 4. Validation Scope

The authoritative validation scope and model assumptions must be documented in:

```text
docs/scope_and_assumptions.md
```

The independent validator must confirm that the scope used for validation is
consistent with that document.

The validation scope includes the following areas.

### 4.1 Conceptual Soundness

* Intended model use.
* Product scope.
* Market scope.
* Clearing-member assumptions.
* Position assumptions.
* Portfolio assumptions.
* Base currency.
* Confidence level.
* Margin periods of risk.
* Risk-factor selection.
* Historical observation windows.
* Rebalancing assumptions.
* Treatment of missing prices.
* Treatment of stale prices.
* Treatment of corporate actions.
* Treatment of non-trading days.
* Treatment of market holidays.
* Treatment of valuation dates.
* Excluded risks.
* Known limitations.
* Compensating controls.
* Model-use restrictions.

### 4.2 Margin Methodology

* Historical-simulation Value-at-Risk.
* Parametric Value-at-Risk.
* One-day margin periods of risk.
* Multi-day margin periods of risk.
* Volatility adjustments.
* Liquidity adjustments.
* Concentration-risk components.
* Gap-risk components.
* Portfolio aggregation.
* Diversification assumptions.
* Correlation assumptions.
* Floors.
* Caps.
* Buffers.
* Add-ons.
* Total margin calculation.
* Rounding rules.
* Currency-conversion rules.
* Netting and offset rules.

### 4.3 Quantitative Validation

* Backtesting exception analysis.
* Kupiec unconditional-coverage testing.
* Christoffersen independence testing.
* Christoffersen conditional-coverage testing.
* Basel traffic-light analysis.
* Benchmark-model comparison.
* Challenger-model comparison.
* Parameter-sensitivity analysis.
* Stability testing.
* Stressed-period analysis.
* Extreme-but-plausible stress scenarios.
* Margin-shortfall analysis.
* Portfolio-concentration testing.
* Procyclicality measurement.
* Threshold analysis.
* Reconciliation analysis.
* Statistical power and sample-size limitations.
* Normal-period and stressed-period comparison.

### 4.4 Data and Implementation Validation

* Data-source suitability.
* Data completeness.
* Data accuracy.
* Data consistency.
* Data timeliness.
* Data lineage.
* Missing-value treatment.
* Duplicate-record testing.
* Outlier treatment.
* Stale-price treatment.
* Corporate-action treatment.
* Non-trading-day treatment.
* Risk-factor construction.
* Return calculation.
* Profit-and-loss construction.
* Configuration verification.
* Formula verification.
* Code implementation verification.
* Numerical precision.
* Reconciliation against independent calculations.
* Reproducibility testing.
* Unit-test review.
* Integration-test review.
* Dependency review.
* Environment review.
* Output-schema review.
* Logging review.
* Error-handling review.

### 4.5 Governance Validation

* Documentation completeness.
* Intended-use documentation.
* Model-use controls.
* Change-management controls.
* Model-monitoring requirements.
* Limitation management.
* Compensating controls.
* Finding management.
* Validation independence.
* Approval governance.
* Evidence preservation.
* Revalidation governance.
* Charter compliance.
* Deviation management.

Items outside the approved validation scope must be explicitly identified as:

* Scope exclusions.
* Model limitations.
* Data limitations.
* Implementation limitations.
* Validation limitations.
* Future validation work.

An item must not be omitted from the validation report merely because it could
not be tested.

Untested or incompletely tested material areas must be recorded in the final
validation conclusion.

---

## 5. Evidence Standards

Validation conclusions must be supported by sufficient, relevant, reliable, and
reproducible evidence.

Acceptable evidence includes:

* Version-controlled source code.
* Version-controlled configuration files.
* Unit-test results.
* Integration-test results.
* Independent calculation outputs.
* Data manifests.
* Data-lineage records.
* Reconciliation tables.
* Statistical-test outputs.
* Benchmark comparisons.
* Challenger comparisons.
* Sensitivity-analysis results.
* Stability-analysis results.
* Stress-test results.
* Margin-shortfall results.
* Concentration results.
* Procyclicality results.
* Charts generated from reproducible scripts.
* Tables generated from reproducible scripts.
* Documented reviewer judgments.
* Preserved execution logs.
* Preserved failed tests.
* Preserved negative results.
* Finding records.
* Remediation evidence.
* Monitoring results.
* Change-impact assessments.
* Revalidation records.
* Approval records.
* Environment and dependency records.

Each material validation result must identify, where applicable:

* Model name.
* Model version.
* Code version or Git commit.
* Validation-code version or Git commit.
* Data source.
* Data version.
* Data extraction date.
* Observation period.
* Configuration used.
* Execution date.
* Execution environment.
* Dependency version.
* Test identifier.
* Test owner.
* Test objective.
* Expected result.
* Actual result.
* Applicable tolerance.
* Applicable threshold.
* Pass, fail, warning, or not-applicable status.
* Location of supporting evidence.

Screenshots alone are not sufficient evidence when a reproducible,
machine-readable result can reasonably be produced.

A screenshot may supplement, but must not replace:

* Machine-readable output.
* Source code.
* Configuration.
* Data version.
* Execution record.
* Reproducible calculations.

Manual judgment must be documented with:

* The judgment made.
* The rationale.
* Reviewer identity.
* Review date.
* Supporting evidence.
* Material assumptions.
* Known uncertainty.
* Any dissenting view.

### 5.1 Predetermined Validation Criteria

Material validation decision criteria must be documented before the applicable
validation results are observed.

These criteria include, where applicable:

* Statistical significance levels.
* Confidence levels.
* Exception thresholds.
* Reconciliation tolerances.
* Numerical tolerances.
* Sensitivity limits.
* Stability limits.
* Margin-shortfall thresholds.
* Concentration thresholds.
* Procyclicality thresholds.
* Traffic-light rules.
* Data-quality thresholds.
* Warning thresholds.
* Escalation thresholds.
* Pass and fail criteria.
* Materiality criteria.

Thresholds and tolerances must be maintained in:

* Version-controlled validation configuration files.
* A validation test plan.
* A documented validation methodology.
* Another traceable validation record.

Any threshold established or modified after results are observed must preserve
the previous threshold and document:

* The original threshold.
* The revised threshold.
* The reason for the change.
* The conceptual rationale.
* The empirical rationale.
* The person requesting the change.
* The independent-validator assessment.
* The approval authority.
* The effect on previous results.
* Whether affected tests must be rerun.
* Whether a formal model change or validation deviation is required.

A threshold must not be changed solely to convert a failed or unfavorable result
into a passing or favorable result.

### 5.2 Evidence Retention

Material validation evidence must be retained for the life of the repository.

Evidence must not be removed merely because:

* A later model version becomes available.
* A calculation is corrected.
* A test is rerun successfully.
* A finding is closed.
* A model is retired.
* A later result is more favorable.
* A newer configuration replaces an earlier configuration.

Where files cannot reasonably be stored directly in the repository because of:

* Size.
* Licensing restrictions.
* Confidentiality restrictions.
* Source restrictions.
* Technical limitations.

the repository must retain:

* A data manifest.
* Source identification.
* Extraction date.
* Applicable query or download procedure.
* File hashes, when permitted.
* Data schema.
* Processing instructions.
* Reproduction instructions.
* The reason the underlying file is not retained.
* The location or method through which the source may be reacquired.

Repository history must preserve prior material evidence versions or provide an
equivalent immutable audit record.

Evidence records must not be overwritten without preserving:

* The previous version.
* The reason for revision.
* The revision date.
* The person making the revision.
* The reviewer.
* The effect of the revision.

---

## 6. Finding Severity Definitions

### 6.1 Critical

A critical finding indicates that the model is materially unreliable, invalid,
or unsafe for its intended use.

Examples include:

* Materially incorrect margin calculations.
* Serious implementation defects.
* Severe or systematic under-margining.
* Invalid core methodology.
* Missing or unreliable critical data.
* Material calculation non-reproducibility.
* Evidence manipulation.
* Suppression of failed tests.
* Compromise of validation independence.
* Use of the model outside its intended scope without appropriate controls.
* Falsification or deletion of validation evidence.
* Inability to reproduce core calculations because of an unresolved material
  defect.

Critical findings prevent approval.

A critical finding requires immediate:

* Escalation.
* Model-use restriction.
* Suspension assessment.
* Remediation planning.
* Approval-authority notification.

### 6.2 High

A high finding indicates a significant weakness that could materially affect:

* Model output.
* Risk measurement.
* Margin adequacy.
* Model stability.
* Governance.
* Data reliability.
* Implementation integrity.
* Approved model use.

Examples include:

* Significant backtesting failure.
* Material benchmark-model underperformance.
* Material unexplained reconciliation differences.
* Unstable output under reasonable parameter changes.
* Inadequate stressed-period performance.
* Significant procyclicality.
* Material margin shortfall.
* Missing controls over important assumptions.
* Material undocumented limitations.
* Significant data-quality weaknesses.
* Material monitoring weakness.
* Material change-control weakness.
* Significant implementation inconsistency.

High findings normally prevent full approval.

A high finding may permit conditional approval only when:

* No critical finding exists.
* The risk is clearly understood.
* The residual risk is formally accepted by the approval authority.
* Effective compensating controls are implemented.
* Appropriate model-use restrictions are documented.
* Remediation actions are documented.
* A remediation owner is assigned.
* A target completion date is established.
* Increased monitoring is defined.
* Follow-up validation is required.
* An expiration or mandatory review date is established.

### 6.3 Moderate

A moderate finding indicates a weakness that does not immediately invalidate
the model but requires remediation.

Examples include:

* Incomplete documentation.
* Limited sensitivity evidence.
* Non-material reconciliation differences.
* Weak monitoring thresholds.
* Non-material implementation inconsistencies.
* Incomplete data-lineage documentation.
* Inadequate evidence packaging.
* Weaknesses in change-management controls.
* Incomplete but non-material test coverage.
* Documentation that is sufficient for current use but requires improvement.

Moderate findings may permit conditional approval when:

* Owners are assigned.
* Deadlines are established.
* Interim controls are documented.
* Residual risk is understood.
* Follow-up validation requirements are defined.

### 6.4 Low

A low finding indicates a minor weakness with limited impact.

Examples include:

* Minor documentation inconsistencies.
* Naming defects.
* Formatting defects.
* Non-material code-quality issues.
* Minor evidence-packaging deficiencies.
* Minor test-coverage gaps with limited model impact.
* Minor traceability defects that do not prevent reproduction.

Low findings do not normally prevent approval.

### 6.5 Observation

An observation identifies an improvement opportunity that is not considered a
formal deficiency.

Observations do not prevent approval but must remain documented.

Observations may be tracked separately from formal findings but must not be
deleted merely because they do not require remediation.

---

## 7. Approval Criteria

The final validation conclusion must be one of:

* Approved for the documented research use.
* Conditionally approved for the documented research use.
* Not approved.
* Validation incomplete.

Approval is based on the totality of evidence.

Approval must not be determined solely by whether individual statistical tests
pass or fail.

### 7.1 Approved for the Documented Research Use

Approval for the documented research use requires:

* No unresolved critical findings.
* No unresolved high findings.
* Core calculations independently reproduced within documented tolerances.
* Material reconciliation differences resolved.
* Required backtesting completed.
* Required statistical tests completed.
* Required benchmark analysis completed.
* Required challenger analysis completed.
* Required sensitivity testing completed.
* Required stability testing completed.
* Required stress testing completed.
* Material data-quality issues resolved.
* Material implementation issues resolved.
* Material governance issues resolved.
* Model limitations documented.
* Scope exclusions documented.
* Compensating controls documented.
* Monitoring requirements defined.
* Model-use restrictions documented where applicable.
* Required evidence preserved.
* Validation evidence reproducible.
* Intended research use clearly documented.
* Final validation conclusion supported by the totality of evidence.

Open moderate or low findings may remain only when:

* Their impact is not material to the approval conclusion.
* Remediation actions are documented.
* Responsible owners are assigned.
* Target dates are established where appropriate.
* The independent validator concludes that the remaining risk is acceptable for
  the documented research use.

### 7.2 Conditionally Approved for the Documented Research Use

Conditional approval may be recommended when:

* No unresolved critical finding exists.
* Remaining weaknesses are understood.
* Remaining risks are controlled.
* Compensating controls are documented.
* Use restrictions are documented where necessary.
* Remediation actions are defined.
* Remediation owners are assigned.
* Target completion dates are established.
* Follow-up validation requirements are documented.
* Increased monitoring is documented where necessary.
* The remaining risk is acceptable only under stated conditions.

Conditional approval must identify:

* The conditions of approval.
* Applicable model-use restrictions.
* Required remediation.
* Responsible remediation owners.
* Target completion dates.
* Required monitoring.
* Warning thresholds.
* Escalation thresholds.
* Required follow-up validation.
* Conditions requiring withdrawal of approval.
* The conditional-approval expiration or mandatory review date.
* The authority responsible for reviewing expiration or extension.

Conditional approval must not be indefinite.

Failure to satisfy a condition by the required date must trigger:

* Escalation.
* Reassessment of the conclusion.
* Possible model-use restriction.
* Possible withdrawal of conditional approval.
* Partial or full revalidation.

### 7.3 Not Approved

The model must not be approved when:

* A critical finding remains unresolved.
* Core calculations cannot be independently reproduced.
* Material reconciliation differences remain unexplained.
* Material under-margining remains unexplained.
* Required backtesting is incomplete or materially deficient.
* Required statistical tests are missing.
* Data are unsuitable for the intended use.
* Material implementation defects remain unresolved.
* Validation independence has been compromised.
* Required evidence is missing or unreliable.
* Required evidence is materially non-reproducible.
* The model is outside its documented intended use.
* The model exceeds documented research-use limits.
* Compensating controls are inadequate.
* Conditional-approval requirements have materially failed.
* Material charter violations remain unresolved.
* The totality of evidence indicates that the model is not appropriate for the
  documented research use.

A not-approved conclusion must identify:

* The principal reasons for non-approval.
* Applicable findings.
* Required remediation.
* Model-use restrictions.
* Conditions for resubmission.
* Required partial or full revalidation.
* Evidence required before reconsideration.

### 7.4 Validation Incomplete

A validation-incomplete conclusion must be issued when the independent
validator cannot obtain sufficient, relevant, reliable, and reproducible
evidence to reach an approved, conditionally approved, or not-approved
conclusion.

Validation may be incomplete when:

* Required data are unavailable.
* Required validation tests have not been completed.
* Material portions of the approved validation scope remain untested.
* Core calculations cannot yet be independently assessed.
* Required model documentation is unavailable.
* The execution environment cannot be reproduced.
* Material evidence is missing.
* Material evidence is corrupted.
* Material evidence is inconsistent.
* Material evidence is inaccessible.
* Open questions prevent a reliable final conclusion.
* Validation work has been suspended.
* Validation work has been terminated before completion.
* A material dependency prevents completion.
* The model or validation implementation is not sufficiently developed for
  assessment.

A validation-incomplete conclusion does not indicate that the model is
acceptable or unacceptable.

It indicates that the available evidence is insufficient to reach a final
substantive conclusion.

A model with a validation-incomplete conclusion must not be represented as:

* Approved.
* Conditionally approved.
* Validated.
* Suitable for unrestricted research use.

The validation-incomplete record must identify:

* The incomplete validation activities.
* The reason each activity remains incomplete.
* The evidence or information still required.
* The responsible owner.
* The target completion date, when applicable.
* Interim model-use restrictions.
* Required compensating controls.
* Conditions necessary to resume validation.
* Required follow-up validation scope.
* Whether any completed results remain valid.
* Whether any completed tests must be rerun.

### 7.5 Final Validation Conclusion Record

The final validation conclusion must be documented in a version-controlled
validation record.

The conclusion record must identify:

* Model name.
* Model version.
* Primary-model code version or Git commit.
* Independent-validation code version or Git commit.
* Data version.
* Applicable observation period.
* Configuration versions.
* Execution environment.
* Documented intended research use.
* Validation scope.
* Scope exclusions.
* Validation work completed.
* Validation work not completed.
* Material assumptions.
* Material limitations.
* Open findings by severity.
* Risk-accepted findings.
* Compensating controls.
* Model-use restrictions.
* Required remediation.
* Required monitoring.
* Revalidation requirements.
* Final validation conclusion.
* Rationale for the conclusion.
* Independent validator.
* Conclusion date.
* Approval-authority decision.
* Approval-authority decision date.
* Evidence location.

The conclusion must be supported by the totality of the validation evidence.

The conclusion must not be based solely on whether individual quantitative
tests passed or failed.

---

## 8. Prohibition on Validation-Driven Tuning

The model must not be tuned merely to pass validation tests.

Model development, calibration, and modification decisions must be based on
sound:

* Conceptual considerations.
* Empirical considerations.
* Operational considerations.
* Risk-management considerations.
* Intended-use considerations.

Validation results must not be used to reverse-engineer a passing outcome.

Any model change made after reviewing validation results must have:

* A documented conceptual rationale.
* A documented empirical rationale.
* A clear description of the identified deficiency or limitation.
* Approval through the applicable model-change governance process.
* Separate model-development evidence.
* Separate independent-validation evidence.
* An assessment of model-selection risk.
* An assessment of overfitting risk.
* An assessment across normal market periods.
* An assessment across stressed market periods.
* An assessment across relevant products.
* An assessment across relevant portfolios.
* An assessment of the effect on margin adequacy.
* An assessment of the effect on procyclicality.
* An assessment of the effect on model stability.
* Re-execution of all materially affected validation tests.
* Preservation of the original model results.
* Preservation of the original validation evidence.
* Documentation of the model version.
* Documentation of the configuration version.
* Documentation of the data period.
* Documentation of the code version associated with the change.

The following practices are prohibited:

* Changing model parameters solely because a validation test failed.
* Repeatedly adjusting parameters until a statistical test produces a passing
  result.
* Selecting a favorable calibration period after reviewing validation results.
* Selecting a favorable backtesting period after reviewing validation results.
* Excluding unfavorable portfolios without documented conceptual
  justification.
* Excluding unfavorable clearing members without documented justification.
* Removing unfavorable stress scenarios.
* Reducing stress severity solely to obtain favorable results.
* Changing validation thresholds after observing results solely to obtain a
  passing classification.
* Changing exception definitions solely to improve backtesting performance.
* Changing data-cleaning rules solely to eliminate unfavorable observations.
* Reporting only the most favorable model specification.
* Reporting only favorable benchmark comparisons.
* Suppressing unfavorable sensitivity results.
* Suppressing unfavorable stability results.
* Replacing failed results without preserving the original evidence.
* Allowing the model owner to select validation methods solely to improve the
  likelihood of approval.
* Allowing the model owner to alter independent-validation conclusions.
* Redefining the intended use solely to avoid an unfavorable result.
* Reclassifying a material issue as immaterial without documented support.

When model changes are proposed following a failed or unfavorable validation
result, the model owner must document:

* The original model specification.
* The original validation result.
* The reason the result was considered deficient.
* The proposed model change.
* The conceptual basis for the change.
* The empirical evidence supporting the change.
* Alternative changes considered.
* The expected effect of the change.
* Potential unintended consequences.
* The approval authority for the change.
* The model version in which the change was implemented.

The independent validator must determine whether the proposed change:

* Addresses the underlying model weakness.
* Is conceptually justified.
* Is supported by sufficient empirical evidence.
* Creates new model risk.
* Increases overfitting risk.
* Increases model-selection risk.
* Remains appropriate across normal conditions.
* Remains appropriate across stressed conditions.
* Remains appropriate across the intended product universe.
* Remains appropriate across the intended portfolio universe.
* Requires targeted review.
* Requires partial revalidation.
* Requires full revalidation.

Parameter changes must be treated as formal model changes when they materially
affect:

* Model output.
* Risk sensitivity.
* Margin adequacy.
* Backtesting.
* Procyclicality.
* Stability.
* Intended use.
* Model limitations.
* Compensating controls.

A successful result obtained after model modification does not invalidate or
replace the original failed result.

Both the original result and the revised result must remain preserved in the
validation evidence.

Material validation-driven tuning, manipulation of validation evidence, or
suppression of unfavorable results may result in:

* A formal validation finding.
* Increased finding severity.
* Escalation to the approval authority.
* A requirement for additional independent review.
* Targeted validation review.
* Partial revalidation.
* Full revalidation.
* Conditional approval.
* Withdrawal of conditional approval.
* A not-approved conclusion.
* Model-use restriction.
* Model suspension.

---

## 9. Preservation of Failed Tests and Negative Results

All failed tests, unexpected outcomes, exceptions, unfavorable benchmark
comparisons, unfavorable challenger comparisons, and negative results must be
preserved.

They must not be:

* Deleted.
* Hidden.
* Suppressed.
* Reclassified without explanation.
* Replaced by only favorable reruns.
* Excluded from the validation report without documented justification.
* Removed from version-controlled evidence.
* Overwritten without retaining the original result.
* Renamed or relocated for the purpose of concealing the result.
* Omitted merely because remediation was completed later.

When a failed test is corrected and rerun, the evidence record must preserve:

* The original failed result.
* The original test configuration.
* The original code version.
* The original data version.
* The cause of the failure.
* The corrective action.
* The revised code or configuration version.
* The rerun result.
* The validator's assessment of whether the issue is resolved.
* Any residual limitation.
* Any related finding identifier.

A successful rerun does not erase the original failure.

A corrected result must not be presented without clear identification that:

* A previous result failed.
* A correction was applied.
* The result was rerun.
* The original evidence remains available.

Negative results remain part of the permanent validation record even when they
do not result in a formal finding.

---

## 10. Independence Control

Independent validation must remain organizationally, procedurally, and
technically separate from primary model development throughout the model
lifecycle.

The following independence controls apply:

* Primary model code must remain under `src/ccp_margin/models/`.
* Independent-validation code must remain under
  `src/ccp_margin/validation/`.
* Core validation calculations must be independently implemented.
* Validation code must not import private primary-model functions.
* Validation code must not import undocumented primary-model implementation
  utilities.
* Validation code must not reuse primary-model intermediate results merely to
  reproduce the primary output.
* Shared public data schemas may be used where necessary.
* Approved configuration values may be used where necessary.
* Documented interfaces may be used where necessary.
* Shared resources must not compromise independent calculation.
* Validation methodology must be determined by the independent validator.
* Test design must be determined by the independent validator.
* Materiality thresholds must be determined or independently accepted by the
  independent validator before applicable results are observed.
* Benchmark selection must be determined by the independent validator.
* Challenger selection must be determined by the independent validator.
* Sampling decisions must be determined by the independent validator.
* Validation conclusions must be determined by the independent validator.
* Differences between primary-model and independent-validation results must be
  investigated.
* Differences must be reconciled where possible.
* Unresolved differences must be documented.
* The model owner cannot approve their own model.
* The model owner cannot assign validation-finding severity.
* The model owner cannot reduce validation-finding severity without
  independent-validator agreement.
* The model owner cannot close a validation finding without
  independent-validator review.
* Failed tests cannot be deleted.
* Exceptions cannot be suppressed.
* Unexpected outcomes cannot be overwritten.
* Negative results cannot be removed.
* Material model changes require validation reassessment.
* Material data changes require validation reassessment.
* Material methodology changes require validation reassessment.
* Material parameter changes require validation reassessment.
* Material configuration changes require validation reassessment.
* Material implementation changes require validation reassessment.
* Validation conclusions must remain traceable to independently generated code,
  calculations, tests, evidence, and professional judgment.
* Material disagreements must be documented.
* Material disagreements must be escalated to the approval authority.
* Validation personnel must disclose actual conflicts of interest.
* Validation personnel must disclose potential conflicts of interest.
* Validation personnel must disclose perceived conflicts of interest.
* Validation evidence must remain under version control.
* Validation evidence must identify the validator.
* Validation evidence must identify the execution date.
* Validation evidence must identify the code version.
* Validation evidence must identify the configuration version.
* Validation evidence must identify the data version.
* Validation evidence must identify the results.
* Validation evidence must identify the conclusions.

Development assistance may be provided to the independent validator for:

* Administrative support.
* Environment configuration.
* Infrastructure support.
* Data access.
* Repository access.
* Technical support.
* Dependency installation.
* Execution troubleshooting.

Such assistance must be documented when material.

Development assistance must not determine or influence:

* Validation methodology.
* Test selection.
* Test implementation.
* Finding classification.
* Finding severity.
* Interpretation of results.
* Remediation acceptance.
* Approval recommendations.
* Final validation conclusions.
* Revalidation decisions.

Any situation that could compromise validation independence must be:

* Disclosed.
* Documented.
* Assessed.
* Escalated.
* Resolved or controlled before the affected conclusion is issued.

---

## 11. Finding Management

Every formal validation finding must be recorded, tracked, reviewed, and
retained from initial identification through final disposition.

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
* Management or model-owner response.
* Validator review notes.
* Validator closure assessment.
* Closure date, when applicable.
* Related monitoring identifier, when applicable.
* Related change identifier, when applicable.
* Related deviation identifier, when applicable.
* Related revalidation decision, when applicable.

Finding identifiers must use the following format:

```text
FIND-YYYY-NNN
```

where:

* `YYYY` is the year in which the finding was identified.
* `NNN` is a sequential three-digit number.

Examples include:

```text
FIND-2026-001
FIND-2026-002
FIND-2026-003
```

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

* **Open** means that the finding has been issued and remediation has not been
  completed.
* **Remediation in progress** means that the responsible owner is actively
  implementing corrective action.
* **Pending validation review** means that remediation evidence has been
  submitted for independent-validator assessment.
* **Risk accepted** means that the approval authority has formally accepted the
  residual risk instead of requiring full remediation. Risk acceptance does not
  constitute validation closure.
* **Closed** means that the independent validator has confirmed that all closure
  requirements have been satisfied.
* **Overdue** means that the target completion date has passed and the finding
  has not been closed.

A finding may be closed only after the independent validator confirms that:

* Required remediation is complete.
* Supporting evidence is sufficient.
* Relevant tests have been rerun.
* Original failed results remain preserved.
* Rerun results are documented.
* The identified issue has been resolved.
* No material residual risk remains unaddressed.
* Required compensating controls have been implemented.
* The closure conclusion is supported by independently reviewed evidence.

The model owner or remediation owner may request closure but cannot
independently close a validation finding.

Risk acceptance does not automatically constitute validation closure.

A risk-accepted finding must remain:

* Separately identifiable.
* Supported by documented approval.
* Subject to monitoring.
* Subject to escalation requirements.
* Subject to reassessment.
* Subject to an expiration or review date.

Any change to a finding's severity, status, target date, remediation
requirement, or disposition must be documented with:

* Date of the change.
* Previous value.
* Revised value.
* Reason for the change.
* Person requesting the change.
* Independent-validator review.
* Approval authority, when applicable.

Finding evidence must remain version-controlled and traceable.

The following must not be overwritten or deleted:

* Previous finding records.
* Management responses.
* Failed tests.
* Remediation submissions.
* Validator assessments.
* Closure decisions.
* Risk-acceptance decisions.

Closed findings must remain in the permanent validation record.

---

## 12. Change and Revalidation Triggers

Partial or full revalidation is required when a material change, deterioration,
defect, control failure, or change in model use could affect:

* Conceptual soundness.
* Implementation integrity.
* Model performance.
* Data reliability.
* Model limitations.
* Model risk.
* Approved research use.
* Monitoring requirements.
* Compensating controls.
* Prior validation conclusions.

Revalidation triggers include:

* Methodology changes.
* Parameter changes.
* Confidence-level changes.
* Margin-period-of-risk changes.
* New products.
* New markets.
* New asset classes.
* Changes to portfolio aggregation.
* Changes to volatility adjustments.
* Changes to liquidity adjustments.
* Changes to concentration methodology.
* Changes to gap-risk methodology.
* Material data-source changes.
* Material data-processing changes.
* Material code changes.
* Material configuration changes.
* Significant backtesting deterioration.
* Significant benchmark deterioration.
* Significant challenger deterioration.
* Significant margin shortfall.
* Significant procyclicality.
* New regulatory expectations.
* Changes to intended model use.
* Identification of a material implementation defect.
* Significant changes in portfolio composition.
* Significant changes in market behavior.
* Failure of a compensating control.
* Expiration of conditional approval.

Additional revalidation triggers include:

* Changes to model assumptions.
* Changes to model limitations.
* Changes to valuation methods.
* Changes to pricing methods.
* Changes to risk-factor mappings.
* Changes to data-quality controls.
* Changes to missing-data treatment.
* Changes to corporate-action treatment.
* Changes to holiday treatment.
* Changes to non-trading-day treatment.
* Changes to portfolio netting rules.
* Changes to portfolio offset rules.
* Changes to stressed-period selection.
* Changes to model calibration windows.
* Changes to model thresholds.
* Changes to materiality limits.
* Changes to software libraries that could affect results.
* Changes to model dependencies that could affect results.
* Migration to a new platform.
* Migration to a new operating environment.
* Migration to a new database.
* Migration to new execution infrastructure.
* Changes to production interfaces for any future operational implementation.
* Changes to scheduling or orchestration.
* Changes to downstream consumption.
* Repeated operational incidents.
* Repeated unexplained calculation differences.
* Discovery that validation evidence is incomplete.
* Discovery that validation evidence is inaccurate.
* Discovery that validation evidence is not reproducible.
* Failure to complete required remediation by an approved deadline.
* Material findings issued by another independent reviewer.
* Changes that invalidate approved compensating controls.
* Model performance outside approved monitoring thresholds.
* Model use outside the previously validated scope.
* Material charter deviations.
* Material changes to the research objective.

Every proposed or completed material change must be documented through a
change-impact assessment.

The change-impact assessment must contain:

* Unique change identifier.
* Change title.
* Date identified or proposed.
* Requesting party.
* Responsible implementation owner.
* Description of the change.
* Business, research, or risk rationale.
* Affected model components.
* Affected data.
* Affected code.
* Affected configurations.
* Affected assumptions.
* Affected documentation.
* Expected impact on margin calculations.
* Expected impact on model risk.
* Applicable revalidation triggers.
* Materiality assessment.
* Proposed revalidation scope.
* Required testing.
* Required evidence.
* Implementation date.
* Independent-validator review.
* Validation decision.
* Required conditions or restrictions.
* Final approval or escalation record.

Change identifiers must use the following format:

```text
CHG-YYYY-NNN
```

where:

* `YYYY` is the year in which the change was identified.
* `NNN` is a sequential three-digit number.

Examples include:

```text
CHG-2026-001
CHG-2026-002
CHG-2026-003
```

The independent validator must classify the required response as one of:

* No additional validation required.
* Targeted validation review.
* Partial revalidation.
* Full revalidation.
* Immediate model-use restriction or suspension pending review.

A targeted validation review may be appropriate when the change is:

* Limited.
* Well understood.
* Low risk.
* Not expected to alter core methodology.
* Not expected to alter the approved risk profile.
* Not expected to alter the documented research use materially.

Partial revalidation may include:

* Independent recalculation.
* Code review.
* Data reconciliation.
* Configuration review.
* Backtesting.
* Benchmark comparison.
* Challenger comparison.
* Sensitivity testing.
* Stability testing.
* Stress testing.
* Margin-shortfall analysis.
* Concentration analysis.
* Procyclicality analysis.
* Implementation testing.
* Documentation review.
* Review of compensating controls.

Full revalidation may be required when:

* Core model methodology changes.
* The approved purpose changes materially.
* The approved scope changes materially.
* A new material asset class is introduced.
* A new material market is introduced.
* A new material product is introduced.
* A material implementation defect affects historical or current results.
* Performance deterioration is significant.
* Performance deterioration is persistent.
* Multiple related changes collectively alter the model-risk profile.
* Prior validation conclusions are no longer reliable.
* Conditional approval expires without satisfactory remediation.
* Approval-authority requirements mandate full revalidation.

The independent validator determines the required depth and scope of
revalidation based on:

* Nature of the change.
* Magnitude of the change.
* Components affected.
* Model-risk significance.
* Portfolio impact.
* Financial impact.
* Implementation complexity.
* Performance implications.
* Data implications.
* Governance implications.
* Operational dependencies.
* Existing findings.
* Effectiveness of compensating controls.
* Reliability of available evidence.
* Cumulative impact of related changes.

The model owner may propose a revalidation scope but cannot make the final
revalidation determination.

A material change must not be used without the required independent review
unless an authorized temporary exception is documented with:

* Research or business justification.
* Risk assessment.
* Temporary controls.
* Model-use restrictions.
* Approval authority.
* Expiration date.
* Required follow-up validation.

All revalidation decisions, testing, evidence, conclusions, conditions, and
approvals must remain version-controlled and traceable.

Completion of implementation testing does not by itself constitute completion
of independent revalidation.

### 12.1 Periodic Validation Review

The final validation conclusion must establish a periodic validation-review
date or document why a time-based review is not applicable to the current
research use.

A periodic review must be performed at least annually while the model remains
active in the repository, unless a shorter period is required by:

* Conditional approval.
* A finding.
* A monitoring breach.
* A model change.
* A deviation.
* An approval-authority decision.

A periodic review must assess whether:

* The intended research use has changed.
* The validation scope remains appropriate.
* Model assumptions remain reasonable.
* Model limitations remain accurate.
* Data sources remain available.
* Data sources remain suitable.
* Dependencies remain suitable.
* Previously completed tests remain reproducible.
* Findings remain accurately documented.
* Monitoring requirements remain appropriate.
* Material code changes have occurred.
* Material configuration changes have occurred.
* Material environment changes have occurred.
* Compensating controls remain effective.
* Partial or full revalidation is required.

A periodic review is not a substitute for immediate revalidation when a
material trigger occurs.

The periodic-review record must identify:

* Review date.
* Reviewer.
* Model version.
* Validation version.
* Changes since the prior review.
* Monitoring results reviewed.
* Findings reviewed.
* Limitations reviewed.
* Revalidation decision.
* Required follow-up action.
* Next review date.

---

## 13. Ongoing Monitoring Expectations

The independent-validation conclusion must define the ongoing monitoring
requirements necessary to confirm that the model continues to operate within:

* Its documented scope.
* Its assumptions.
* Its limitations.
* Its performance expectations.
* Its documented research-use limits.
* Its compensating controls.
* Its approved conditions.

Monitoring requirements must be proportionate to:

* Model materiality.
* Model complexity.
* Portfolio impact.
* Data dependencies.
* Implementation risk.
* Validation findings.
* Known limitations.
* Conditional-approval requirements.

Required monitoring must include, where applicable:

* Daily or periodic backtesting.
* Exception-rate monitoring.
* Kupiec unconditional-coverage monitoring.
* Christoffersen independence monitoring.
* Christoffersen conditional-coverage monitoring.
* Basel traffic-light classification.
* Margin-shortfall monitoring.
* Benchmark-model comparison.
* Challenger-model comparison.
* Sensitivity monitoring.
* Parameter-stability monitoring.
* Model-output stability monitoring.
* Procyclicality monitoring.
* Concentration monitoring.
* Liquidity-risk monitoring.
* Gap-risk monitoring.
* Portfolio-composition monitoring.
* Data-quality monitoring.
* Missing-data monitoring.
* Stale-price monitoring.
* Duplicate-record monitoring.
* Configuration-change monitoring.
* Code-version monitoring.
* Dependency-version monitoring.
* Production-reconciliation monitoring for any future production
  implementation.
* Model-performance thresholds.
* Warning thresholds.
* Escalation thresholds.
* Required management reporting.
* Finding-management triggers.
* Revalidation triggers.

Each required monitoring metric must identify:

* Unique monitoring identifier.
* Monitoring metric name.
* Monitoring objective.
* Applicable model component.
* Calculation methodology.
* Data source.
* Monitoring frequency.
* Observation window.
* Responsible monitoring owner.
* Independent-review responsibility.
* Approved threshold.
* Warning threshold.
* Escalation threshold.
* Required response when a threshold is breached.
* Required reporting recipient.
* Evidence location.
* Retention requirement.
* Related finding identifier, when applicable.
* Related change identifier, when applicable.
* Related revalidation trigger, when applicable.

Monitoring identifiers must use the following format:

```text
MON-YYYY-NNN
```

where:

* `YYYY` is the year in which the monitoring requirement was established.
* `NNN` is a sequential three-digit number.

Examples include:

```text
MON-2026-001
MON-2026-002
MON-2026-003
```

### 13.1 Monitoring Metric Conditions

Permitted monitoring metric conditions are:

* Within threshold.
* Warning threshold breached.
* Escalation threshold breached.
* Not applicable.

These conditions describe the result of the monitoring metric.

They do not describe the workflow status of a breach investigation.

### 13.2 Monitoring-Breach Workflow Statuses

Permitted monitoring-breach workflow statuses are:

* Open.
* Under investigation.
* Remediation in progress.
* Pending validation review.
* Risk accepted.
* Closed.
* Overdue.

These statuses describe the management and validation disposition of an
identified breach.

A breach may be closed only after the required investigation, corrective
action, evidence review, and closure assessment are complete.

### 13.3 Traffic-Light Classification

Where traffic-light classification is used, the approved classification rules
must be documented in the monitoring plan and applied consistently.

At a minimum:

* **Green** indicates performance within approved limits.
* **Amber** indicates deterioration requiring investigation, increased
  monitoring, or management attention.
* **Red** indicates material deterioration requiring escalation, model-use
  restriction, remediation, or revalidation assessment.

Traffic-light thresholds must be documented before applicable monitoring
results are observed.

### 13.4 Monitoring Breaches

A monitoring result that breaches an approved warning or escalation threshold
must be:

* Preserved.
* Recorded in the monitoring register.
* Investigated.
* Supported by reproducible evidence.
* Assessed for model impact.
* Assessed for portfolio impact.
* Assessed for data defects.
* Assessed for implementation defects.
* Assessed against existing findings.
* Assessed against known limitations.
* Assigned to a responsible owner.
* Reported within the required escalation period.
* Tracked until an approved disposition is reached.

The monitoring-breach record must contain:

* Monitoring identifier.
* Breach identifier.
* Breach date.
* Metric result.
* Applicable threshold.
* Breach classification.
* Workflow status.
* Affected portfolios.
* Affected model components.
* Preliminary impact assessment.
* Root cause, when known.
* Immediate action taken.
* Compensating controls.
* Responsible owner.
* Target resolution date.
* Management or model-owner response.
* Independent-validator review.
* Finding identifier, when applicable.
* Change identifier, when applicable.
* Revalidation decision, when applicable.
* Closure assessment.
* Closure date.

Monitoring-breach identifiers must use the following format:

```text
BRH-YYYY-NNN
```

Examples include:

```text
BRH-2026-001
BRH-2026-002
BRH-2026-003
```

A threshold breach must trigger a formal validation finding when the breach
identifies a material weakness requiring remediation and formal tracking.

A threshold breach must trigger a change and revalidation assessment when it
indicates that:

* Model performance has deteriorated materially.
* Model assumptions may no longer be valid.
* Market behavior has changed materially.
* Portfolio composition has changed materially.
* A compensating control has failed.
* An implementation defect may exist.
* Model use has moved outside the validated scope.
* Prior validation conclusions may no longer remain reliable.

Monitoring results must not be:

* Deleted.
* Suppressed.
* Overwritten.
* Replaced solely by later favorable results.
* Reclassified without explanation.
* Removed from the monitoring record.

Corrected calculations and successful reruns must preserve:

* The original monitoring result.
* The original breach classification.
* The original data version.
* The original code version.
* The original configuration.
* The identified cause.
* The corrective action.
* The revised code, data, or configuration version.
* The rerun result.
* The final assessment.

The model owner may perform routine monitoring activities but cannot
unilaterally:

* Remove a monitoring breach.
* Change an approved threshold.
* Reduce a breach classification.
* Close a material breach.
* Determine that revalidation is unnecessary after a material breach.
* Delete the original monitoring result.

Material threshold changes require independent-validator review and must be
processed through the change and revalidation framework.

Monitoring results must be reported at the frequency established in the
approved monitoring plan.

Material breaches must be escalated without waiting for the next routine
reporting cycle.

The independent validator must periodically assess whether:

* Monitoring metrics remain appropriate.
* Thresholds remain risk-sensitive.
* Monitoring data remain reliable.
* Breach responses remain timely.
* Compensating controls remain effective.
* Monitoring results support the continued validity of the validation
  conclusion.

All monitoring calculations, threshold changes, breach investigations,
management responses, validator reviews, findings, and revalidation decisions
must remain version-controlled and traceable.

---

## 14. Charter Enforcement

This charter applies throughout the complete model lifecycle, including:

* Model design.
* Model development.
* Model testing.
* Independent validation.
* Finding remediation.
* Model approval.
* Model implementation.
* Research use.
* Any future production use.
* Ongoing monitoring.
* Model change.
* Revalidation.
* Model-use restriction.
* Model suspension.
* Model retirement.

The charter applies to:

* Model owners.
* Model developers.
* Data owners.
* Technology personnel.
* Implementation personnel.
* Independent validators.
* Remediation owners.
* Monitoring owners.
* Model users.
* Approval authorities.
* Governance committees, where applicable.
* Third parties performing activities within the model lifecycle.

Compliance with this charter must be demonstrated through documented,
reproducible, version-controlled, and independently reviewable evidence.

### 14.1 Required Charter Compliance

Each lifecycle activity must comply with the applicable requirements for:

* Role separation.
* Validation independence.
* Documentation.
* Testing.
* Evidence preservation.
* Finding management.
* Change control.
* Revalidation.
* Ongoing monitoring.
* Approval authority.
* Escalation.
* Record retention.

A model must not be approved solely because required governance evidence is
expected to be completed later.

Missing, incomplete, inconsistent, or non-reproducible evidence must be
evaluated as a potential validation deficiency.

### 14.2 Charter Deviations

A deviation exists when a model-lifecycle activity does not comply with an
applicable requirement of this charter.

Deviations from this charter must be:

* Identified promptly.
* Documented.
* Justified.
* Risk assessed.
* Assigned to a responsible owner.
* Supported by compensating controls, when necessary.
* Reviewed by the independent validator.
* Approved or rejected by the documented approval authority.
* Assigned an effective date.
* Assigned an expiration or review date.
* Retained as part of the model-governance evidence.
* Monitored until resolved, expired, superseded, or incorporated through a
  formally approved charter amendment.

A deviation must not be approved merely to avoid:

* A validation finding.
* A remediation requirement.
* A model-use restriction.
* A revalidation requirement.
* An unfavorable approval conclusion.

The model owner may request a deviation but cannot approve their own deviation.

The independent validator must assess whether the proposed deviation:

* Impairs validation independence.
* Limits the required validation scope.
* Prevents independent reproduction.
* Weakens evidence preservation.
* Affects finding severity.
* Affects finding closure.
* Changes approval criteria.
* Creates material model risk.
* Requires model-use restrictions.
* Requires partial revalidation.
* Requires full revalidation.
* Requires escalation to a higher approval authority.

### 14.3 Deviation Identification

Each charter deviation must use the following identifier:

```text
DEV-YYYY-NNN
```

where:

* `YYYY` is the year in which the deviation was identified.
* `NNN` is a sequential three-digit number.

Examples include:

```text
DEV-2026-001
DEV-2026-002
DEV-2026-003
```

Each deviation record must contain:

* Unique deviation identifier.
* Deviation title.
* Date identified.
* Requesting party.
* Responsible owner.
* Applicable charter section.
* Description of the deviation.
* Reason for the deviation.
* Duration of the deviation.
* Affected model components.
* Affected lifecycle activities.
* Model-risk assessment.
* Operational-risk assessment.
* Regulatory or policy implications, when applicable.
* Impact on validation independence.
* Impact on model approval.
* Impact on existing findings.
* Proposed compensating controls.
* Required monitoring.
* Required model-use restrictions.
* Independent-validator assessment.
* Approval-authority decision.
* Effective date.
* Expiration or review date.
* Current status.
* Resolution requirements.
* Closure assessment.
* Closure date, when applicable.
* Supporting-evidence references.

Permitted deviation statuses are:

* Draft.
* Pending independent review.
* Pending authority decision.
* Approved.
* Rejected.
* Remediation in progress.
* Expired.
* Superseded.
* Closed.

### 14.4 Approval Conditions

An approved deviation must clearly state:

* The exact charter requirement affected.
* The approved exception.
* The rationale for approval.
* The residual risk.
* The compensating controls.
* The responsible owner.
* Any model-use restrictions.
* Monitoring requirements.
* Escalation thresholds.
* Required remediation.
* The effective date.
* The expiration or mandatory review date.
* Conditions for extension.
* Conditions requiring immediate withdrawal.

Approval of a deviation does not amend the charter.

A recurring or permanent conflict with the charter must be addressed through:

* Remediation of the underlying process.
* A formally reviewed charter amendment.
* A formally approved charter amendment.
* Model-use restriction.
* Model suspension.
* Model retirement.

Indefinite deviation approval is not permitted without a documented charter
amendment or equivalent governance action.

### 14.5 Emergency Deviations

An emergency deviation may be used only when immediate action is necessary to
address a material:

* Operational event.
* Market event.
* Data event.
* Technology event.
* Risk-management event.

An emergency deviation must:

* Be documented as soon as practicable.
* Identify the emergency condition.
* State why normal approval could not be obtained in advance.
* Identify the temporary action taken.
* Define temporary controls.
* Define model-use restrictions.
* Be escalated immediately.
* Receive retrospective independent-validator review.
* Receive formal approval-authority disposition.
* Include a short and defined expiration period.
* Be withdrawn when the emergency condition no longer exists.

Emergency treatment does not eliminate:

* Documentation requirements.
* Review requirements.
* Evidence requirements.
* Remediation requirements.
* Revalidation requirements.

### 14.6 Prohibited Deviations

A deviation must not be used to:

* Permit the model owner to approve their own model.
* Permit the model owner to determine finding severity.
* Permit the model owner to close validation findings without validator review.
* Remove failed tests.
* Remove unfavorable evidence.
* Suppress material validation results.
* Alter independent-validator conclusions.
* Avoid required revalidation after a material change.
* Approve a model with an unresolved critical finding.
* Conceal a material implementation defect.
* Bypass required escalation.
* Falsify governance evidence.
* Overwrite governance evidence.
* Delete governance evidence.
* Retroactively authorize conduct that materially impaired validation
  independence.
* Convert a validation-incomplete conclusion into approval without completing
  the required work.

A requested deviation involving any prohibited activity must be rejected and
escalated.

### 14.7 Noncompliance and Enforcement Actions

An unapproved, expired, violated, or inadequately controlled deviation may
result in:

* A formal validation finding.
* Increased finding severity.
* Additional testing.
* Increased monitoring.
* Mandatory remediation.
* Model-use restrictions.
* Conditional approval.
* Withdrawal of conditional approval.
* Deferral of model approval.
* Denial of model approval.
* A validation-incomplete conclusion.
* Partial revalidation.
* Full revalidation.
* Suspension of model use.
* Escalation to the documented approval authority.
* Model retirement when risks cannot be adequately controlled.

The independent validator must assess the effect of charter noncompliance on
the reliability of the validation conclusion.

Material noncompliance must be escalated without waiting for the next routine
reporting cycle.

### 14.8 Deviation Closure

A deviation may be closed only after the independent validator confirms that:

* The deviation has ended.
* Required remediation is complete.
* Compensating controls operated as approved.
* Required monitoring was performed.
* Applicable restrictions were observed.
* Supporting evidence is sufficient.
* Related findings have been addressed or remain appropriately tracked.
* No material residual risk remains unaddressed.
* Closure has been approved by the appropriate authority, when required.

Expiration of an approved deviation does not automatically constitute closure.

An expired deviation that remains unresolved must be treated as unapproved
noncompliance and evaluated for:

* A formal finding.
* Model-use restriction.
* Revalidation.
* Withdrawal of approval.
* Model suspension.

### 14.9 Evidence and Traceability

All deviation requests, assessments, decisions, extensions, rejections,
compensating controls, monitoring results, evidence, findings, and closure
decisions must remain version-controlled and traceable.

Original records must not be overwritten or deleted.

Any revision must preserve:

* The prior version.
* The reason for the revision.
* The requesting party.
* The review date.
* The independent-validator assessment.
* The approval authority.
* The revised effective date.
* The revised expiration date.

Unapproved deviations may prevent model approval or continued model use.

### 14.10 Charter Review and Amendment

This charter must be reviewed:

* At least annually.
* When the documented research use changes materially.
* When the model scope changes materially.
* When validation responsibilities change.
* When approval responsibilities change.
* When material governance deficiencies are identified.
* When applicable legal, regulatory, or professional expectations change.
* When repeated deviations indicate that the charter is no longer effective.

A charter amendment must:

* Identify the section being changed.
* Preserve the previous version.
* Explain the reason for the change.
* Assess the governance and model-risk impact.
* Receive independent-validator review.
* Receive approval-authority approval.
* State the effective date.
* Update the charter version.
* Remain version-controlled.

A charter amendment must not be used to conceal or retroactively eliminate:

* A prior charter violation.
* A validation finding.
* A failed test.
* A negative result.
* A deviation.
* A monitoring breach.
* A revalidation requirement.

---

## 15. Final Charter Requirement

This charter is binding for the documented research-governance framework of the
`ccp-margin-model-validation` repository.

Any material departure from this charter must be:

* Documented.
* Justified.
* Risk assessed.
* Independently reviewed.
* Approved or rejected by the documented approval authority.
* Preserved as part of the permanent governance record.

Failure to comply with this charter may prevent:

* Approval for the documented research use.
* Continued conditional approval.
* Continued model use.
* Finding closure.
* Completion of revalidation.

The final validation conclusion must reflect not only quantitative model
performance but also:

* Conceptual soundness.
* Implementation integrity.
* Data reliability.
* Reproducibility.
* Validation independence.
* Governance compliance.
* Model limitations.
* Compensating controls.
* Monitoring readiness.
* The totality of available evidence.
