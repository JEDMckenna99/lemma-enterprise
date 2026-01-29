# Lemma MCP Server

MCP (Model Context Protocol) server that enables AI agents to interact with the Lemma.id platform using agent delegation tokens.

## Features

- **View Pages**: Navigate to any Lemma page and get content
- **Screenshots**: Capture screenshots of UI for visual debugging
- **API Calls**: Make authenticated API calls with agent token
- **Console Logs**: Capture JavaScript errors and logs
- **Debug Dashboard**: Test all endpoints at once

## Setup

### 1. Install Dependencies

```bash
cd mcp-server
npm install
```

### 2. Configure Cursor

Add to your Cursor MCP settings (`.cursor/mcp.json` or Cursor settings):

```json
{
  "mcpServers": {
    "lemma": {
      "command": "node",
      "args": ["C:/Users/jedmc/lemma-enterprise/lemma-rebuild/mcp-server/index.js"],
      "env": {
        "LEMMA_AGENT_TOKEN": "lm_agent_YOUR_TOKEN_HERE"
      }
    }
  }
}
```

Or for Windows:

```json
{
  "mcpServers": {
    "lemma": {
      "command": "cmd",
      "args": ["/c", "node", "C:\\Users\\jedmc\\lemma-enterprise\\lemma-rebuild\\mcp-server\\index.js"],
      "env": {
        "LEMMA_AGENT_TOKEN": "lm_agent_YOUR_TOKEN_HERE"
      }
    }
  }
}
```

### 3. Get Your Agent Token

1. Go to https://lemma.id/developer
2. Generate an agent token with admin scope
3. Copy the token and paste in the config above

## Available Tools

### `lemma_view_page`
Navigate to a page and get its content.
```
path: "/admin" | "/developer" | "/admin/debug" | etc.
```

### `lemma_screenshot`
Take a screenshot of a page.
```
path: "/admin"
```

### `lemma_api_call`
Call any API endpoint with authentication.
```
endpoint: "/api/admin/sites"
method: "GET" | "POST" | etc.
body: {} (optional)
```

### `lemma_debug_dashboard`
Test all admin API endpoints at once.

### `lemma_check_auth`
Verify agent token is valid.

### `lemma_get_console_logs`
Get JavaScript console output from a page.

## Available Resources

- `lemma://admin/dashboard` - Platform stats
- `lemma://admin/sites` - Registered sites
- `lemma://admin/customers` - Customer accounts
- `lemma://health` - Platform health

## Usage Example

Once configured, the AI can:

```
"Check if the admin dashboard is showing the correct data"
-> Uses lemma_view_page to navigate and lemma_api_call to verify

"Take a screenshot of the sites page"
-> Uses lemma_screenshot

"Debug why the user stats aren't loading"
-> Uses lemma_get_console_logs and lemma_api_call
```

## Security

- Agent tokens are time-limited (max 24h)
- Tokens are scoped (read/write/admin)
- All actions are audited
- You can revoke tokens instantly from the developer dashboard
