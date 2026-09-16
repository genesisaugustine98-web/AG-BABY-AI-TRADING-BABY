# Render Control Plane

Render hosts the lightweight operational surface for the AG BABY repository.

## Service

- Service: `ag-baby-control-plane`
- Runtime: Python
- Plan: Free
- Region: Frankfurt
- Source: `main` of `genesisaugustine98-web/AG-BABY-AI-TRADING-BABY`
- URL: `https://ag-baby-control-plane.onrender.com`
- Health endpoint: `/health`

## Boundary

This service is deliberately not the trading engine and has no broker credentials. It only exposes repository/control-plane health information. Heavy research workloads and broker execution remain separate systems.

`EXECUTION_ENV` defaults to `research` and is set to `research` in Render.

Live trading remains disabled by architecture in the repository.
