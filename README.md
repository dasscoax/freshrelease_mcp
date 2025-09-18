# Freshrelease MCP Server

[![PyPI version](https://badge.fury.io/py/freshrelease-mcp.svg)](https://badge.fury.io/py/freshrelease-mcp)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

An MCP server implementation that integrates with Freshrelease, enabling AI models to interact with Freshrelease projects and tasks through 20 powerful MCP tools.

## Quick Reference

| Category | Tools | Description |
|----------|-------|-------------|
| **Project Management** | 2 | Create and retrieve projects |
| **Task Management** | 4 | Create, retrieve, and manage tasks/issues |
| **User Management** | 1 | Search and resolve users |
| **Form Fields Management** | 3 | Get form fields for issues and test cases |
| **Test Case Management** | 6 | List, filter, and manage test cases |
| **Filtering & Search** | 4 | Advanced filtering for tasks and test cases |
| **Lookup Functions** | 4 | Resolve names to IDs for various entities |
| **Total** | **24** | **Complete Freshrelease integration** |

## Features

- **Freshrelease Integration**: Seamless interaction with Freshrelease API endpoints
- **AI Model Support**: Enables AI models to perform project/task operations through Freshrelease
- **Automated Project Management**: Handle project and task creation and retrieval
- **Smart Name Resolution**: Automatic conversion of human-readable names to IDs
- **Custom Field Detection**: Automatic detection and prefixing of custom fields
- **Advanced Filtering**: Powerful task filtering with multiple query formats


## Components

### MCP Tools (24 Available)

The server offers 24 MCP tools for Freshrelease operations, organized by functionality:

#### **Project Management (2 tools)**
- `fr_create_project`: Create a project
  - Inputs: `name` (string, required), `description` (string, optional)

- `fr_get_project`: Get a project by ID or key
  - Inputs: `project_identifier` (number|string, required)

#### **Task Management (4 tools)**
- `fr_create_task`: Create a task under a project
  - Inputs: `project_identifier` (number|string, required), `title` (string, required), `description` (string, optional), `assignee_id` (number, optional), `status` (string|enum, optional), `due_date` (YYYY-MM-DD, optional), `issue_type_name` (string, optional, defaults to "task"), `user` (string email or name, optional), `additional_fields` (object, optional)
  - Notes: `user` resolves to `assignee_id` via users search if `assignee_id` not provided. `issue_type_name` resolves to `issue_type_id`. `additional_fields` allows passing arbitrary extra fields supported by your Freshrelease account. Core fields (`title`, `description`, `assignee_id`, `status`, `due_date`, `issue_type_id`) cannot be overridden.

- `fr_get_task`: Get a task by key or ID within a project
  - Inputs: `project_identifier` (number|string, required), `key` (number|string, required)

- `fr_get_all_tasks`: List issues for a project
  - Inputs: `project_identifier` (number|string, required)

- `fr_get_issue_type_by_name`: Resolve an issue type object by name
  - Inputs: `project_identifier` (number|string, required), `issue_type_name` (string, required)

#### **User Management (1 tool)**
- `fr_search_users`: Search users by name or email within a project
  - Inputs: `project_identifier` (number|string, required), `search_text` (string, required)

#### **Form Fields Management (3 tools)**
- `fr_get_issue_form_fields`: Get form fields for issue creation and filtering
  - Inputs: `project_identifier` (number|string, optional), `issue_type_id` (number|string, optional)
  - Notes: Shows both standard and custom fields. Use `issue_type_id` to get fields specific to an issue type.

- `fr_get_all_issue_type_form_fields`: Get form fields for all issue types in a project
  - Inputs: `project_identifier` (number|string, optional)
  - Notes: Returns form fields for each issue type (Bug, Task, Epic, etc.) to see field differences.

- `fr_get_testcase_form_fields`: Get form fields for test case filtering
  - Inputs: `project_identifier` (number|string, optional)
  - Notes: Shows available fields for test case filter rules.

#### **Test Case Management (6 tools)**
- `fr_list_testcases`: List all test cases in a project
  - Inputs: `project_identifier` (number|string, optional)
  - Notes: Uses FRESHRELEASE_PROJECT_KEY if project_identifier not provided.

- `fr_get_testcase`: Get a specific test case by key or ID
  - Inputs: `project_identifier` (number|string, optional), `test_case_key` (string|number, required)
  - Notes: Uses FRESHRELEASE_PROJECT_KEY if project_identifier not provided.

- `fr_get_testcases_by_section`: Get test cases within a section and its sub-sections
  - Inputs: `project_identifier` (number|string, optional), `section_name` (string, required)
  - Notes: Supports hierarchical section names like "Authentication > Login". Uses FRESHRELEASE_PROJECT_KEY if project_identifier not provided.

- `fr_link_testcase_issues`: Bulk link issues to one or more testcases (using keys)
  - Inputs: `project_identifier` (number|string, required), `testcase_keys` (array of string|number), `issue_keys` (array of string|number)

- `fr_add_testcases_to_testrun`: Add test cases to a test run
  - Inputs: `project_identifier` (number|string, optional), `test_run_id` (number|string, required), `test_case_keys` (array of string|number, optional), `section_hierarchy_paths` (array of string, optional), `filter_rule` (array of object, optional)
  - Notes: Adds test cases to a test run. Can specify test case keys, section hierarchy paths, or filter rules. Uses FRESHRELEASE_PROJECT_KEY if project_identifier not provided.

#### **Filtering & Search (2 tools)**
- `fr_filter_tasks`: Filter tasks/issues using various criteria with automatic name-to-ID resolution and custom field detection
  - Inputs: `project_identifier` (number|string, optional), `query` (string|object, optional), `query_format` (string, optional), plus 19 standard field parameters
  - Standard Fields: `title`, `description`, `status_id` (ID or name), `priority_id`, `owner_id` (ID, name, or email), `issue_type_id` (ID or name), `project_id` (ID or key), `story_points`, `sprint_id` (ID or name), `start_date`, `due_by`, `release_id` (ID or name), `tags`, `document_ids`, `parent_id` (ID or issue key), `epic_id` (ID or issue key), `sub_project_id` (ID or name), `effort_value`, `duration_value`
  - Notes: Supports individual field parameters or query format. Automatically resolves names to IDs for all supported fields. Automatically detects and prefixes custom fields with "cf_". Uses FRESHRELEASE_PROJECT_KEY if project_identifier not provided.

- `fr_save_filter`: Save a filter using query_hash from a previous fr_filter_tasks call
  - Inputs: `label` (string, required), `query_hash` (array, required), `project_identifier` (number|string, optional), `private_filter` (boolean, optional, default: true), `quick_filter` (boolean, optional, default: false)
  - Notes: Creates and saves custom filters that can be reused. Use fr_filter_tasks first to get the query_hash, then save it with this function. Perfect for creating reusable filter presets.

- `fr_filter_testcases`: Filter test cases using filter rules with automatic name-to-ID resolution
  - Inputs: `project_identifier` (number|string, optional), `filter_rules` (array of objects, optional)
  - Notes: Filter test cases by section, severity, type, linked issues, tags, etc. Automatically resolves names to IDs for section_id, type_id, issue_ids, tags, and custom fields. Use fr_get_testcase_form_fields to get available fields and values.

- `fr_get_testcase_form_fields`: Get available fields for test case filtering
  - Inputs: `project_identifier` (number|string, optional)
  - Notes: Returns form fields that can be used in test case filter rules. Use this to understand available filter conditions and their possible values.

#### **Lookup Functions (4 tools)**
- `fr_get_sprint_by_name`: Get sprint ID by name
  - Inputs: `project_identifier` (number|string, optional), `sprint_name` (string, required)

- `fr_get_release_by_name`: Get release ID by name
  - Inputs: `project_identifier` (number|string, optional), `release_name` (string, required)

- `fr_get_tag_by_name`: Get tag ID by name
  - Inputs: `project_identifier` (number|string, optional), `tag_name` (string, required)

- `fr_get_subproject_by_name`: Get subproject ID by name
  - Inputs: `project_identifier` (number|string, optional), `subproject_name` (string, required)

- `fr_get_current_subproject_sprint`: Get the current active sprint for a sub-project by name
  - Inputs: `sub_project_name` (string, required)
  - Notes: Uses FRESHRELEASE_PROJECT_KEY environment variable. Resolves sub-project name to ID, then fetches active sprints. Returns the current sprint with sub-project info and all active sprints.



## Advanced Features

### Internal Performance & Caching
The server includes advanced performance monitoring and caching systems that operate internally:
- **Performance Monitoring**: All MCP tools are automatically monitored for execution times and call counts
- **Multi-level Caching**: Custom fields, lookup data, and resolved IDs are cached for optimal performance
- **Connection Pooling**: Global HTTP client with connection reuse for efficient API calls
- **Batch Processing**: Parallel resolution of multiple names to IDs for improved performance

### Internal Utility Functions
The server includes utility functions for code reuse across MCP tools:
- **`get_subproject_id_by_name()`**: Resolves sub-project names to IDs using default project from environment
- **`_resolve_subproject_name_to_id()`**: Integration wrapper for task filtering system
- Used internally by sprint functions, task filtering, and other sub-project related functions for consistent name resolution

*Note: Performance, cache management, and utility functions are available internally but not exposed as MCP tools to keep the interface clean and focused on core Freshrelease functionality.*

### Smart Name Resolution
The server automatically converts human-readable names to Freshrelease IDs:
- **User Names/Emails** → User IDs
- **Issue Type Names** → Issue Type IDs  
- **Status Names** → Status IDs
- **Sprint Names** → Sprint IDs
- **Release Names** → Release IDs
- **Sub-Project Names** → Sub-Project IDs
- **Project Keys** → Project IDs (when needed)
- **Issue Keys** → Issue IDs

### Project Identifier Flexibility
All functions accept both **project keys** and **project IDs**:
- **Project Keys**: String identifiers like `"FS"`, `"PROJ"`, `"DEV"`
- **Project IDs**: Numeric identifiers like `123`, `456`, `789`
- **Auto-fallback**: Uses `FRESHRELEASE_PROJECT_KEY` environment variable if not specified

### Custom Field Detection
- **Automatic Detection**: Fetches custom fields from Freshrelease form API
- **Smart Prefixing**: Automatically adds "cf_" prefix to custom fields
- **Caching**: Custom fields are cached for performance
- **Standard Fields**: Recognizes 19 standard Freshrelease fields

### Advanced Filtering
- **Multiple Query Formats**: Comma-separated or JSON format
- **Individual Parameters**: Use specific field parameters
- **Combined Queries**: Mix individual parameters with query strings
- **Name Resolution**: All field names automatically resolved to IDs

## Getting Started

### Installation Options

#### Option 1: For End Users (No Python Installation Required)
```bash
# Install uv (one-time setup)
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# OR
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# The MCP will be installed automatically via uvx when needed
```

#### Option 2: For Users with Python + uv Installed  
```bash
# Install as uv tool (recommended - faster startup)
uv tool install freshrelease-mcp

# OR install with pip
pip install freshrelease-mcp
```

#### Option 3: For Local installation
```bash
# Clone and install in development mode
git clone <repository-url>
cd freshrelease-mcp
uv tool install . --force
```

## Cursor IDE Setup

### Quick Setup (3 minutes)

1. **Get your Freshrelease credentials:**
   - **API Key**: Go to Freshrelease → Profile → API Key
   - **Domain**: Your Freshrelease URL (e.g., `company.freshrelease.com`)  
   - **Project Key**: Your project identifier (e.g., `PROJ`, `FS`)

2. **Configure Cursor** by adding to `~/.cursor/mcp.json`:

#### Configuration A: No Python Required (uvx method)
```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uvx",
      "args": ["freshrelease-mcp"],
      "env": {
        "FRESHRELEASE_API_KEY": "your_api_key_here",
        "FRESHRELEASE_DOMAIN": "your_domain.freshrelease.com",
        "FRESHRELEASE_PROJECT_KEY": "your_project_key"
      }
    }
  }
}
```

#### Configuration B: With Python/uv Installed (faster startup)
```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uv",
      "args": ["tool", "run", "freshrelease-mcp"],
      "env": {
        "FRESHRELEASE_API_KEY": "your_api_key_here",
        "FRESHRELEASE_DOMAIN": "your_domain.freshrelease.com", 
        "FRESHRELEASE_PROJECT_KEY": "your_project_key"
      }
    }
  }
}
```

#### Configuration C: Local Development
```json
{
  "mcpServers": {
    "freshrelease-mcp": {
      "command": "uv",
      "args": ["tool", "run", "freshrelease-mcp"],
      "env": {
        "FRESHRELEASE_API_KEY": "your_api_key_here",
        "FRESHRELEASE_DOMAIN": "your_domain.freshrelease.com",
        "FRESHRELEASE_PROJECT_KEY": "your_project_key"
      },
      "cwd": "/path/to/freshrelease_mcp"
    }
  }
}
```

3. **Restart Cursor** completely

4. **Verify Setup**: You should see 24+ Freshrelease MCP tools available in Cursor:
   - `fr_create_task`, `fr_get_all_tasks`, `fr_filter_tasks`
   - `fr_get_testcase`, `fr_filter_testcases`, `fr_link_testcase_issues`
   - And many more!

### Performance Comparison

| Method | Startup Time | Requires Python | Offline Support | Best For |
|--------|-------------|----------------|-----------------|----------|
| **uvx** | ~3-5 seconds | ❌ No | ❌ No | End users, clean systems |
| **uv tool** | **~1 second** | ✅ Yes | ✅ Yes | **Developers, fastest option** |
| **Virtual env** | ~0.5 seconds | ✅ Yes | ✅ Yes | Advanced users |

### Troubleshooting

#### Not seeing tools in Cursor?
1. Check `~/.cursor/mcp.json` syntax is valid JSON
2. Verify your environment variables are correct
3. Restart Cursor completely 
4. Check Cursor's developer console for errors

#### Test MCP directly:
```bash
# Test uvx approach
uvx freshrelease-mcp --help

# Test uv tool approach  
uv tool run freshrelease-mcp --help

# Clear cache if needed
uv cache clean
uvx --reinstall freshrelease-mcp
```

#### Verify credentials:
- Test your API key works with Freshrelease API
- Ensure domain format is `company.freshrelease.com` (no https://)
- Check project key exists in your Freshrelease account

### Environment Setup
```bash
export FRESHRELEASE_API_KEY="your_api_key_here"
export FRESHRELEASE_DOMAIN="your_domain.freshrelease.com"
export FRESHRELEASE_PROJECT_KEY="your_project_key"  # Optional: default project
```

### Basic Usage
```python
# Create a project
fr_create_project(name="My Project", description="Project description")

# Create a task with smart name resolution
fr_create_task(
    project_identifier="FS",  # Project key
    title="Fix bug in login",
    issue_type_name="Bug",  # Automatically resolved to ID
    user="john@example.com",  # Automatically resolved to assignee_id
    status="In Progress"  # Automatically resolved to status ID
)

# Filter tasks with advanced criteria using project ID
fr_filter_tasks(
    project_identifier=123,  # Project ID
    owner_id="John Doe",  # Name automatically resolved to ID
    status_id="In Progress",  # Status name resolved to ID
    sprint_id="Sprint 1"  # Sprint name resolved to ID
)

# Get current sub-project sprint (uses FRESHRELEASE_PROJECT_KEY)
fr_get_current_subproject_sprint(
    sub_project_name="Frontend Development"
)
```


## Configuration

### Environment Variables
```bash
# Required
FRESHRELEASE_API_KEY="your_api_key_here"
FRESHRELEASE_DOMAIN="your_domain.freshrelease.com"

# Optional
FRESHRELEASE_PROJECT_KEY="your_project_key"  # Default project identifier
```

## Examples

### Create a Project and Task
```python
# Create a project
project = fr_create_project(
    name="Web Application",
    description="Main web application project"
)

# Create a task with smart resolution
task = fr_create_task(
    title="Implement user authentication",
    description="Add login and registration functionality",
    issue_type_name="Task",
    user="john@example.com",
    status="In Progress",
    due_date="2024-12-31"
)
```

### Filter Tasks
```python
# Filter by multiple criteria
tasks = fr_filter_tasks(
    owner_id="John Doe",
    status_id="In Progress",
    issue_type_id="Bug",
    sprint_id="Sprint 1"
)

# Using query format
tasks = fr_filter_tasks(
    query="owner_id:John Doe,status_id:In Progress,cf_priority:High"
)

# Filter by sub-project name (automatically resolved to ID)
tasks = fr_filter_tasks(
    sub_project_id="Frontend Development",
    status_id="In Progress"
)
```

### Save Filters
```python
# First, get a filter result
result = fr_filter_tasks(
    owner_id="John Doe",
    status_id="In Progress",
    issue_type_id="Bug"
)

# Then save the filter using the query_hash from the result
saved_filter = fr_save_filter(
    label="My Bug Filter",
    query_hash=result.get("query_hash", []),
    private_filter=True,
    quick_filter=True
)

# Save a filter using query format
result = fr_filter_tasks(query="priority_id:1,status_id:Open")
saved_filter = fr_save_filter(
    label="High Priority Tasks",
    query_hash=result.get("query_hash", []),
    private_filter=False
)
```

### Test Case Management
```python
# Get test cases by section
test_cases = fr_get_testcases_by_section(
    section_name="Authentication > Login"
)

# Add test cases to test run
fr_add_testcases_to_testrun(
    test_run_id=123,
    test_case_keys=["TC-001", "TC-002"],
    section_hierarchy_paths=["Authentication > Login", "Authentication > Registration"]
)
```

### Test Case Filtering
```python
# Get available filter fields first
form_fields = fr_get_testcase_form_fields()

# Filter by section name (automatically resolved to ID)
test_cases = fr_filter_testcases(
    filter_rules=[{"condition": "section_id", "operator": "is", "value": "Authentication"}]
)

# Filter by test case type name and severity (type name automatically resolved)
test_cases = fr_filter_testcases(
    filter_rules=[
        {"condition": "type_id", "operator": "is", "value": "Functional Test"},
        {"condition": "severity_id", "operator": "is_in", "value": ["High", "Medium"]}
    ]
)

# Filter by linked issue keys (automatically resolved to IDs)
test_cases = fr_filter_testcases(
    filter_rules=[{"condition": "issue_ids", "operator": "is_in", "value": ["PROJ-123", "PROJ-456"]}]
)

# Filter by tag names (automatically resolved to IDs)
test_cases = fr_filter_testcases(
    filter_rules=[{"condition": "tags", "operator": "is_in", "value": ["smoke", "regression"]}]
)

# Filter by custom fields (values automatically resolved)
test_cases = fr_filter_testcases(
    filter_rules=[{"condition": "cf_priority", "operator": "is", "value": "Critical"}]
)
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

