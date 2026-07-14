STEP 18 — DUCKDB SQL PIPELINE

Copy the contents of this bundle into the project root so that sql, scripts,
and tests merge with the existing project directories. Do not create a nested
step18_bundle directory inside the project.

Project root:
C:\Users\nejat\OneDrive\Desktop\UN\Skills\GitHub 2026\ccp-margin-model-validation

From the VS Code PowerShell terminal, run:

Set-ExecutionPolicy -Scope Process Bypass
.\STEP18_RUN.ps1

Expected final result:
- data\database\ccp_margin_validation.duckdb
- reports\sql\load_manifest.csv
- reports\sql\member_exception_summary.csv
- ten required physical tables
- ten reusable SQL views
- pytest reports 3 passed

Review reports\sql\load_manifest.csv. A status of NO_SOURCE_FOUND means the
SQL infrastructure is correct, but the loader could not locate the source CSV
or Parquet file for that table. Rename the source to a descriptive name or add
its filename stem to SOURCE_HINTS in scripts\18_build_duckdb.py, then rerun.
