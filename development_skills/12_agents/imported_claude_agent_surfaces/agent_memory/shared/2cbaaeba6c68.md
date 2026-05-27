# OPS Dash Lineage Memory

Use this for future OPS Dash troubleshooting and refresh validation.

## Final TD Report
- Final file: `OPS Dash/TD Report_February 2026_2.xlsx` (supersedes `TD Report_February 2026.xlsx`).

## Critical Cell Mappings
- `Call Center Daily Tracker 2026.xlsx` row 59 (daily values across columns):
  - `B59` -> `TD Report_February 2026_2.xlsx` `Monthly Data` `B36`.
- `007-QueueGroupPerformancebyQueue-YYYYMMDDHHMMSS.xls`:
  - `O13` -> `Monthly Data` `B34`.
  - `T13` -> `Monthly Data` `B35`.
- `OTPA_-_LD_SUMMARY_BY_DAY_(MV_DAILY).csv`:
  - Column `E` (Early Trips) from `E2` -> `Monthly Data` `B43` (row 43 forward).
  - `Monthly Data` `B30` contains a formula and must remain intact.
- `Trend_Count_Runs_by_Provider_by_Day_(Current_Month).csv`:
  - Column `B` (`total`) from `B2` -> `Monthly Data` rows `92`, `104`, `106`.
  - Column `E` (`cnt_vehs`) from `E2` -> `Monthly Data` row `108`.
- `VTA Access Down List - February 2026.xlsx`:
  - `D12` -> `Monthly Data` row `107`.

## VTA Schedule Workup
- `VTA Sch Workup v8 20260220.xlsm`:
  - Tabs: `Daily Stats`, `Negotiation`, `Sched_Stats`, `Sched_Trips`, `Unsched_trips`, `RunCut Info`.
  - `Daily Stats` is populated by running the workbook scripts and then copy/paste from the query outputs.
  - `PROVIDER_ALL_TRIPS.csv` -> `Sched_Trips` tab.
  - `UNSCHED_TRIPINFO.csv` -> `Unsched_trips` tab.

## SDB Ops Output
- `serious-disruptive-dashboard/client/scripts/sync-ops-dash.js` generates `client/public/data/ops/ops-dash.json` for OPS tabs.
