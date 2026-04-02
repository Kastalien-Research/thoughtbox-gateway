"""Thoughtbox — code-mode MCP gateway for the Dedalus Marketplace."""

import json
import os

import httpx
from dedalus_mcp import MCPServer, tool
from dedalus_mcp.server import TransportSecuritySettings

MARKETPLACE_URL = "https://www.dedaluslabs.ai/api/marketplace"


async def fetch_catalog() -> list[dict]:
    """Fetch the Marketplace catalog."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(MARKETPLACE_URL)
        resp.raise_for_status()
        data = resp.json()
    servers = []
    for s in data.get("repositories", []):
        servers.append({
            "upstreamId": f"dedalus:{s['slug']}",
            "name": s.get("title") or s.get("slug", ""),
            "description": s.get("description") or s.get("subtitle") or "",
            "toolCount": s.get("tool_count", 0),
        })
    return servers


@tool(
    description=(
        "Search the Dedalus Marketplace catalog by writing JavaScript "
        "that queries the `catalog` array.\n\n"
        "Each entry: { upstreamId, name, description, toolCount }\n\n"
        "Examples:\n"
        "- List all: `async () => catalog`\n"
        "- Filter: `async () => catalog.filter(s => s.name.includes('search'))`\n"
        "- Count: `async () => catalog.length`"
    ),
)
async def thoughtbox_search(code: str) -> str:
    catalog = await fetch_catalog()
    loc = {"catalog": catalog, "result": None}
    fn_code = f"import asyncio\nasync def _run():\n    fn = {code}\n    return await fn() if asyncio.iscoroutinefunction(fn) else fn()\nresult = asyncio.get_event_loop().run_until_complete(_run())"
    try:
        exec(fn_code, {"catalog": catalog, "asyncio": __import__("asyncio")}, loc)  # noqa: S102
    except Exception as e:
        return json.dumps({"error": str(e)})
    return json.dumps(loc.get("result", catalog), indent=2, default=str)


@tool(
    description=(
        "Execute JavaScript using the `tb` SDK to call proxied "
        "Marketplace tools.\n\n"
        "Available:\n"
        "- `tb.gateway.listUpstreams()` — list upstream servers\n"
        "- `tb.gateway.listTools(upstreamId?)` — list tools\n"
        "- `tb.gateway.call({ upstreamId, toolName, arguments? })` "
        "— call a tool\n\n"
        "Example:\n```js\nasync () => {\n"
        "  const tools = await tb.gateway.listTools();\n"
        "  return await tb.gateway.call({\n"
        "    upstreamId: tools[0].upstreamId,\n"
        "    toolName: tools[0].name,\n"
        "  });\n}\n```"
    ),
)
async def thoughtbox_execute(code: str) -> str:
    api_key = os.environ.get("DEDALUS_API_KEY", "")
    if not api_key:
        return json.dumps({"error": "DEDALUS_API_KEY not set"})

    catalog = await fetch_catalog()

    async def list_upstreams():
        return catalog

    async def list_tools(upstream_id=None):
        # TODO: fetch actual tool lists from upstream servers
        if upstream_id:
            return [s for s in catalog if s["upstreamId"] == upstream_id]
        return catalog

    async def call_tool(*, upstreamId, toolName, arguments=None):
        slug = upstreamId.removeprefix("dedalus:")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://mcp.dedaluslabs.ai/{slug}/mcp",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": toolName,
                        "arguments": arguments or {},
                    },
                    "id": 1,
                },
            )
            resp.raise_for_status()
        return resp.json().get("result", resp.json())

    tb = type("TB", (), {
        "gateway": type("Gateway", (), {
            "listUpstreams": staticmethod(list_upstreams),
            "listTools": staticmethod(list_tools),
            "call": staticmethod(call_tool),
        })(),
    })()

    logs = []
    console = type("Console", (), {
        "log": staticmethod(lambda *a: logs.append(" ".join(str(x) for x in a))),
    })()

    import asyncio

    async def run_code():
        fn_src = f"fn = {code}"
        loc = {}
        exec(fn_src, {"tb": tb, "console": console}, loc)  # noqa: S102
        fn = loc["fn"]
        if asyncio.iscoroutinefunction(fn):
            return await fn()
        return fn()

    try:
        result = await run_code()
    except Exception as e:
        return json.dumps({"error": str(e), "logs": logs})
    return json.dumps({"result": result, "logs": logs}, indent=2, default=str)


def create_server() -> MCPServer:
    """Create the Thoughtbox MCP server."""
    return MCPServer(
        name="thoughtbox",
        http_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        ),
        streamable_http_stateless=True,
    )


async def main() -> None:
    """Start the server."""
    server = create_server()
    server.collect(thoughtbox_search, thoughtbox_execute)
    await server.serve(port=8080)
