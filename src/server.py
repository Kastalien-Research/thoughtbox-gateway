"""MCP server — Thoughtbox gateway for the Dedalus Marketplace."""

import json
import os

import httpx
from dedalus_mcp import MCPServer, tool
from dedalus_mcp.server import TransportSecuritySettings

MARKETPLACE_URL = "https://www.dedaluslabs.ai/api/marketplace"
DEDALUS_API_URL = "https://api.dedaluslabs.ai/v1/chat/completions"
TOOL_EXEC_MODEL = "anthropic/claude-haiku-4-5-20251001"


@tool(
    description=(
        "Search the live Dedalus Marketplace tool catalog. "
        "Pass a query string to filter by name or description. "
        "Returns available upstream servers and their tool counts."
    ),
)
async def thoughtbox_search(query: str = "") -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(MARKETPLACE_URL)
        resp.raise_for_status()
        data = resp.json()

    results = []
    q = query.lower()
    for server in data.get("repositories", []):
        name = server.get("title") or server.get("slug", "")
        desc = server.get("description") or server.get("subtitle") or ""
        if q in name.lower() or q in desc.lower() or not q:
            results.append({
                "upstreamId": f"dedalus:{server['slug']}",
                "name": name,
                "description": desc,
                "toolCount": server.get("tool_count", 0),
            })
    return json.dumps(results, indent=2)


@tool(
    description=(
        "Call a Marketplace tool by upstream ID and tool name. "
        "Use thoughtbox_search first to find the upstreamId. "
        "Routes through Dedalus chat completions with mcp_servers."
    ),
)
async def thoughtbox_execute(
    upstream_id: str,
    tool_name: str,
    arguments: str = "{}",
) -> str:
    api_key = os.environ.get("DEDALUS_API_KEY", "")
    if not api_key:
        return "Error: DEDALUS_API_KEY not set"

    slug = upstream_id.removeprefix("dedalus:")
    prompt = (
        f'Call the tool "{tool_name}" with arguments: {arguments}. '
        f"Return only the tool result."
    )
    body = {
        "model": TOOL_EXEC_MODEL,
        "mcp_servers": [slug],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            DEDALUS_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=body,
        )
        resp.raise_for_status()
    return resp.json()["choices"][0]["message"].get("content", "")


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
