# Model Scope and Assumptions

## 1. Document Purpose

This document defines the scope, assumptions, exclusions, and known
limitations of the CCP Margin Model Independent Validation Framework.

The repository is an independent research and model-validation project. It
does not represent a production clearinghouse system, a regulatory filing, or
the methodology of any specific central counterparty.

All clearing members, positions, portfolios, and margin requirements used in
the project are simulated unless a dataset is explicitly identified as public
market data.

## 2. Product Scope

The framework covers initial-margin estimation and independent validation for
simulated portfolios of liquid, linear financial instruments.

The initial implementation includes:

- Historical-simulation Value at Risk.
- Parametric Value at Risk.
- One-day and multi-day margin periods of risk.
- Volatility adjustments.
- Liquidity add-ons.
- Concentration add-ons.
- Gap-risk and stress add-ons.
- Benchmark and challenger margin models.
- Backtesting and exception analysis.
- Margin shortfall analysis.
- Sensitivity and stability testing.
- Stress-period analysis.
- Procyclicality measurement.

The initial implementation does not constitute a complete production CCP
margin methodology.

## 3. Market Universe

The initial market universe consists of publicly observable United States
market instruments and liquid proxies, including:

- Large-capitalization U.S. equities.
- Broad-market equity exchange-traded funds.
- U.S. Treasury securities or Treasury ETF proxies.
- Investment-grade fixed-income ETF proxies.
- High-yield fixed-income ETF proxies, where explicitly configured.

Only instruments with sufficient price history and acceptable data quality
are eligible for model estimation.

The market universe must be defined in version-controlled configuration files.
Any addition or removal of instruments must be documented in the applicable
data manifest and validation evidence.

## 4. Clearing-Member Assumptions

Clearing members are synthetic entities created for research and validation.

The following assumptions apply:

- No clearing-member name represents an actual financial institution.
- Each member has one or more simulated portfolios.
- Portfolios may contain long and short positions.
- Positions are assumed to be legally enforceable and operationally valid.
- Netting is allowed only where explicitly defined by the portfolio and model
  configuration.
- Member default probabilities are outside the initial model scope.
- Wrong-way risk is excluded unless introduced as a separate stress scenario.
- Member-specific credit quality is not used to reduce initial margin.
- No member receives a discretionary model override unless the override is
  recorded, justified, and separately validated.

## 5. Position and Portfolio Assumptions

The initial implementation assumes:

- End-of-day positions.
- End-of-day market prices.
- Linear cash-equivalent exposures.
- Positions expressed as quantities, market values, or defined risk weights.
- Portfolio values calculated consistently in the base currency.
- Long and short positions are permitted.
- Fractional positions may be used in synthetic portfolios.
- Portfolio composition remains unchanged between explicitly scheduled
  rebalancing dates.
- No intraday trading or intraday margin call process is modeled.
- No options, embedded optionality, nonlinear derivatives, or path-dependent
  products are included in the initial scope.
- No undocumented position is silently excluded from the calculation.

Invalid, missing, or unmapped positions must generate a data-quality exception
rather than being assigned a zero exposure.

## 6. Base Currency

The base currency is the United States dollar, USD.

The initial market universe is expected to contain USD-denominated
instruments. Foreign-exchange risk is excluded unless explicitly introduced
through a future model extension.

Any non-USD position must either:

1. Be converted using an approved and documented foreign-exchange rate; or
2. Be rejected as outside the configured model scope.

## 7. Confidence Level

The primary initial-margin confidence level is:

- 99 percent, one-tailed.

Alternative confidence levels may be used for sensitivity analysis, including:

- 97.5 percent.
- 99.5 percent.
- 99.9 percent.

A sensitivity result does not automatically replace the approved primary
parameter.

Any change to the primary confidence level must be documented as a model
change and independently validated.

## 8. Margin Periods of Risk

The primary configured margin periods of risk are:

- One trading day.
- Five trading days.

Additional periods may be evaluated for sensitivity or stress testing,
including two-day and ten-day periods.

Multi-day returns must be calculated using a documented methodology. The
implementation must identify whether returns are overlapping or
non-overlapping and must preserve that choice in configuration and evidence.

Square-root-of-time scaling may be used only in models where its assumptions
are documented and tested. Historical multi-day returns should be used as an
independent benchmark where sufficient observations exist.

## 9. Data Start and End Dates

The default research data start date is:

- January 1, 2010.

The data end date is:

- The latest successfully retrieved and validated market date available at the
  time the dataset is created.

The exact start date, end date, extraction timestamp, source, instrument count,
row count, and file checksum must be recorded in a versioned data manifest.

A model run must not silently extend or shorten the estimation period.

Alternative periods may be used for:

- Stressed-period analysis.
- Benchmark analysis.
- Parameter sensitivity analysis.
- Data-availability testing.

Any alternative period must be identified in the run configuration and
validation evidence.

## 10. Rebalancing Assumptions

The initial framework supports:

