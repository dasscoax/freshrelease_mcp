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
  - Inputs: `project_identifier` (number|string, required), `title` (string, required), `description` (string, optional), `assignee_id` (number, optional), `status` (string|enum, optional), `due_date` (YYYY-MM-DD, optional), `issue_type_name` (string, optional, defaults to "task"), `user` (string email or name, optional), `additional_fields` (object, optional)
  - Notes: `user` resolves to `assignee_id` via users search if `assignee_id` not provided. `issue_type_name` resolves to `issue_type_id`. `additional_fields` allows passing arbitrary extra fields supported by your Freshrelease account. Core fields (`title`, `description`, `assignee_id`, `status`, `due_date`, `issue_type_id`) cannot be overridden.

- `fr_get_task`: Get a task by key or ID within a project
  - Inputs: `project_identifier` (number|string, required), `key` (number|string, required)

- `fr_get_all_tasks`: List issues for a project
  - Inputs: `project_identifier` (number|string, required)

- `fr_get_issue_type_by_name`: Resolve an issue type object by name
  - Inputs: `project_identifier` (number|string, required), `issue_type_name` (string, required)

- `fr_search_users`: Search users by name or email within a project
  - Inputs: `project_identifier` (number|string, required), `search_text` (string, required)

- `fr_link_testcase_issues`: Bulk link issues to one or more testcases (using keys)
  - Inputs: `project_identifier` (number|string, required), `testcase_keys` (array of string|number), `issue_keys` (array of string|number)

## MCP Tool Reference

