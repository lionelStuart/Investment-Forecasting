---
name: investment-market-data-skill
description: Read-only market data access for Investment Forecasting agents.
---

# Investment Market Data Skill

Use only system-provided read APIs/MCP tools for assets, prices, market
snapshots, macro observations, and capital-flow observations. Do not query
SQLite directly and do not scrape the WebUI.

When making a market claim, cite the evidence identifier or explain that the
claim is an assumption. Treat missing, stale, or insufficient history as a risk
condition rather than filling gaps from memory.
