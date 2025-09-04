# Freshrelease MCP Server
[![smithery badge](https://smithery.ai/badge/@dasscoax/freshrelease_mcp)](https://smithery.ai/server/@dasscoax/freshrelease_mcp)

An MCP server implementation that integrates with Freshrelease, enabling AI models to interact with Freshrelease projects and tasks.

## Features

- **Freshrelease Integration**: Seamless interaction with Freshrelease API endpoints
- **AI Model Support**: Enables AI models to perform project/task operations through Freshrelease
- **Automated Project Management**: Handle project and task creation and retrieval

## Components

### Tools

The server offers several tools for Freshrelease operations:

- `fr_create_project`: Create a project
  - Inputs: `name` (string, required), `description` (string, optional)

- `fr_get_project`: Get a project by ID or key
  - Inputs: `project_identifier` (number|string, required)

- `fr_create_task`: Create a task under a project
  - Inputs: `project_identifier` (number|string, required), `title` (string, required), `description` (string, optional), `assignee_id` (number, optional), `status` (string, optional), `due_date` (YYYY-MM-DD, optional)

- `fr_get_task`: Get a task by ID
  - Inputs: `task_id` (number, required)

- `fr_list_status_categories`: List status categories (key→id and name→id)
  - Inputs: None

- `fr_get_status_category_id`: Resolve status key to id
  - Inputs: `key` (todo | in_progress | done)

- `fr_get_status_category_id_from_name`: Resolve human name to id
  - Inputs: `name` (Yet To Start | Work In Progress | Completed)

- `fr_list_status_category_names`: List human-readable status names
  - Inputs: None

## Getting Started

### Installing via Smithery

If distributed via Smithery, install for Claude Desktop (example):

```bash
npx -y @smithery/cli install @dasscoax/freshrelease_mcp --client claude
```

### Installing from PyPI

Install the published package directly from PyPI:

```bash
pip install -U freshrelease-mcp
```

Verify installation:

```bash
freshrelease-mcp --help
```

Run the server locally with environment variables:

```bash
FRESHRELEASE_API_KEY="<YOUR_FRESHRELEASE_API_KEY>" \
FRESHRELEASE_DOMAIN="<YOUR_FRESHRELEASE_DOMAIN>" \
freshrelease-mcp
```

### Prerequisites

- Freshrelease API access (domain + API key)
- Freshrelease API key
- `uvx` installed (`pip install uv` or `brew install uv`)

### Configuration

1. Obtain your Freshrelease API key
2. Set up your Freshrelease domain and authentication details

### Usage with Claude Desktop

1. Install Claude Desktop if you haven't already
2. Recommended: Use `uvx` to fetch and run from PyPI (no install needed). Add the following to your `claude_desktop_config.json`:


```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uvx",
      "args": [
        "freshrelease-mcp"
      ],
      "env": {
        "FRESHRELEASE_API_KEY": "<YOUR_FRESHRELEASE_API_KEY>",
        "FRESHRELEASE_DOMAIN": "<YOUR_FRESHRELEASE_DOMAIN>"
      }
    }
  }
}
```

**Important Notes**:
- Replace `<YOUR_FRESHRELEASE_API_KEY>` with your Freshrelease API key
- Replace `<YOUR_FRESHRELEASE_DOMAIN>` with your Freshrelease domain (e.g., `yourcompany.freshrelease.com`)
 - Alternatively, you can install the package and point `command` directly to `freshrelease-mcp`.

### Usage with Cursor

1. Add the following to Cursor settings JSON (Settings → Features → MCP → Edit JSON):

```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uvx",
      "args": [
        "freshrelease-mcp"
      ],
      "env": {
        "FRESHRELEASE_API_KEY": "<YOUR_FRESHRELEASE_API_KEY>",
        "FRESHRELEASE_DOMAIN": "<YOUR_FRESHRELEASE_DOMAIN>"
      }
    }
  }
}
```

### Usage with VS Code (Claude extension)

1. In VS Code settings (JSON), add:

```json
{
  "claude.mcpServers": {
    "freshrelease-mcp": {
      "command": "uvx",
      "args": [
        "freshrelease-mcp"
      ],
      "env": {
        "FRESHRELEASE_API_KEY": "<YOUR_FRESHRELEASE_API_KEY>",
        "FRESHRELEASE_DOMAIN": "<YOUR_FRESHRELEASE_DOMAIN>"
      }
    }
  }
}
```

## Example Operations

Once configured, you can ask Claude to perform operations like:

- "Create a Freshrelease project named 'Roadmap Q4'"
- "Get project 'ENG' details"
- "Create a task 'Add CI pipeline' under project 'ENG'"
- "What is the id for status category 'Yet To Start'?"


## Testing

For testing purposes, you can start the server manually:

```bash
uvx freshrelease-mcp --env FRESHRELEASE_API_KEY=<your_api_key> --env FRESHRELEASE_DOMAIN=<your_domain>
```

## Troubleshooting

- Verify your Freshrelease API key and domain are correct
- Ensure proper network connectivity to Freshrelease servers
- Check API rate limits and quotas
- Verify the `uvx` command is available in your PATH

## License

This MCP server is licensed under the MIT License. See the LICENSE file in the project repository for full details.
