# Lemma MCP Server

MCP (Model Context Protocol) server that enables AI agents to **fully interact** with the Lemma.id platform using agent delegation tokens. This goes beyond observation - agents can click, type, fill forms, and run automated UI tests.

## Features

### Observation Tools
- **View Pages**: Navigate to any Lemma page and get content
- **Screenshots**: Capture screenshots of UI for visual debugging
- **API Calls**: Make authenticated API calls with agent token
- **Console Logs**: Capture JavaScript errors and logs
- **Debug Dashboard**: Test all endpoints at once

### Interaction Tools
- **Click**: Click buttons, links, and interactive elements
- **Type**: Enter text into input fields
- **Select**: Choose options from dropdowns
- **Checkbox**: Toggle checkbox states
- **Fill Forms**: Fill multiple fields and submit forms
- **Wait For**: Wait for elements to appear

### Workflow Testing
- **Site Registration**: Automated test of full registration flow
- **API Key Generation**: Test key generation workflow
- **Agent Token Flow**: Test agent token creation
- **UI Test Suites**: Run comprehensive automated tests

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
      "args": ["<PATH_TO_REPO>/mcp-server/index.js"],
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
      "args": ["/c", "node", "<PATH_TO_REPO>\\mcp-server\\index.js"],
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

### Observation Tools

#### `lemma_view_page`
Navigate to a page and get its content.
```
path: "/admin" | "/developer" | "/admin/debug" | etc.
```

#### `lemma_screenshot`
Take a screenshot of a page.
```
path: "/admin"
```

#### `lemma_api_call`
Call any API endpoint with authentication.
```
endpoint: "/api/admin/sites"
method: "GET" | "POST" | etc.
body: {} (optional)
```

#### `lemma_debug_dashboard`
Test all admin API endpoints at once.

#### `lemma_check_auth`
Verify agent token is valid.

#### `lemma_get_console_logs`
Get JavaScript console output from a page.

### Interaction Tools

#### `lemma_click`
Click on an element by CSS selector or text content.
```
selector: "#submit-btn" | ".btn-primary" | "[data-action=generate-token]"
text: "Generate Token" | "Submit" (alternative to selector)
waitAfter: 1000 (ms to wait after click)
```

#### `lemma_type`
Type text into an input field.
```
selector: "#email-input"
text: "test@example.com"
clear: true (clear field first)
```

#### `lemma_select`
Select an option from a dropdown.
```
selector: "#ttl-select"
value: "8"
```

#### `lemma_checkbox`
Check or uncheck a checkbox.
```
selector: "#remember-me"
checked: true
```

#### `lemma_get_elements`
Discover elements on the page (useful for understanding structure).
```
selector: "button" | "input" | "[data-action]"
path: "/developer" (optional, navigate first)
```

#### `lemma_wait_for`
Wait for an element to appear.
```
selector: ".loading-complete"
timeout: 10000 (max ms to wait)
visible: true (wait for visibility)
```

#### `lemma_fill_form`
Fill multiple form fields at once.
```
fields: {
  "#email": "test@example.com",
  "#name": "Test User",
  "#company": "Acme Inc"
}
submit: true (click submit after filling)
submitSelector: "button[type=submit]"
```

### Workflow Testing Tools

#### `lemma_test_site_registration`
Test the complete site registration flow.
```
siteDomain: "test.example.com"
companyName: "Test Company"
```

#### `lemma_test_api_key_generation`
Test generating an API key for a site.
```
siteId: "site_abc123"
```

#### `lemma_test_agent_token_flow`
Test the agent token generation workflow.
```
scope: ["read", "write", "admin"]
ttlHours: 8
```

#### `lemma_run_ui_test`
Run a predefined UI test suite.
```
suite: "admin_dashboard" | "developer_dashboard" | "site_management" | "agent_tokens" | "all"
```

## Available Resources

- `lemma://admin/dashboard` - Platform stats
- `lemma://admin/sites` - Registered sites
- `lemma://admin/customers` - Customer accounts
- `lemma://health` - Platform health

## Usage Examples

Once configured, the AI can:

### Test Button Functionality
```
"Click all the buttons on the developer dashboard and verify they work"
-> Uses lemma_get_elements to find buttons
-> Uses lemma_click to test each one
-> Verifies expected behavior
```

### Fill and Submit Forms
```
"Register a new test site called myapp.example.com"
-> Uses lemma_test_site_registration or manual:
-> lemma_view_page to navigate
-> lemma_fill_form to enter data
-> lemma_click to submit
```

### Run Full UI Tests
```
"Run the full UI test suite for the admin dashboard"
-> Uses lemma_run_ui_test with suite: "admin_dashboard"
-> Returns pass/fail for each test
```

### Debug Issues
```
"Debug why the user stats aren't loading"
-> Uses lemma_get_console_logs to check for JS errors
-> Uses lemma_api_call to verify API responses
-> Uses lemma_screenshot for visual state
```

### Verify Deployments
```
"Test all the features I just deployed"
-> Uses lemma_run_ui_test with suite: "all"
-> Reports which tests pass and fail
```

## Security

- Agent tokens are time-limited (max 24h)
- Tokens are scoped (read/write/admin)
- All actions are audited
- You can revoke tokens instantly from the developer dashboard
- Browser session is isolated (headless Chromium)

## Troubleshooting

### Token Not Working
1. Verify token hasn't expired
2. Check token has admin scope
3. Use `lemma_check_auth` to validate

### Element Not Found
1. Use `lemma_get_elements` to discover available elements
2. Check if page requires authentication
3. Verify selector syntax

### Tests Failing
1. Check console logs with `lemma_get_console_logs`
2. Take screenshot with `lemma_screenshot`
3. Verify API responses with `lemma_api_call`
