# Federal Reserve H.10 reference-data provenance

The H.10 daily bilateral exchange-rate series is reference data, not executable bid/ask data. The Federal Reserve states that H.10 is generally released Monday at 4:15 p.m. ET and covers the previous business week; the historical page also states that data are available through Friday of the previous business week.

For point-in-time research, the value date (`event_time`) must not be treated as the availability time (`usable_at`). A historical replay should assign `usable_at` to the actual H.10 release timestamp for the corresponding release, including daylight-saving changes. Do not use the current wall-clock time to backfill availability metadata.

The repository adapter therefore accepts an explicit `usable_at` for reproducible historical ingestion. Its default current-time behavior is intended only for live ingestion of newly retrieved reference data, not for retrospective backtesting.

H.10 observations remain `execution_grade=false`; they must not be used as a substitute for executable dealer/venue quotes.
