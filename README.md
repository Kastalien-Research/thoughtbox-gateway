# Thoughtbox Gateway

Code-mode-first MCP gateway for the Dedalus Marketplace.

## What it does

Two tools:

- **`thoughtbox_search`** — Query the Dedalus Marketplace catalog. Returns available servers and their tool counts.
- **`thoughtbox_execute`** — Call a Marketplace tool by upstream ID and tool name. Routes through Dedalus chat completions with `mcp_servers`.

Workflow: search to discover available tools, then execute to call them.

## Setup

```bash
export DEDALUS_API_KEY="your-key"
```

## Run locally

```bash
uv run src/main.py
```

Server starts on `http://127.0.0.1:8080/mcp`.

## Deploy

Point the Dedalus dashboard at this repo. It handles the rest.