- Static synthetic portfolios.
- Explicitly scheduled portfolio rebalancing.
- Daily end-of-day valuation.

A portfolio is not assumed to rebalance merely because market values change.

Where scheduled rebalancing is used:

- The rebalancing date must be recorded.
- The pre-rebalancing and post-rebalancing positions must be retained.
- The model must not use future position information in an earlier margin
  calculation.
- Backtesting must use the portfolio known as of the relevant calculation
  date.

## 11. Treatment of Missing Prices

Missing prices must not be replaced with zero.

The following controls apply:

1. Missing observations are identified during data validation.
2. A missing current valuation price causes the position or portfolio to be
   flagged.
3. Forward-filling may be used only for valuation continuity when explicitly
   configured and documented.
4. A forward-filled valuation must not be treated as a genuine zero return for
   VaR estimation without justification.
5. Long gaps must cause the instrument to be excluded or escalated as a
   data-quality finding.
6. No backward-filling from future observations is permitted.
7. The selected treatment must be reproducible and included in the data
   manifest.

Thresholds for acceptable missingness must be defined in configuration rather
than embedded as undocumented code constants.

## 12. Treatment of Corporate Actions

For equities and exchange-traded funds, adjusted prices should be used when
available and appropriate.

The data process must account for:

- Stock splits.
- Reverse stock splits.
- Ordinary distributions.
- Special distributions.
- Symbol changes.
- Delistings.
- Mergers and other material corporate actions.

Large returns potentially caused by corporate actions must be investigated
before being retained as genuine market shocks.

Corporate-action adjustments must not remove legitimate economic losses from
the return series.

Raw and adjusted price fields should be retained where practical to support
independent comparison.

## 13. Treatment of Non-Trading Days

Margin calculations use valid market trading dates.

The following rules apply:

- Weekends are not treated as trading observations.
- Exchange holidays are not assigned fabricated prices or returns.
- Instrument calendars must be aligned using a documented rule.
- A return is calculated only between valid consecutive observations for that
  instrument.
- Calendar alignment must not introduce future information.
- Multi-day margin-period calculations must distinguish trading days from
  calendar days.

Where instruments have different trading calendars, the selected alignment
method must be documented and independently tested.

## 14. Excluded Risks

The initial framework excludes or materially simplifies the following risks:

- Counterparty credit risk outside the margin model.
- Default-fund sizing.
- Recovery and resolution processes.
- Intraday margin and intraday liquidity risk.
- Settlement risk.
- Collateral eligibility and collateral haircut models.
- Collateral concentration risk.
- Foreign-exchange risk unless explicitly configured.
- Nonlinear options and derivatives risk.
- Volatility-surface and implied-volatility risk.
- Basis risk not represented by available market prices.
- Full wrong-way-risk modeling.
- Legal and documentation risk.
- Operational risk.
- Cybersecurity risk.
- Climate-related financial risk.
- Clearing-member default probability estimation.
- Joint member-default scenarios.
- Fire-sale market impact beyond configured liquidity or concentration
  add-ons.
- Production infrastructure resilience and high-availability requirements.

An excluded risk must not be described as captured merely because a general
stress add-on is present.

## 15. Known Limitations

Known limitations include:

- Public market data may contain revisions, missing observations, or vendor
  methodology changes.
- Synthetic portfolios may not reproduce the full complexity of actual
  clearing-member portfolios.
- Historical simulation assumes that the selected historical window is
  representative of relevant future risks.
- Parametric models depend on distributional and dependence assumptions.
- Correlations may change materially during stress.
- Liquidity and concentration add-ons are simplified approximations unless
  calibrated to independently justified data.
- Limited historical data may weaken tail estimation.
- Overlapping multi-day returns introduce dependence between observations.
- Exchange-traded funds are imperfect proxies for direct fixed-income
  instruments.
- End-of-day data do not capture intraday price and liquidity movements.
- Backtesting power is limited when exceptions are rare.
- Passing a statistical backtest does not prove that the model is correct.
- Failing a test does not automatically prove that the model is unusable; the
  cause, materiality, and remediation must be assessed.
- Model risk remains even after independent validation.

## 16. Configuration and Change Control

Material assumptions and parameters must be stored in version-controlled
configuration files.

At minimum, configuration must identify:

- Market universe.
- Base currency.
- Confidence level.
- Margin period of risk.
- Estimation-window length.
- Return methodology.
- Missing-data rules.
- Corporate-action treatment.
- Volatility methodology.
- Liquidity methodology.
- Concentration methodology.
- Stress scenarios.
- Backtesting thresholds.

Changes must be:

1. Recorded in Git.
2. Supported by a clear rationale.
3. Tested.
4. Independently validated when material.
5. Reflected in applicable documentation and evidence.

## 17. Interpretation

The framework is intended to demonstrate reproducible model development,
independent validation, model-risk identification, and governance discipline.

Results must be interpreted as research evidence, not as regulatory approval
or authorization for production use.
