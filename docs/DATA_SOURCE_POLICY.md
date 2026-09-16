# AG BABY Data Source Policy

## Purpose

The research system must distinguish data that is useful for historical/structural research from data that can support execution decisions.

## Tier 1 — executable-market observations

Use timestamped bid/ask quotes, trades, depth, venue status, and broker/venue acknowledgements when testing execution-sensitive hypotheses. Every record must carry event time, availability time, source, source version, and a stable observation identifier.

These observations are the only class suitable for claims about spread, fill quality, slippage, latency, and execution behavior.

## Tier 2 — official reference rates

Official central-bank reference series are appropriate for lower-frequency research, sanity checks, macro relationships, and cross-source reconciliation. The Federal Reserve H.10 program currently publishes daily foreign-exchange rates and provides downloadable packages; its data-download page also records historical corrections. Do not treat these daily reference observations as executable quotes. See: https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H10

## Tier 3 — market-structure evidence

BIS Triennial Survey and related BIS research provide authoritative structural evidence on OTC FX market size, composition, dealer intermediation and fragmentation. BIS reports that the 2025 survey covered 52 jurisdictions and more than 1,100 banks/dealers; the final survey results were released in 2026. Use these sources for market-structure priors and falsification context, not as a substitute for timestamped trade/quote data.

## Required provenance

Every ingested observation must preserve:

- source name and endpoint/file identity;
- retrieval timestamp;
- source version or release/vintage;
- event timestamp and earliest usable timestamp;
- transformation code/version;
- quality status and rejection reasons;
- raw artifact checksum where practical.

## Research rule

A strategy result is not promoted because it works on an official daily reference series. Promotion requires a separately validated data path appropriate to the execution horizon. Any degradation from executable data to reference data must be explicit in the experiment record.
