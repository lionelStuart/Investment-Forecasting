# ADR-002: Official MCP Python SDK For Transport

## Status

accepted

## Context

`TASK-006` implemented a transport-neutral MCP-compatible tool registry and JSON
CLI. `TASK-011` requires a real MCP transport so AI clients can list and call
tools through standard MCP rather than a project-specific CLI wrapper.

The official Model Context Protocol documentation lists the Python SDK as a
Tier 1 SDK for creating MCP servers, and the SDK provides `FastMCP` plus stdio,
SSE, and streamable HTTP transports.

## Decision

Use the official `mcp` Python SDK for MCP transport. Keep all business logic in
`investment_forecasting.mcp.tools`; the transport layer only adapts those tools
to MCP server calls.

## Consequences

- The project gains a standard stdio MCP server command:
  `investment-forecasting-mcp --db data/investment_forecasting.sqlite3`.
- The same server can later expose SSE or streamable HTTP if needed.
- The dependency adds Pydantic/Starlette/AnyIO transitive dependencies, which is
  acceptable for the integration boundary but should not leak into quant or data
  services.
- MCP SDK version changes may require transport smoke tests to be maintained.

