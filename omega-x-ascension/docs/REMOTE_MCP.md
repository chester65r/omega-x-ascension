# Remote MCP integration

Omega-X Ascension can connect to a remote Model Context Protocol (MCP) server over HTTPS Streamable HTTP.

## Configuration

Set these variables in the deployment secret/environment configuration:

```dotenv
OMEGA_REMOTE_MCP_URL=https://wild-cloud-3h9z2.run.mcp-use.com/mcp
OMEGA_REMOTE_MCP_TIMEOUT_SECONDS=20
# Set only if the server requires bearer authentication:
# OMEGA_REMOTE_MCP_TOKEN=replace-with-a-secret
```

Do not commit real credentials. The client rejects non-HTTPS endpoints and does not accept credentials embedded in the URL.

## Authenticated API

All routes below are under `/v1/integrations/mcp` and require the usual signed Omega bearer JWT.

- `GET /status` — initialize the connection and report server metadata.
- `GET /tools` — retrieve the server's advertised tool schemas.
- `POST /tools/call` — invoke one advertised tool. Requires `runs:write` and `runs:approve` scopes.

Example tool invocation:

```http
POST /v1/integrations/mcp/tools/call
Authorization: Bearer <omega-jwt>
Content-Type: application/json

{
  "name": "fetch-weather",
  "arguments": {
    "city": "Jeddah"
  }
}
```

Tool names are validated against the server's current `tools/list` response. Requests are bounded by a configurable timeout, and oversized responses are rejected.

## Use from an agent workflow

To request use of the remote MCP server during a workflow, include `use_remote_mcp` in `requested_actions` when creating the run. This action is approval-gated: the run must be approved through the normal Omega approval flow before the worker executes. The workflow asks the configured model to select at most one relevant read-only tool, applies a basic safety filter, and treats returned tool content as untrusted data. If selection or execution fails, the workflow continues without remote tool output.

The read-only filter is a defense-in-depth heuristic, not a substitute for trusting the server and reviewing each tool's actual implementation. Do not connect untrusted MCP servers to production credentials or expose tool execution to unauthenticated callers.
