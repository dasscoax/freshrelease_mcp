# Freshrelease MCP Server


An MCP server implementation that integrates with Freshrelease, enabling AI models to interact with Freshrelease projects and tasks.

## Features

- **Freshrelease Integration**: Seamless interaction with Freshrelease API endpoints
- **AI Model Support**: Enables AI models to perform project/task operations through Freshrelease
- **Automated Project Management**: Handle project and task creation and retrieval
- **Smart Name Resolution**: Automatic conversion of human-readable names to IDs
- **Custom Field Detection**: Automatic detection and prefixing of custom fields
- **Advanced Filtering**: Powerful task filtering with multiple query formats


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

- `fr_filter_tasks`: Filter tasks/issues using various criteria with automatic name-to-ID resolution and custom field detection
  - Inputs: `project_identifier` (number|string, optional), `query` (string|object, optional), `query_format` (string, optional), plus 19 standard field parameters
  - Standard Fields: `title`, `description`, `status_id` (ID or name), `priority_id`, `owner_id` (ID, name, or email), `issue_type_id` (ID or name), `project_id` (ID or key), `story_points`, `sprint_id` (ID or name), `start_date`, `due_by`, `release_id` (ID or name), `tags`, `document_ids`, `parent_id` (ID or issue key), `epic_id` (ID or issue key), `sub_project_id` (ID or name), `effort_value`, `duration_value`
  - Notes: Supports individual field parameters or query format. Automatically resolves names to IDs for all supported fields. Automatically detects and prefixes custom fields with "cf_". Uses FRESHRELEASE_PROJECT_KEY if project_identifier not provided.

- `fr_save_filter`: Save a filter using query_hash from a previous fr_filter_tasks call
  - Inputs: `label` (string, required), `query_hash` (array, required), `project_identifier` (number|string, optional), `private_filter` (boolean, optional, default: true), `quick_filter` (boolean, optional, default: false)
  - Notes: Creates and saves custom filters that can be reused. Use fr_filter_tasks first to get the query_hash, then save it with this function. Perfect for creating reusable filter presets.

- `fr_clear_filter_cache`: Clear the custom fields cache for filter operations
  - Inputs: None
  - Notes: Useful when custom fields are added/modified in Freshrelease and you want to refresh the cache without restarting the server.

- `fr_clear_lookup_cache`: Clear the lookup cache for sprints, releases, tags, and subprojects
  - Inputs: None
  - Notes: Useful when these items are added/modified in Freshrelease and you want to refresh the cache without restarting the server.

- `fr_clear_resolution_cache`: Clear the resolution cache for name-to-ID lookups
  - Inputs: None
  - Notes: Useful when you want to refresh resolved IDs without restarting the server.

- `fr_clear_all_caches`: Clear all caches (custom fields, lookup data, and resolution cache)
  - Inputs: None
  - Notes: Useful when you want to refresh all cached data without restarting the server.

### Lookup Functions
- `fr_get_sprint_by_name`: Get sprint ID by name
  - Inputs: `project_identifier` (number|string, optional), `sprint_name` (string, required)

- `fr_get_release_by_name`: Get release ID by name
  - Inputs: `project_identifier` (number|string, optional), `release_name` (string, required)

- `fr_get_tag_by_name`: Get tag ID by name
  - Inputs: `project_identifier` (number|string, optional), `tag_name` (string, required)

- `fr_get_subproject_by_name`: Get subproject ID by name
  - Inputs: `project_identifier` (number|string, optional), `subproject_name` (string, required)



## Advanced Features

### Smart Name Resolution
The server automatically converts human-readable names to Freshrelease IDs:
- **User Names/Emails** → User IDs
- **Issue Type Names** → Issue Type IDs  
- **Status Names** → Status IDs
- **Sprint Names** → Sprint IDs
- **Release Names** → Release IDs
- **Project Keys** → Project IDs
- **Issue Keys** → Issue IDs

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

### Installation
```bash
pip install freshrelease-mcp
```

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
    title="Fix bug in login",
    issue_type_name="Bug",  # Automatically resolved to ID
    user="john@example.com",  # Automatically resolved to assignee_id
    status="In Progress"  # Automatically resolved to status ID
)

# Filter tasks with advanced criteria
fr_filter_tasks(
    owner_id="John Doe",  # Name automatically resolved to ID
    status_id="In Progress",  # Status name resolved to ID
    sprint_id="Sprint 1"  # Sprint name resolved to ID
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

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

