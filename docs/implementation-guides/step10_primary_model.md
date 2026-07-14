# Step 10 — Primary Historical-Simulation Margin Model

Copy the `src` and `tests` directories into the project root. The implementation:

- Applies historical simple returns to current signed market values.
- Uses directly observed overlapping 1-day, 3-day, and 5-day returns.
- Supports configurable confidence levels and lookback windows.
- Preserves the full scenario P&L and loss distribution.
- Produces security-level attribution at the selected VaR scenario.
- Reports missing histories and supports drop, zero-fill, or error policies.
- Uses deterministic sorting and an observation-based `higher` quantile.
- Provides non-overlapping return construction for independence testing.

Run from the project root:

```powershell
python -m pip install -e .
python -m pytest tests/test_primary_historical_var.py -q
python -m pytest -q
```
