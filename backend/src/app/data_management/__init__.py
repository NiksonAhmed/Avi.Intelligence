"""Data Management module (Viedoc EDC): queries, missing data and, later, labs and deviations.

Self-contained by design (docs/decisions.md, 2026-11-11): it may use the shared foundations (auth and
roles, audit, database session, settings), but nothing outside it imports from it except the app's
wiring in `app/main.py`. Its tables are prefixed `dm_`. Read-only towards Viedoc.
"""