<style>
.tool-table { width: 100%; border-collapse: collapse; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; }
.tool-table thead th { background: #0f172a; color: #fff; padding: 12px 10px; text-align: left; font-weight: 600; letter-spacing: 0.2px; }
.tool-table tbody td { border-top: 1px solid #e5e7eb; vertical-align: top; padding: 12px 10px; }
.tool-table tbody tr:nth-child(odd) { background: #f8fafc; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 12px; line-height: 18px; margin-right: 6px; background: #e2e8f0; color: #0f172a; }
.badge.req { background: #dbeafe; color: #1e3a8a; }
.badge.opt { background: #ecfccb; color: #3f6212; }
.code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; background: #0b1020; color: #e2e8f0; padding: 2px 6px; border-radius: 6px; }
.small { color: #475569; font-size: 12px; }
.note { background: #fff7ed; border: 1px solid #fed7aa; padding: 8px 10px; border-radius: 8px; color: #7c2d12; }
</style>

<table class="tool-table">
  <thead>
    <tr>
      <th>Tool</th>
      <th>Description</th>
      <th>Required Params</th>
      <th>Optional Params</th>
      <th>Notes</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><span class="code">fr_create_project</span></td>
      <td>Create a Freshrelease project</td>
      <td>
        <span class="badge req">name: string</span>
      </td>
      <td>
        <span class="badge opt">description: string</span>
      </td>
      <td></td>
    </tr>
    <tr>
      <td><span class="code">fr_get_project</span></td>
      <td>Get a project by id or key</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
      </td>
      <td></td>
      <td></td>
    </tr>
    <tr>
      <td><span class="code">fr_create_task</span></td>
      <td>Create an issue/task in a project</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
        <span class="badge req">title: string</span>
      </td>
      <td>
        <span class="badge opt">description: string</span>
        <span class="badge opt">assignee_id: number</span>
        <span class="badge opt">status: string|enum</span>
        <span class="badge opt">due_date: YYYY-MM-DD</span>
        <span class="badge opt">issue_type_name: string (defaults to "task")</span>
        <span class="badge opt">user: string (email or name)</span>
        <span class="badge opt">additional_fields: object</span>
      </td>
      <td>
        - <span class="small">If <span class="code">assignee_id</span> not provided and <span class="code">user</span> is, the user is looked up by <span class="code">/{project}/users?q=..</span> to set <span class="code">assignee_id</span>.</span><br/>
        - <span class="small"><span class="code">issue_type_name</span> resolves via <span class="code">/{project}/project_issue_types</span> to an <span class="code">issue_type_id</span>.</span><br/>
        - <span class="small">Protected keys in <span class="code">additional_fields</span> won’t override core fields.</span>
      </td>
    </tr>
    <tr>
      <td><span class="code">fr_get_task</span></td>
      <td>Get an issue by key or id</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
        <span class="badge req">key: number|string</span>
      </td>
      <td></td>
      <td></td>
    </tr>
    <tr>
      <td><span class="code">fr_get_all_tasks</span></td>
      <td>List all issues in a project</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
      </td>
      <td></td>
      <td></td>
    </tr>
    <tr>
      <td><span class="code">fr_get_issue_type_by_name</span></td>
      <td>Resolve an issue type object by name</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
        <span class="badge req">issue_type_name: string</span>
      </td>
      <td></td>
      <td></td>
    </tr>
    <tr>
      <td><span class="code">fr_search_users</span></td>
      <td>Search users by name or email</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
        <span class="badge req">search_text: string</span>
      </td>
      <td></td>
      <td><span class="small">Calls <span class="code">/{project}/users?q=...</span></span></td>
    </tr>
    <tr>
      <td><span class="code">fr_link_testcase_issues</span></td>
      <td>Link issues to one or more testcases (by keys)</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
        <span class="badge req">testcase_keys: array&lt;string|number&gt;</span>
        <span class="badge req">issue_keys: array&lt;string|number&gt;</span>
      </td>
      <td></td>
      <td>
        <span class="small">Resolves keys to ids, then calls <span class="code">PUT /{project}/test_cases/update_many</span>.</span>
      </td>
    </tr>
    <tr>
      <td><span class="code">fr_list_testcases</span></td>
      <td>List all test cases in a project</td>
      <td></td>
      <td>
        <span class="badge opt">project_identifier: number|string</span>
      </td>
      <td>
        <span class="small">Uses <span class="code">FRESHRELEASE_PROJECT_KEY</span> if project_identifier not provided.</span>
      </td>
    </tr>
    <tr>
      <td><span class="code">fr_get_testcase</span></td>
      <td>Get a specific test case by key or ID</td>
      <td>
        <span class="badge req">test_case_key: string|number</span>
      </td>
      <td>
        <span class="badge opt">project_identifier: number|string</span>
      </td>
      <td>
        <span class="small">Uses <span class="code">FRESHRELEASE_PROJECT_KEY</span> if project_identifier not provided.</span>
      </td>
    </tr>
    <tr>
      <td><span class="code">fr_get_testcases_by_section</span></td>
      <td>Get test cases in a section and its sub-sections</td>
      <td>
        <span class="badge req">section_name: string</span>
      </td>
      <td>
        <span class="badge opt">project_identifier: number|string</span>
      </td>
      <td>
        <span class="small">Uses <span class="code">FRESHRELEASE_PROJECT_KEY</span> if project_identifier not provided.</span>
      </td>
    </tr>
    <tr>
      <td><span class="code">fr_add_testcases_to_testrun</span></td>
      <td>Add test cases to a test run</td>
      <td>
        <span class="badge req">project_identifier: number|string</span>
        <span class="badge req">test_run_id: number|string</span>
      </td>
      <td>
        <span class="badge opt">test_case_keys: array&lt;string|number&gt;</span>
        <span class="badge opt">section_hierarchy_paths: array&lt;string&gt;</span>
        <span class="badge opt">section_subtree_ids: array&lt;string|number&gt;</span>
        <span class="badge opt">section_ids: array&lt;string|number&gt;</span>
        <span class="badge opt">filter_rule: array&lt;object&gt;</span>
      </td>
      <td>
        <span class="small">Resolves keys to IDs. <span class="code">section_hierarchy_paths</span> format: "Parent > Child > Grandchild".</span>
      </td>
    </tr>
  </tbody>
</table>

<div class="note">
For <span class="code">status</span> you may pass a string or enum. Enum values: <span class="code">todo</span>, <span class="code">in_progress</span>, <span class="code">done</span>.
</div>

## Getting Started


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
FRESHRELEASE_PROJECT_KEY="<YOUR_PROJECT_KEY>" \
freshrelease-mcp
```

### Prerequisites

- Freshrelease API access (domain + API key)
- Freshrelease API key

### Environment Variables

- `FRESHRELEASE_API_KEY`: Your Freshrelease API key (required)
- `FRESHRELEASE_DOMAIN`: Your Freshrelease domain (required)
- `FRESHRELEASE_PROJECT_KEY`: Default project key/ID to use when not specified in function calls (optional)

**Note**: When `FRESHRELEASE_PROJECT_KEY` is set, you can omit the `project_identifier` parameter from most functions, and the server will automatically use the default project key.
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
- "Create a task 'Add CI pipeline' under project 'ENG' with a custom field"

Example with custom fields for task creation and assignee by email:

```json
{
  "tool": "fr_create_task",
  "args": {
    "project_identifier": "ENG",
    "title": "Add CI pipeline",
    "status": "in_progress",
    "issue_type_name": "task",
    "user": "dev@yourco.com",
    "additional_fields": {
      "priority": "High",
      "labels": ["devops", "ci"],
      "estimate": 3
    }
  }
}
```

Link multiple testcases to issues by keys:

```json
{
  "tool": "fr_link_testcase_issues",
  "args": {
    "project_identifier": "ENG",
    "testcase_keys": ["TC-101", "TC-102"],
    "issue_keys": ["ENG-123", "ENG-456"]
  }
}
```

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
