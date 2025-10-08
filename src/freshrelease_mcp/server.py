import httpx
import asyncio
from mcp.server.fastmcp import FastMCP
import logging
import os
import base64
from typing import Optional, Dict, Union, Any, List, Callable, Awaitable
from enum import IntEnum, Enum
import re
from pydantic import BaseModel, Field
from functools import wraps
import time
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize FastMCP server
mcp = FastMCP("freshrelease-mcp")

FRESHRELEASE_API_KEY = os.getenv("FRESHRELEASE_API_KEY")
FRESHRELEASE_DOMAIN = os.getenv("FRESHRELEASE_DOMAIN")
FRESHRELEASE_PROJECT_KEY = os.getenv("FRESHRELEASE_PROJECT_KEY")

# Global HTTP client for connection pooling
_http_client: Optional[httpx.AsyncClient] = None

# Performance metrics
_performance_metrics: Dict[str, List[float]] = {}


def get_http_client() -> httpx.AsyncClient:
    """Get or create a global HTTP client for connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
    return _http_client


async def close_http_client():
    """Close the global HTTP client."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def performance_monitor(func_name: str):
    """Decorator to monitor function performance."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if func_name not in _performance_metrics:
                    _performance_metrics[func_name] = []
                _performance_metrics[func_name].append(duration)
        return async_wrapper
    return decorator


def get_performance_stats() -> Dict[str, Dict[str, float]]:
    """Get performance statistics for all monitored functions."""
    stats = {}
    for func_name, durations in _performance_metrics.items():
        if durations:
            stats[func_name] = {
                "count": len(durations),
                "avg_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "total_duration": sum(durations)
            }
    return stats


def clear_performance_stats():
    """Clear performance statistics."""
    global _performance_metrics
    _performance_metrics.clear()


def get_project_identifier(project_identifier: Optional[Union[int, str]] = None) -> Union[int, str]:
    """Get project identifier from parameter or environment variable.
    
    Args:
        project_identifier: Project identifier passed to function
        
    Returns:
        Project identifier from parameter or environment variable
        
    Raises:
        ValueError: If no project identifier is provided and FRESHRELEASE_PROJECT_KEY is not set
    """
    if project_identifier is not None:
        return project_identifier
    
    if FRESHRELEASE_PROJECT_KEY:
        return FRESHRELEASE_PROJECT_KEY
    
    raise ValueError("No project identifier provided and FRESHRELEASE_PROJECT_KEY environment variable is not set")


def validate_environment() -> Dict[str, str]:
    """Validate required environment variables are set.
    
    Returns:
        Dictionary with base_url and headers if valid
        
    Raises:
        ValueError: If required environment variables are missing
    """
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        raise ValueError("FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set")
    
    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }
    return {"base_url": base_url, "headers": headers}


async def make_api_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None
) -> Dict[str, Any]:
    """Make an API request with standardized error handling and connection pooling.
    
    Args:
        method: HTTP method (GET, POST, PUT, etc.)
        url: Request URL
        headers: Request headers
        json_data: JSON payload for POST/PUT requests
        params: Query parameters
        client: HTTP client instance (optional, uses global client if not provided)
        
    Returns:
        API response as dictionary
        
    Raises:
        httpx.HTTPStatusError: For HTTP errors
        Exception: For other errors
    """
    if client is None:
        client = get_http_client()
    
    try:
        if method.upper() == "GET":
            response = await client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, json=json_data, params=params)
        elif method.upper() == "PUT":
            response = await client.put(url, headers=headers, json=json_data, params=params)
        elif method.upper() == "DELETE":
            response = await client.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        error_details = e.response.json() if e.response else None
        raise httpx.HTTPStatusError(
            f"API request failed: {str(e)}", 
            request=e.request, 
            response=e.response
        ) from e
    except Exception as e:
        raise Exception(f"Unexpected error during API request: {str(e)}") from e


def create_error_response(error_msg: str, details: Any = None) -> Dict[str, Any]:
    """Create standardized error response.
    
    Args:
        error_msg: Error message
        details: Additional error details
        
    Returns:
        Standardized error response dictionary
    """
    response = {"error": error_msg}
    if details is not None:
        response["details"] = details
    return response




# Cache for standard fields to avoid recreating set on every call
_STANDARD_FIELDS = {
    "status_id", "priority_id", "owner_id", "issue_type_id", "project_id", 
    "story_points", "sprint_id", "start_date", "due_by", "release_id", 
    "tags", "parent_id", "epic_id", "sub_project_id"
}

# Cache for custom fields to avoid repeated API calls
_custom_fields_cache: Dict[str, List[Dict[str, Any]]] = {}

# Cache for lookup data (sprints, releases, tags, subprojects)
_lookup_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

# Cache for resolved IDs to avoid repeated API calls
_resolution_cache: Dict[str, Dict[str, Any]] = {}

# Cache for test case form fields
_testcase_form_cache: Dict[str, Any] = {}


def get_standard_fields() -> frozenset:
    """Get the set of standard Freshrelease fields that are not custom fields."""
    return frozenset(_STANDARD_FIELDS)


def is_custom_field(field_name: str, custom_fields: List[Dict[str, Any]]) -> bool:
    """Check if a field name is a custom field based on the custom fields list."""
    # Quick check: if it's a standard field, it's not custom
    if field_name in _STANDARD_FIELDS:
        return False
    
    # If already prefixed with cf_, it's definitely custom
    if field_name.startswith("cf_"):
        return True
    
    # Check if it's in the custom fields list
    # Create a set of custom field names/keys for O(1) lookup
    custom_field_names = set()
    for custom_field in custom_fields:
        if "name" in custom_field:
            custom_field_names.add(custom_field["name"])
        if "key" in custom_field:
            custom_field_names.add(custom_field["key"])
    
    return field_name in custom_field_names


def build_filter_query_from_params(params: Dict[str, Any]) -> str:
    """Build a comma-separated filter query from individual parameters."""
    query_parts = []
    
    for key, value in params.items():
        if value is not None:
            if isinstance(value, (list, tuple)):
                # Handle array values - join with commas
                value_str = ",".join(str(v) for v in value)
                query_parts.append(f"{key}:{value_str}")
            else:
                query_parts.append(f"{key}:{value}")
    
    return ",".join(query_parts)


def parse_query_string(query_str: str) -> List[tuple]:
    """Parse a comma-separated query string into field-value pairs."""
    if not query_str:
        return []
    
    pairs = []
    for pair in query_str.split(","):
        pair = pair.strip()
        if ":" in pair:
            field_name, value = pair.split(":", 1)
            pairs.append((field_name.strip(), value.strip()))
    
    return pairs


def process_query_with_custom_fields(query_str: str, custom_fields: List[Dict[str, Any]]) -> str:
    """Process query string to add cf_ prefix for custom fields."""
    if not query_str:
        return query_str
    
    pairs = parse_query_string(query_str)
    processed_pairs = []
    
    for field_name, value in pairs:
        # Check if it's a custom field and add cf_ prefix if needed
        if is_custom_field(field_name, custom_fields) and not field_name.startswith("cf_"):
            processed_pairs.append(f"cf_{field_name}:{value}")
        else:
            processed_pairs.append(f"{field_name}:{value}")
    
    return ",".join(processed_pairs)


def parse_link_header(link_header: str) -> Dict[str, Optional[int]]:
    """Parse the Link header to extract pagination information.

    Args:
        link_header: The Link header string from the response

    Returns:
        Dictionary containing next and prev page numbers
    """
    pagination = {
        "next": None,
        "prev": None
    }

    if not link_header:
        return pagination

    # Split multiple links if present
    links = link_header.split(',')

    for link in links:
        # Extract URL and rel
        match = re.search(r'<(.+?)>;\s*rel="(.+?)"', link)
        if match:
            url, rel = match.groups()
            # Extract page number from URL
            page_match = re.search(r'page=(\d+)', url)
            if page_match:
                page_num = int(page_match.group(1))
                pagination[rel] = page_num

    return pagination


class TASK_STATUS(str, Enum):
    """Machine-friendly task status values supported by the API."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

async def fr_create_project(name: str, description: Optional[str] = None) -> Dict[str, Any]:
    """Create a project in Freshrelease.
    
    Args:
        name: Project name (required)
        description: Project description (optional)
        
    Returns:
        Created project data or error response
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]

        url = f"{base_url}/projects"
        payload: Dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description

        return await make_api_request("POST", url, headers, json_data=payload)

    except Exception as e:
        return create_error_response(f"Failed to create project: {str(e)}")

def _generate_bug_details(title: str, bug_type: str) -> Dict[str, str]:
    """Generate AI-enhanced bug details based on title and bug type.
    
    Args:
        title: Original bug title provided by user
        bug_type: Type of bug (bug, support_bug, iteration_bug)
        
    Returns:
        Dictionary with enhanced title, description, and steps_to_reproduce
    """
    # Enhanced title generation based on bug type
    title_lower = title.lower()
    
    if bug_type == "support_bug":
        if not any(word in title_lower for word in ["support", "customer", "user"]):
            enhanced_title = f"Support Issue: {title}"
        else:
            enhanced_title = title
    elif bug_type == "iteration_bug":
        if not any(word in title_lower for word in ["iteration", "sprint", "development"]):
            enhanced_title = f"Iteration Bug: {title}"
        else:
            enhanced_title = title
    else:
        # Regular bug
        if not any(word in title_lower for word in ["bug", "issue", "error", "problem"]):
            enhanced_title = f"Bug: {title}"
        else:
            enhanced_title = title
    
    # Generate steps to reproduce and contextual description
    steps = _generate_reproduction_steps(title, bug_type)
    contextual_desc = _generate_contextual_description(title)
    
    # Generate description based on bug type and title context
    description_templates = {
        "support_bug": f"""**Support Bug Report**

**Issue Summary:** {title}

**Customer Impact:** This issue affects user experience and requires immediate attention.

**Business Impact:** 
- User workflow disruption
- Potential customer escalation
- Support ticket volume increase

{steps}

**Additional Context:** 
Please provide customer details, support ticket reference, and any customer communication history.
""",
        "iteration_bug": f"""**Iteration Development Bug**

**Issue Summary:** {title}

**Development Impact:**
- Requires investigation and fix within iteration

{steps}

**Additional Context:**
Please provide iteration details, related user stories, and development context.
""",
        "bug": f"""**Bug Report**

**Issue Summary:** {title}

**Description:** 
{contextual_desc}

**Environment:**
- Browser/Platform: [To be specified]
- Version: [To be specified]  
- Environment: [Development/Staging/Production]

{steps}

**Additional Information:**
Please provide any relevant logs, screenshots, or error messages.
"""
    }
    
    return {
        "enhanced_title": enhanced_title,
        "description": description_templates.get(bug_type, description_templates["bug"]),
        "steps_to_reproduce": steps
    }


def _generate_contextual_description(title: str) -> str:
    """Generate contextual description based on title keywords."""
    title_lower = title.lower()
    
    # Common bug scenarios and their descriptions
    if any(word in title_lower for word in ["login", "authentication", "auth"]):
        return "User authentication system is not functioning as expected. This may prevent users from accessing the application."
    elif any(word in title_lower for word in ["crash", "freeze", "hang"]):
        return "Application stability issue causing unexpected termination or unresponsive behavior."
    elif any(word in title_lower for word in ["ui", "interface", "display", "render"]):
        return "User interface rendering or display issue affecting user experience and visual presentation."
    elif any(word in title_lower for word in ["data", "database", "save", "load"]):
        return "Data handling issue affecting information storage, retrieval, or processing functionality."
    elif any(word in title_lower for word in ["performance", "slow", "timeout"]):
        return "Performance degradation issue causing slower response times or system timeouts."
    elif any(word in title_lower for word in ["api", "service", "endpoint"]):
        return "API or service integration issue affecting system communication or data exchange."
    else:
        return "System functionality issue requiring investigation and resolution."


def _generate_reproduction_steps(title: str, bug_type: str) -> str:
    """Generate reproduction steps based on title analysis."""
    title_lower = title.lower()
    
    if bug_type == "support_bug":
        return """**Steps to Reproduce:**
1. Review customer support ticket and communication
2. Identify customer environment and configuration
3. Attempt to reproduce issue in similar environment
4. Document exact customer workflow that triggered the issue
5. Verify issue consistently occurs

**Expected Result:** Customer workflow should complete successfully
**Actual Result:** [Customer reported issue occurs]"""
    
    elif bug_type == "iteration_bug":
        return """**Steps to Reproduce:**
1. Set up development environment for current iteration
2. Execute the development workflow related to this issue
3. Follow the specific code path or feature implementation
4. Observe the unexpected behavior
5. Verify issue is reproducible in development environment

**Expected Result:** Development workflow should complete as designed
**Actual Result:** [Issue occurs during development]"""
    
    # Generate steps based on title keywords
    if any(word in title_lower for word in ["login", "authentication"]):
        return """**Steps to Reproduce:**
1. Navigate to login page
2. Enter valid credentials
3. Click login button
4. Observe the behavior

**Expected Result:** User should be logged in successfully
**Actual Result:** [Describe the actual issue]"""
    
    elif any(word in title_lower for word in ["ui", "interface", "display"]):
        return """**Steps to Reproduce:**
1. Open the application/page
2. Navigate to the affected UI component
3. Perform the action that triggers the display issue
4. Observe the visual behavior

**Expected Result:** UI should display correctly
**Actual Result:** [Describe the visual issue]"""
    
    else:
        return """**Steps to Reproduce:**
1. [Specify the initial setup or preconditions]
2. [Describe the first action to perform]
3. [Describe subsequent actions]
4. [Describe how to trigger the issue]
5. [Note any specific conditions required]

**Expected Result:** [Describe what should happen]
**Actual Result:** [Describe what actually happens]"""


@mcp.tool()
@performance_monitor("fr_create_bug")
async def fr_create_bug(
    title: str,
    bug_type: str = "bug",
    project_identifier: Optional[Union[int, str]] = None,
    parent_id: Optional[Union[int, str]] = None,
    assignee_id: Optional[int] = None,
    user: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
    additional_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a bug with AI-generated details and proper issue type mapping.
    
    This method creates bugs with three different types:
    - "bug": Maps to issue type "Bug" 
    - "support_bug": Maps to issue type "Support Bug"
    - "iteration_bug": Maps to sub task type and requires parent_id
    
    The method uses AI to generate enhanced title, description, and steps to reproduce
    based on the provided title and bug type context.
    
    Args:
        title: Bug title - will be enhanced by AI (required)
        bug_type: Type of bug - "bug", "support_bug", or "iteration_bug" (default: "bug") 
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        parent_id: Parent issue ID/key (required for iteration_bug type)
        assignee_id: Assignee user ID (optional)
        user: User name or email - resolves to assignee_id if assignee_id not provided
        priority: Bug priority (optional)
        due_date: ISO 8601 date string (optional)
        additional_fields: Additional fields to include (optional)
        
    Returns:
        Created bug data or error response
        
    Examples:
        # Create a regular bug
        fr_create_bug(title="Login page not loading", bug_type="bug")
        
        # Create a support bug  
        fr_create_bug(title="Customer can't access dashboard", bug_type="support_bug", user="support@company.com")
        
        # Create an iteration bug (requires parent_id)
        fr_create_bug(title="Unit test failing", bug_type="iteration_bug", parent_id="PROJ-123")
    """
    try:
        # Validate bug_type
        valid_bug_types = ["bug", "support_bug", "iteration_bug"]
        if bug_type not in valid_bug_types:
            return create_error_response(f"Invalid bug_type '{bug_type}'. Must be one of: {', '.join(valid_bug_types)}")
        
        # Validate parent_id for iteration_bug
        if bug_type == "iteration_bug" and not parent_id:
            return create_error_response("parent_id is required for iteration_bug type")
        
        # Map bug types to issue types
        issue_type_mapping = {
            "bug": "Bug",
            "support_bug": "Support Bug", 
            "iteration_bug": "Sub Task"  # Assuming sub task is available
        }
        
        issue_type_name = issue_type_mapping[bug_type]
        
        # First, get the issue type form for the specific bug type
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
        
        # Get form fields for the specific issue type
        form_fields_response = await fr_get_issue_form_fields(project_identifier, issue_type_name)
        if "error" in form_fields_response:
            return create_error_response(f"Could not get form fields for issue type '{issue_type_name}': {form_fields_response['error']}")
        
        # Extract mandatory fields from the form
        form_fields = form_fields_response.get("form", {}).get("fields", [])
        mandatory_fields = []
        for field in form_fields:
            if field.get("required", False):
                field_name = field.get("name", "")
                field_label = field.get("label", "")
                mandatory_fields.append({
                    "name": field_name,
                    "label": field_label,
                    "type": field.get("type", ""),
                    "default": field.get("default", False)
                })
        
        logging.info(f"Found {len(mandatory_fields)} mandatory fields for issue type '{issue_type_name}': {[f['name'] for f in mandatory_fields]}")
        
        # Generate AI-enhanced bug details
        enhanced_details = _generate_bug_details(title, bug_type)
        
        # Build the bug payload with AI-generated content and handle mandatory fields
        bug_payload = {
            "title": enhanced_details["enhanced_title"],
            "description": enhanced_details["description"],
            "issue_type_name": issue_type_name
        }
        
        # Check and populate mandatory fields
        missing_fields = []
        for field in mandatory_fields:
            field_name = field["name"]
            field_label = field["label"]
            
            # Skip fields that are already handled
            if field_name in ["title", "description", "issue_type"]:
                continue
            
            # Check if field is provided in parameters or additional_fields
            field_value = None
            if field_name == "assignee_id" and (assignee_id or user):
                field_value = assignee_id or user
            elif field_name == "priority_id" and priority:
                field_value = priority
            elif field_name == "due_date" and due_date:
                field_value = due_date
            elif field_name == "parent_id" and parent_id:
                field_value = parent_id
            elif additional_fields and field_name in additional_fields:
                field_value = additional_fields[field_name]
            
            if field_value is None:
                missing_fields.append(f"{field_label} ({field_name})")
        
        # Return error if mandatory fields are missing
        if missing_fields:
            return create_error_response(
                f"Missing mandatory fields for issue type '{issue_type_name}': {', '.join(missing_fields)}. "
                f"Please provide these fields in the function parameters or additional_fields."
            )
        
        # Add steps to reproduce as additional field or custom field
        if additional_fields:
            additional_fields["steps_to_reproduce"] = enhanced_details["steps_to_reproduce"]
        else:
            additional_fields = {"steps_to_reproduce": enhanced_details["steps_to_reproduce"]}
        
        # Add parent_id for iteration bugs
        if bug_type == "iteration_bug":
            additional_fields["parent_id"] = parent_id
        
        # Add optional parameters
        if assignee_id:
            bug_payload["assignee_id"] = assignee_id
        if user:
            bug_payload["user"] = user
        if priority:
            additional_fields["priority"] = priority
        if due_date:
            bug_payload["due_date"] = due_date
        
        # Create the bug using existing fr_create_task function
        result = await fr_create_task(
            title=bug_payload["title"],
            project_identifier=project_identifier,
            description=bug_payload["description"],
            assignee_id=bug_payload.get("assignee_id"),
            due_date=bug_payload.get("due_date"),
            issue_type_name=issue_type_name,
            user=bug_payload.get("user"),
            additional_fields=additional_fields
        )
        
        # Add metadata about AI generation
        if "error" not in result:
            result["ai_generated_content"] = {
                "original_title": title,
                "bug_type": bug_type,
                "enhanced_title": enhanced_details["enhanced_title"],
                "ai_generated": True
            }
        
        return result
        
    except Exception as e:
        return create_error_response(f"Failed to create bug: {str(e)}")


@mcp.tool()
@performance_monitor("fr_get_project")
async def fr_get_project(project_identifier: Optional[Union[int, str]] = None) -> Dict[str, Any]:
    """Get a project from Freshrelease by ID or key.

    Args:
        project_identifier: numeric ID (e.g., 123) or key (e.g., "ENG") (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        
    Returns:
        Project data or error response
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        url = f"{base_url}/projects/{project_id}"
        return await make_api_request("GET", url, headers)

    except Exception as e:
        return create_error_response(f"Failed to get project: {str(e)}")


@performance_monitor("fr_create_task")
async def fr_create_task(
    title: str,
    project_identifier: Optional[Union[int, str]] = None,
    description: Optional[str] = None,
    assignee_id: Optional[int] = None,
    status: Optional[Union[str, TASK_STATUS]] = None,
    due_date: Optional[str] = None,
    issue_type_name: Optional[str] = None,
    user: Optional[str] = None,
    additional_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a task under a Freshrelease project.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        title: Task title (required)
        description: Task description (optional)
        assignee_id: Assignee user ID (optional)
        status: Task status (optional)
        due_date: ISO 8601 date string (e.g., 2025-12-31) (optional)
        issue_type_name: Issue type name (e.g., "epic", "task") - defaults to "task"
        user: User name or email - resolves to assignee_id if assignee_id not provided
        additional_fields: Additional fields to include in request body (optional)
        
    Returns:
        Created task data or error response
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        # Build base payload
        payload: Dict[str, Any] = {"title": title}
        if description is not None:
            payload["description"] = description
        if assignee_id is not None:
            payload["assignee_id"] = assignee_id
        if status is not None:
            payload["status"] = status.value if isinstance(status, TASK_STATUS) else status
        if due_date is not None:
            payload["due_date"] = due_date

        # Merge additional fields without allowing overrides of core fields
        if additional_fields:
            protected_keys = {"title", "description", "assignee_id", "status", "due_date", "issue_type_id"}
            for key, value in additional_fields.items():
                if key not in protected_keys:
                    payload[key] = value

        # Resolve issue type name to ID
        name_to_resolve = issue_type_name or "task"
        issue_type_id = await resolve_issue_type_name_to_id(
            get_http_client(), base_url, project_id, headers, name_to_resolve
        )
        payload["issue_type_id"] = issue_type_id

        # Resolve user to assignee_id if applicable
        if "assignee_id" not in payload and user:
            assignee_id = await resolve_user_to_assignee_id(
                get_http_client(), base_url, project_id, headers, user
            )
            payload["assignee_id"] = assignee_id

        # Create the task
        url = f"{base_url}/{project_id}/issues"
        return await make_api_request("POST", url, headers, json_data=payload)

    except Exception as e:
        return create_error_response(f"Failed to create task: {str(e)}")


@mcp.tool()
@performance_monitor("fr_get_task")
async def fr_get_task(project_identifier: Optional[Union[int, str]] = None, key: Union[int, str] = None) -> Dict[str, Any]:
    """Get a task from Freshrelease by ID or key.
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        key: Task ID or key (required)
        
    Returns:
        Task data or error response
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        if key is None:
            return create_error_response("key is required")

        url = f"{base_url}/{project_id}/issues/{key}"
        return await make_api_request("GET", url, headers)

    except Exception as e:
        return create_error_response(f"Failed to get task: {str(e)}")

@mcp.tool()
@performance_monitor("fr_get_all_tasks")
async def fr_get_all_tasks(project_identifier: Optional[Union[int, str]] = None) -> Dict[str, Any]:
    """Get all tasks/issues for a project.
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        
    Returns:
        List of tasks or error response
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        url = f"{base_url}/{project_id}/issues"
        return await make_api_request("GET", url, headers)

    except Exception as e:
        return create_error_response(f"Failed to get all tasks: {str(e)}")


@mcp.tool()
@performance_monitor("fr_get_epic_insights")
async def fr_get_epic_insights(
    epic_key: Union[int, str],
    project_identifier: Optional[Union[int, str]] = None,
    fetch_detailed_tasks: bool = True,
    max_tasks: Optional[int] = 100
) -> Dict[str, Any]:
    """Get comprehensive AI-powered insights for an epic including detailed task analysis, git development status, and risk assessment.
    
    This method fetches an epic and all its child tasks with full details, then provides intelligent
    analysis including completion rates, team distribution, git/PR status, timeline risks, and actionable recommendations.
    
    Args:
        epic_key: Epic/Parent task ID or key (e.g., "FS-12345", 123456)
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        fetch_detailed_tasks: Whether to fetch individual task details for deep analysis (default: True)
        max_tasks: Maximum number of tasks to analyze in detail (default: 100)
        
    Returns:
        Dictionary containing epic details, detailed child tasks, and comprehensive AI insights
        
    Examples:
        # Get comprehensive epic insights with AI analysis
        fr_get_epic_insights("FS-12345")
        
        # Returns: {
        #   "epic_details": {...},
        #   "child_tasks": [...],
        #   "ai_insights": {
        #     "summary": "Epic contains 15 tasks with 60% completion rate...",
        #     "insights": ["Epic is progressing well...", "Development is active..."],
        #     "risk_factors": ["High number of open PRs..."],
        #     "metrics": {"git_development": {"open_prs": 3}, ...}
        #   }
        # }
        
        # Get insights for large epics with task limit
        fr_get_epic_insights("FS-12345", max_tasks=50)
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        project_id = get_project_identifier(project_identifier)
        
        logging.info(f"Fetching comprehensive insights for epic: {epic_key}")
        
        # Step 1: Get the epic/parent task details
        epic_details = None
        try:
            epic_response = await fr_get_task(project_identifier, epic_key)
            if "error" not in epic_response:
                epic_details = epic_response
                epic_title = epic_details.get('issue', {}).get('title', 'N/A')
                logging.info(f"Retrieved epic details: {epic_title}")
            else:
                logging.warning(f"Could not fetch epic details: {epic_response.get('error', 'Unknown error')}")
        except Exception as e:
            logging.warning(f"Could not fetch epic details: {str(e)}")
        
        # Step 2: Get list of child tasks using filter
        query_hash = [
            {"condition": "parent_id", "operator": "is", "value": epic_key}
        ]
        
        # Also check for epic_id relationship
        try:
            query_hash.append({"condition": "epic_id", "operator": "is", "value": epic_key})
        except Exception:
            pass
        
        # Get child task list with basic info
        filter_params = {
            "query_hash": query_hash,
            "project_identifier": project_identifier,
            "page": 1,
            "per_page": max_tasks or 100,
            "include": "custom_field,owner,priority,status"
        }
        
        child_tasks_response = await fr_filter_tasks(**filter_params)
        
        if "error" in child_tasks_response:
            return child_tasks_response
        
        # Extract task list
        if isinstance(child_tasks_response, dict) and "issues" in child_tasks_response:
            basic_child_tasks = child_tasks_response["issues"]
        elif isinstance(child_tasks_response, list):
            basic_child_tasks = child_tasks_response
        else:
            basic_child_tasks = []
        
        logging.info(f"Found {len(basic_child_tasks)} child tasks for epic {epic_key}")
        
        # Step 3: Fetch detailed information for each child task (if requested)
        detailed_child_tasks = []
        if fetch_detailed_tasks and basic_child_tasks:
            limited_tasks = basic_child_tasks[:max_tasks] if max_tasks else basic_child_tasks
            
            logging.info(f"Fetching detailed information for {len(limited_tasks)} tasks...")
            
            # Fetch detailed task information for each child task
            for i, task in enumerate(limited_tasks):
                try:
                    # Extract task key/ID
                    task_data = task if isinstance(task, dict) else task.get("issue", {})
                    task_key = task_data.get("key") or task_data.get("display_id") or task_data.get("id")
                    
                    if task_key:
                        # Fetch detailed task information
                        detailed_task_response = await fr_get_task(project_identifier, task_key)
                        if "error" not in detailed_task_response:
                            detailed_child_tasks.append(detailed_task_response)
                        else:
                            # If detailed fetch fails, use basic task info
                            detailed_child_tasks.append(task)
                    else:
                        # Use basic task info if no key found
                        detailed_child_tasks.append(task)
                        
                    # Progress logging for large epic analysis
                    if (i + 1) % 10 == 0:
                        logging.info(f"Processed {i + 1}/{len(limited_tasks)} tasks...")
                        
                except Exception as e:
                    logging.warning(f"Failed to fetch detailed info for task {i}: {str(e)}")
                    # Use basic task info as fallback
                    detailed_child_tasks.append(task)
        else:
            # Use basic task information
            detailed_child_tasks = basic_child_tasks[:max_tasks] if max_tasks else basic_child_tasks
        
        # Step 4: Generate comprehensive AI insights
        ai_insights = _generate_epic_insights(epic_details, detailed_child_tasks)
        
        # Step 5: Prepare comprehensive response
        result = {
            "epic_key": epic_key,
            "epic_details": epic_details,
            "child_tasks": detailed_child_tasks,
            "total_child_tasks": len(detailed_child_tasks),
            "ai_insights": ai_insights,
            "analysis_metadata": {
                "detailed_analysis": fetch_detailed_tasks,
                "tasks_analyzed": len(detailed_child_tasks),
                "max_tasks_limit": max_tasks,
                "analysis_timestamp": datetime.now().isoformat()
            }
        }
        
        logging.info(f"Generated comprehensive insights for epic {epic_key} with {len(detailed_child_tasks)} tasks")
        return result

    except Exception as e:
        error_msg = f"Failed to get epic insights: {str(e)}"
        logging.error(error_msg)
        return create_error_response(error_msg)

async def fr_get_issue_type_by_name(project_identifier: Optional[Union[int, str]] = None, issue_type_name: str = None) -> Dict[str, Any]:
    """Fetch the issue type object for a given human name within a project.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        issue_type_name: Issue type name to search for (required)
        
    Returns:
        Issue type data or error response
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        if issue_type_name is None:
            return create_error_response("issue_type_name is required")

        url = f"{base_url}/{project_id}/issue_types"
        data = await make_api_request("GET", url, headers)
        
        # Expecting a list of objects with a 'label' property
        if isinstance(data, list):
            target = issue_type_name.strip().lower()
            for item in data:
                label = str(item.get("label", "")).strip().lower()
                if label == target:
                    return item
            return create_error_response(f"Issue type '{issue_type_name}' not found")
        return create_error_response("Unexpected response structure for issue types", data)

    except Exception as e:
        return create_error_response(f"Failed to get issue type: {str(e)}")


@mcp.tool()
async def get_task_default_and_custom_fields(
    project_identifier: Optional[Union[int, str]] = None,
    issue_type_name: str = None
) -> Dict[str, Any]:
    """Get default and custom fields for a specific issue type by fetching form details.
    
    This method:
    1. Gets issue type ID from issue type name using fr_get_issue_type_by_name
    2. Gets form ID from project_issue_types mapping API
    3. Gets form details including all fields (standard and custom) from forms API
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        issue_type_name: Issue type name to get default and custom fields for (required)
        
    Returns:
        Form details with all fields information (default and custom) or error response
        
    Examples:
        # Get default and custom fields for Bug issue type
        get_task_default_and_custom_fields(issue_type_name="Bug")
        
        # Get default and custom fields for Story issue type in specific project
        get_task_default_and_custom_fields(project_identifier="FS", issue_type_name="Story")
    """
    try:
        # Validate inputs
        if not issue_type_name:
            return create_error_response("issue_type_name is required")
        
        # Step 1: Get issue type details using the existing function
        issue_type_result = await fr_get_issue_type_by_name(project_identifier, issue_type_name)
        if "error" in issue_type_result:
            return issue_type_result
        
        issue_type_id = issue_type_result.get("id")
        if not issue_type_id:
            return create_error_response("Could not extract issue_type_id from issue type result")
        
        # Get environment data
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
        
        client = get_http_client()
        
        # Step 2: Get project_issue_types mapping to find form_id
        project_issue_types_url = f"{base_url}/{project_id}/project_issue_types"
        logging.info(f"Fetching project issue types from: {project_issue_types_url}")
        
        project_issue_types_response = await client.get(project_issue_types_url, headers=headers)
        project_issue_types_response.raise_for_status()
        project_issue_types_data = project_issue_types_response.json()
        
        # Find the form_id for our issue_type_id
        project_issue_types_list = project_issue_types_data.get("project_issue_types", [])
        form_id = None
        
        for mapping in project_issue_types_list:
            if mapping.get("issue_type_id") == issue_type_id:
                form_id = mapping.get("form_id")
                break
        
        if not form_id:
            return create_error_response(f"No form found for issue type '{issue_type_name}' (ID: {issue_type_id})")
        
        # Step 3: Get form details using form_id
        form_url = f"{base_url}/{project_id}/forms/{form_id}"
        logging.info(f"Fetching form details from: {form_url}")
        
        form_response = await client.get(form_url, headers=headers)
        form_response.raise_for_status()
        form_data = form_response.json()
        
        # Add metadata to the response
        result = {
            "issue_type_info": {
                "id": issue_type_id,
                "name": issue_type_name,
                "details": issue_type_result
            },
            "form_id": form_id,
            **form_data
        }
        
        return result
        
    except Exception as e:
        logging.error(f"Error getting project custom fields: {str(e)}")
        return create_error_response(f"Failed to get project custom fields: {str(e)}")


@mcp.tool()
async def fr_search_users(project_identifier: Optional[Union[int, str]] = None, search_text: str = None) -> Any:
    """Search users in a project by name or email.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        search_text: Text to search for in user names or emails (required)
        
    Returns:
        List of matching users or error response
    """
    try:
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
    except ValueError as e:
        return create_error_response(str(e))

    if search_text is None:
        return create_error_response("search_text is required")

    url = f"{base_url}/{project_id}/users"
    params = {"q": search_text}

    try:
        return await make_api_request("GET", url, headers, params=params)
    except httpx.HTTPStatusError as e:
        return create_error_response(f"Failed to search users: {str(e)}", e.response.json() if e.response else None)
    except Exception as e:
        return create_error_response(f"An unexpected error occurred: {str(e)}")

async def issue_ids_from_keys(client: httpx.AsyncClient, base_url: str, project_identifier: Union[int, str], headers: Dict[str, str], issue_keys: List[Union[str, int]]) -> List[int]:
    resolved: List[int] = []
    for key in issue_keys:
        url = f"{base_url}/{project_identifier}/issues/{key}"
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "id" in data:
            resolved.append(int(data["id"]))
        else:
            raise httpx.HTTPStatusError("Unexpected issue response structure", request=resp.request, response=resp)
    return resolved

async def testcase_id_from_key(client: httpx.AsyncClient, base_url: str, project_identifier: Union[int, str], headers: Dict[str, str], test_case_key: Union[str, int]) -> int:
    url = f"{base_url}/{project_identifier}/test_cases/{test_case_key}"
    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "id" in data:
        return int(data["id"])
    raise httpx.HTTPStatusError("Unexpected test case response structure", request=resp.request, response=resp)

async def resolve_user_to_assignee_id(
    client: httpx.AsyncClient, 
    base_url: str, 
    project_identifier: Union[int, str], 
    headers: Dict[str, str], 
    user: str
) -> int:
    """Resolve user name or email to assignee ID.
    
    Args:
        client: HTTP client instance
        base_url: API base URL
        project_identifier: Project identifier
        headers: Request headers
        user: User name or email to resolve
        
    Returns:
        Resolved user ID
        
    Raises:
        ValueError: If no matching user found
        httpx.HTTPStatusError: For API errors
    """
    users_url = f"{base_url}/{project_identifier}/users"
    params = {"q": user}
    
    response = await client.get(users_url, headers=headers, params=params)
    response.raise_for_status()
    users_data = response.json()
    
    # Handle nested response structure {"users": [...], "meta": {...}}
    users_list = None
    if isinstance(users_data, list):
        users_list = users_data  # Direct array (backward compatibility)
    elif isinstance(users_data, dict) and "users" in users_data:
        users_list = users_data["users"]  # Nested structure
    else:
        raise ValueError(f"Unexpected response structure for users API")
    
    if not users_list:
        raise ValueError(f"No users found matching '{user}'")
    
    lowered = user.strip().lower()
    
    # Prefer exact email match
    for item in users_list:
        email = str(item.get("email", "")).strip().lower()
        if email and email == lowered:
            return item.get("id")
    
    # Then exact name match
    for item in users_list:
        name_val = str(item.get("name", "")).strip().lower()
        if name_val and name_val == lowered:
            return item.get("id")
    
    # Fallback to first result
    return users_list[0].get("id")


async def resolve_issue_type_name_to_id(
    client: httpx.AsyncClient,
    base_url: str,
    project_identifier: Union[int, str],
    headers: Dict[str, str],
    issue_type_name: str
) -> int:
    """Resolve issue type name to ID using the label field.
    
    Args:
        client: HTTP client instance
        base_url: API base URL
        project_identifier: Project identifier
        headers: Request headers
        issue_type_name: Issue type name to resolve (matches against label field)
        
    Returns:
        Resolved issue type ID
        
    Raises:
        ValueError: If issue type not found
        httpx.HTTPStatusError: For API errors
    """
    issue_types_url = f"{base_url}/{project_identifier}/issue_types"
    response = await client.get(issue_types_url, headers=headers)
    response.raise_for_status()
    it_data = response.json()
    
    types_list = it_data.get("issue_types", []) if isinstance(it_data, dict) else []
    target = issue_type_name.strip().lower()
    
    for t in types_list:
        label = str(t.get("label", "")).strip().lower()
        if label == target:
            return t.get("id")
    
    raise ValueError(f"Issue type with label '{issue_type_name}' not found")


async def resolve_section_hierarchy_to_ids(client: httpx.AsyncClient, base_url: str, project_identifier: Union[int, str], headers: Dict[str, str], section_path: str) -> List[int]:
    """Resolve a section hierarchy path like 'level1 --> level2 --> level3' to the final section ID.
    
    Navigates through section hierarchy level by level using the API:
    /{Project_identifier}/sections/{level}/sections
    
    Supports up to 7 levels of nesting.
    Returns list containing the ID of the final (deepest) section.
    
    Args:
        client: HTTP client instance
        base_url: API base URL  
        project_identifier: Project ID or key
        headers: Request headers
        section_path: Hierarchy path like "Authentication --> Login Tests --> Positive Cases"
        
    Returns:
        List containing the ID of the final section, or empty list if not found
        
    Raises:
        ValueError: If section not found in hierarchy or exceeds depth limit
        httpx.HTTPStatusError: For API errors
    """
    # Parse and validate hierarchy path
    separator = '-->' if '-->' in section_path else '>'
    path_parts = [part.strip() for part in section_path.split(separator) if part.strip()]
    
    if not path_parts:
        return []
    
    if len(path_parts) > 7:
        raise ValueError(f"Section hierarchy exceeds maximum depth of 7 levels. Got {len(path_parts)} levels.")
    
    # Navigate through hierarchy levels
    current_parent_id = None
    
    for level_index, section_name in enumerate(path_parts):
        is_final_level = level_index == len(path_parts) - 1
        
        # Fetch sections at current level
        sections = await _fetch_sections_at_level(client, base_url, project_identifier, headers, current_parent_id)
        
        # Find matching section (case-insensitive)
        section_id = _find_section_by_name(sections, section_name)
        
        if section_id is None:
            available_names = [s.get("name") for s in sections if s.get("name")]
            raise ValueError(
                f"Section '{section_name}' not found at level {level_index + 1}. "
                f"Available sections: {', '.join(available_names)}"
            )
        
        # Return final section ID or continue to next level
        if is_final_level:
            return [section_id]
        
        current_parent_id = section_id
    
    return []


def _find_section_by_name(sections: List[Dict[str, Any]], target_name: str) -> Optional[int]:
    """Find section ID by name (case-insensitive).
    
    Args:
        sections: List of section objects
        target_name: Section name to find
        
    Returns:
        Section ID if found, None otherwise
    """
    target_lower = target_name.lower()
    
    for section in sections:
        section_name = section.get("name")
        if section_name and str(section_name).strip().lower() == target_lower:
            section_id = section.get("id")
            return section_id if isinstance(section_id, int) else None
    
    return None


async def _fetch_sections_at_level(
    client: httpx.AsyncClient, 
    base_url: str, 
    project_identifier: Union[int, str], 
    headers: Dict[str, str], 
    parent_section_id: Optional[int]
) -> List[Dict[str, Any]]:
    """Fetch sections at a specific level in the hierarchy.
    
    Args:
        client: HTTP client instance
        base_url: API base URL
        project_identifier: Project ID or key  
        headers: Request headers
        parent_section_id: Parent section ID (None for root level)
        
    Returns:
        List of sections at the specified level
        
    Raises:
        httpx.HTTPStatusError: For API errors
        ValueError: For unexpected response structure
    """
    # Build URL based on hierarchy level
    if parent_section_id is None:
        url = f"{base_url}/{project_identifier}/sections"
    else:
        url = f"{base_url}/{project_identifier}/sections/{parent_section_id}/sections"
    
    # Fetch and parse response
    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    
    # Extract sections list from various response formats
    if isinstance(data, list):
        return data
    
    if isinstance(data, dict):
        # Try common response patterns in priority order
        for key in ["sections", "test_sections", "section_list", "data"]:
            sections_list = data.get(key)
            if isinstance(sections_list, list):
                return sections_list
    
    # Unexpected response structure
    raise ValueError(f"Unexpected sections API response structure: {type(data)}")

@mcp.tool()
async def fr_list_testcases(project_identifier: Optional[Union[int, str]] = None) -> Any:
    """List all test cases in a project.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        
    Returns:
        List of test cases or error response
    """
    try:
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
    except ValueError as e:
        return create_error_response(str(e))

    url = f"{base_url}/{project_id}/test_cases"

    try:
        return await make_api_request("GET", url, headers)
    except httpx.HTTPStatusError as e:
        return create_error_response(f"Failed to list test cases: {str(e)}", e.response.json() if e.response else None)
    except Exception as e:
        return create_error_response(f"An unexpected error occurred: {str(e)}")

@mcp.tool()
async def fr_get_testcase(project_identifier: Optional[Union[int, str]] = None, test_case_key: Union[str, int] = None) -> Any:
    """Get a specific test case by key or ID.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        test_case_key: Test case key or ID (required)
        
    Returns:
        Test case data or error response
    """
    try:
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
    except ValueError as e:
        return create_error_response(str(e))

    if test_case_key is None:
        return create_error_response("test_case_key is required")

    url = f"{base_url}/{project_id}/test_cases/{test_case_key}"

    try:
        return await make_api_request("GET", url, headers)
    except httpx.HTTPStatusError as e:
        return create_error_response(f"Failed to get test case: {str(e)}", e.response.json() if e.response else None)
    except Exception as e:
        return create_error_response(f"An unexpected error occurred: {str(e)}")

@mcp.tool()
async def fr_link_testcase_issues(project_identifier: Optional[Union[int, str]] = None, testcase_keys: List[Union[str, int]] = None, issue_keys: List[Union[str, int]] = None) -> Any:
    """Bulk update multiple test cases with issue links by keys.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        testcase_keys: List of test case keys/IDs to link (required)
        issue_keys: List of issue keys/IDs to link to test cases (required)
        
    Returns:
        Update result or error response
    """
    try:
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
    except ValueError as e:
        return create_error_response(str(e))

    if testcase_keys is None or issue_keys is None:
        return create_error_response("testcase_keys and issue_keys are required")

    async with httpx.AsyncClient() as client:
        try:
            # Resolve testcase keys to ids
            resolved_testcase_ids: List[int] = []
            for key in testcase_keys:
                resolved_testcase_ids.append(await testcase_id_from_key(client, base_url, project_id, headers, key))
            
            # Resolve issue keys to ids
            resolved_issue_ids = await issue_ids_from_keys(client, base_url, project_id, headers, issue_keys)
            
            # Perform bulk update
            url = f"{base_url}/{project_id}/test_cases/update_many"
            payload = {"ids": resolved_testcase_ids, "test_case": {"issue_ids": resolved_issue_ids}}
            
            return await make_api_request("PUT", url, headers, json_data=payload, client=client)
        except httpx.HTTPStatusError as e:
            return create_error_response(f"Failed to bulk update testcases: {str(e)}", e.response.json() if e.response else None)
        except Exception as e:
            return create_error_response(f"An unexpected error occurred: {str(e)}")

@mcp.tool()
async def fr_get_testcases_by_section(project_identifier: Optional[Union[int, str]] = None, section_name: str = None) -> Any:
    """Get test cases that belong to a section (by name) and its sub-sections.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        section_name: Section name to search for (required)
        
    Returns:
        List of test cases in the section or error response
    """
    try:
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
    except ValueError as e:
        return create_error_response(str(e))

    if section_name is None:
        return create_error_response("section_name is required")

    async with httpx.AsyncClient() as client:
        try:
            # 1) Fetch sections and find matching id(s)
            sections_url = f"{base_url}/{project_id}/sections"
            sections = await make_api_request("GET", sections_url, headers, client=client)

            target = section_name.strip().lower()
            matched_ids: List[int] = []
            if isinstance(sections, list):
                for sec in sections:
                    name_val = str(sec.get("name", "")).strip().lower()
                    if name_val == target:
                        sec_id = sec.get("id")
                        if isinstance(sec_id, int):
                            matched_ids.append(sec_id)
            else:
                return create_error_response("Unexpected sections response structure", sections)

            if not matched_ids:
                return create_error_response(f"Section named '{section_name}' not found")

            # 2) Fetch test cases for each matched section subtree and merge results
            testcases_url = f"{base_url}/{project_id}/test_cases"
            all_results: List[Any] = []
            
            for sid in matched_ids:
                params = [("section_subtree_ids[]", str(sid))]
                data = await make_api_request("GET", testcases_url, headers, params=params, client=client)
                if isinstance(data, list):
                    all_results.extend(data)
                else:
                    # If API returns an object, append as-is for transparency
                    all_results.append(data)

            return all_results

        except httpx.HTTPStatusError as e:
            return create_error_response(f"Failed to fetch test cases for section: {str(e)}", e.response.json() if e.response else None)
        except Exception as e:
            return create_error_response(f"An unexpected error occurred: {str(e)}")

async def _get_project_fields_mapping(
    project_id: Union[int, str],
    project_identifier: Optional[Union[int, str]] = None
) -> Dict[str, Any]:
    """Helper function to get field mappings (label to name) for filtering.
    
    This function:
    1. Gets all issue types for the project
    2. Uses the first issue type to get form fields
    3. Creates a mapping from field labels to field names
    4. Returns both the mapping and custom fields information
    
    Args:
        project_id: Project ID (resolved)
        project_identifier: Original project identifier for API calls
        
    Returns:
        Dictionary containing field_label_to_name_map and custom_fields
    """
    try:
        # Get all issue types to find one to use for form fields
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        
        client = get_http_client()
        
        # Get issue types
        issue_types_url = f"{base_url}/{project_id}/issue_types"
        logging.info(f"Fetching issue types from: {issue_types_url}")
        
        response = await client.get(issue_types_url, headers=headers)
        response.raise_for_status()
        issue_types_data = response.json()
        
        logging.info(f"Issue types response: {issue_types_data}")
        
        # Handle both direct array and nested object responses
        if isinstance(issue_types_data, dict) and "issue_types" in issue_types_data:
            issue_types_list = issue_types_data["issue_types"]
        elif isinstance(issue_types_data, list):
            issue_types_list = issue_types_data
        else:
            logging.error(f"Unexpected issue types response format: {type(issue_types_data)}")
            return {"error": f"Unexpected issue types response format: {type(issue_types_data)}"}
        
        if not issue_types_list or len(issue_types_list) == 0:
            return {"error": "No issue types found in project"}
        
        # Use the first issue type's label to get form fields
        first_issue_type = issue_types_list[0]
        issue_type_name = first_issue_type.get("label", "")
        
        if not issue_type_name:
            logging.error(f"Issue type has no label: {first_issue_type}")
            return {"error": "Issue type has no label"}
        
        logging.info(f"Using issue type '{issue_type_name}' for form fields")
        
        # Get form fields using the get_task_default_and_custom_fields method
        form_result = await get_task_default_and_custom_fields(project_identifier, issue_type_name)
        if "error" in form_result:
            logging.error(f"Form fields error: {form_result}")
            return form_result
        
        # Extract fields from the form
        form_data = form_result.get("form", {})
        fields_list = form_data.get("fields", [])
        
        logging.info(f"Found {len(fields_list)} form fields")
        
        # Create mapping from label to name
        field_label_to_name_map = {}
        custom_fields = []
        
        # Add common field mappings that might not be in form fields
        common_mappings = {
            "parent": "parent_id",
            "epic": "epic_id", 
            "owner": "owner_id",
            "assignee": "owner_id",
            "status": "status_id",
            "priority": "priority_id",
            "issue type": "issue_type_id",
            "sprint": "sprint_id",
            "release": "release_id",
            "tags": "tags",
            "sub project": "sub_project_id",
            "story points": "story_points"
        }
        
        field_label_to_name_map.update(common_mappings)
        
        for field in fields_list:
            field_name = field.get("name", "")
            field_label = field.get("label", "")
            field_default = field.get("default", False)
            
            if field_label and field_name:
                field_label_to_name_map[field_label.lower()] = field_name
                
                # If it's not a default field, add to custom_fields
                if not field_default:
                    custom_fields.append({
                        "name": field_name,
                        "label": field_label,
                        "type": field.get("type", ""),
                        "required": field.get("required", False),
                        "field_options": field.get("field_options", {}),
                        "choices": field.get("choices", [])
                    })
        
        logging.info(f"Created field mapping with {len(field_label_to_name_map)} entries")
        
        return {
            "field_label_to_name_map": field_label_to_name_map,
            "custom_fields": custom_fields,
            "issue_type_used": issue_type_name,
            "total_fields": len(fields_list)
        }
        
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code} error getting project fields mapping: {str(e)}"
        logging.error(error_msg)
        return {"error": error_msg}
    except Exception as e:
        error_msg = f"Failed to get project fields mapping: {type(e).__name__}: {str(e)}"
        logging.error(error_msg)
        return {"error": error_msg}


@mcp.tool()
@performance_monitor("fr_filter_tasks")
async def fr_filter_tasks(
    project_identifier: Optional[Union[int, str]] = None,
    query: Optional[Union[str, Dict[str, Any]]] = None,
    query_format: str = "comma_separated",
    query_hash: Optional[List[Dict[str, Any]]] = None,
    
    # Additional API parameters
    filter_id: Optional[Union[int, str]] = None,
    include: Optional[str] = None,
    page: Optional[int] = 1,
    per_page: Optional[int] = 30,
    sort: Optional[str] = None,
    sort_type: Optional[str] = None,
    
    # Standard fields
    status_id: Optional[Union[int, str]] = None,
    priority_id: Optional[Union[int, str]] = None,
    owner_id: Optional[Union[int, str]] = None,
    issue_type_id: Optional[Union[int, str]] = None,
    project_id: Optional[Union[int, str]] = None,
    story_points: Optional[Union[int, str]] = None,
    sprint_id: Optional[Union[int, str]] = None,
    start_date: Optional[str] = None,
    due_by: Optional[str] = None,
    release_id: Optional[Union[int, str]] = None,
    tags: Optional[Union[str, List[str]]] = None,
    parent_id: Optional[Union[int, str]] = None,
    epic_id: Optional[Union[int, str]] = None,
    sub_project_id: Optional[Union[int, str]] = None
) -> Any:
    """Filter tasks/issues using field labels with automatic name-to-ID resolution and custom field detection.

    This function supports both individual field parameters and query-based filtering with comprehensive
    label-to-name mapping and name-to-ID resolution for all field types including custom fields.
    
    Supports native Freshrelease query_hash format for advanced filtering.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        query: Filter query in JSON string or comma-separated format (optional)
        query_format: Format of the query - "comma_separated" or "json" (default: "comma_separated")
        query_hash: Native Freshrelease query_hash format (optional)
            Example: [{"condition": "status_id", "operator": "is_in", "value": [18, 74]}]
        
        # Additional API parameters
        filter_id: Saved filter ID to apply (optional)
        include: Fields to include in response (e.g., "custom_field,owner,priority,status")
        page: Page number for pagination (default: 1)
        per_page: Number of items per page (default: 30)
        sort: Field to sort by (e.g., "display_id", "created_at")
        sort_type: Sort direction ("asc" or "desc")
        
        # Standard fields (optional) - supports both IDs and names
        status_id: Filter by status ID or name (e.g., "In Progress", "Done")
        priority_id: Filter by priority ID
        owner_id: Filter by owner ID, name, or email (e.g., "John Doe", "john@example.com")
        issue_type_id: Filter by issue type ID or name (e.g., "Bug", "Task", "Epic")
        project_id: Filter by project ID or key (e.g., "PROJ123")
        story_points: Filter by story points
        sprint_id: Filter by sprint ID or name (e.g., "Sprint 1")
        start_date: Filter by start date (YYYY-MM-DD format)
        due_by: Filter by due date (YYYY-MM-DD format)
        release_id: Filter by release ID or name (e.g., "Release 1.0")
        tags: Filter by tags (string or array)
        parent_id: Filter by parent issue ID or key (e.g., "PROJ-123")
        epic_id: Filter by epic issue ID or key (e.g., "PROJ-456")
        sub_project_id: Filter by sub project ID or name (e.g., "Frontend")
        
    Returns:
        Filtered list of tasks or error response
        
    Examples:
        # Using native query_hash format
        fr_filter_tasks(query_hash=[
            {"condition": "status_id", "operator": "is_in", "value": [18, 74]},
            {"condition": "owner_id", "operator": "is_in", "value": [53089]}
        ])
        
        # Using saved filter with pagination
        fr_filter_tasks(filter_id=102776, include="custom_field,owner,priority,status", page=1, per_page=30)
        
        # Date range filtering using query_hash
        fr_filter_tasks(query_hash=[
            {"condition": "start_date", "operator": "is_in_the_range", 
            "value": "2024-12-31T18:30:00.000Z,2025-08-31T18:29:59.999Z"}
        ])
        
        # Using individual field parameters with names (automatically resolved to IDs)
        fr_filter_tasks(owner_id="John Doe", status_id="In Progress", issue_type_id="Bug")
        
        # Using query format with field labels and custom fields
        fr_filter_tasks(query="Owner:John Doe,Status:In Progress,Theme:ITPM")
        
    Note:
        - Field labels are automatically mapped to field names (e.g., "Status" -> "status_id", "Issue Type" -> "issue_type")
        - All field names support both human-readable names and IDs
        - Custom fields are automatically detected and handled
        - Name-to-ID resolution works for: owner_id, status_id, issue_type_id, sprint_id, release_id, sub_project_id
        - Custom field values are also resolved to IDs when possible
        - query_hash format takes precedence over individual field parameters
        - Supports all native Freshrelease operators: "is", "is_in", "is_in_the_range", "contains", etc.
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        # Build base parameters
        params = {}
        
        # Add pagination and sorting parameters
        if page:
            params["page"] = page
        if per_page:
            params["per_page"] = per_page
        if sort:
            params["sort"] = sort
        if sort_type:
            params["sort_type"] = sort_type
        # Only add include parameter if explicitly provided (not None and not empty)
        if include is not None and include.strip():
            params["include"] = include
            logging.info(f"fr_filter_tasks: Including fields: {include}")
        else:
            logging.info("fr_filter_tasks: No include parameter specified - skipping include field")
        if filter_id:
            params["filter_id"] = filter_id

        # Handle native query_hash format (highest priority)
        if query_hash:
            async with httpx.AsyncClient() as client:
                # Get form fields for value resolution
                fields_info = await _get_project_fields_mapping(project_id, project_identifier)
                if "error" in fields_info:
                    return fields_info
                
                field_label_to_name_map = fields_info["field_label_to_name_map"]
                custom_fields = fields_info["custom_fields"]
                
                for i, query_item in enumerate(query_hash):
                    condition = query_item.get("condition")
                    operator = query_item.get("operator")
                    value = query_item.get("value")
                    
                    if condition and operator and value is not None:
                        params[f"query_hash[{i}][condition]"] = condition
                        params[f"query_hash[{i}][operator]"] = operator
                        
                        # Resolve values to IDs if needed
                        resolved_values = await _resolve_query_fields(
                            [(condition, value)], 
                            project_id, 
                            client, 
                            base_url, 
                            headers,
                            custom_fields,
                            field_label_to_name_map
                        )
                        final_value = resolved_values.get(condition, value)
                        
                        # Handle array values
                        if isinstance(final_value, list):
                            for val in final_value:
                                key = f"query_hash[{i}][value][]"
                                if key in params:
                                    # Convert to list if multiple values
                                    if not isinstance(params[key], list):
                                        params[key] = [params[key]]
                                    params[key].append(val)
                                else:
                                    params[key] = val
                        else:
                            params[f"query_hash[{i}][value]"] = final_value
            
            # Make API request with query_hash
            url = f"{base_url}/{project_id}/issues"
            result = await make_api_request("GET", url, headers, params=params)
            return result

        # Collect individual field parameters (excluding project_id to avoid duplication)
        field_params = {
            "status_id": status_id,
            "priority_id": priority_id,
            "owner_id": owner_id,
            "issue_type_id": issue_type_id,
            "story_points": story_points,
            "sprint_id": sprint_id,
            "start_date": start_date,
            "due_by": due_by,
            "release_id": release_id,
            "tags": tags,
            "parent_id": parent_id,
            "epic_id": epic_id,
            "sub_project_id": sub_project_id
        }

        # Filter out None values
        field_params = {k: v for k, v in field_params.items() if v is not None}

        # Handle legacy query parameter format (only if query is provided and not empty)
        if query and str(query).strip():
            async with httpx.AsyncClient() as client:
                # Get form fields (standard and custom) for the project to process query properly
                fields_info = await _get_project_fields_mapping(project_id, project_identifier)
                if "error" in fields_info:
                    return fields_info
                
                field_label_to_name_map = fields_info["field_label_to_name_map"]
                custom_fields = fields_info["custom_fields"]
                
                # Parse query based on format
                if query_format == "json":
                    if isinstance(query, str):
                        import json
                        query_dict = json.loads(query)
                    else:
                        query_dict = query
                    query_pairs = list(query_dict.items())
                else:
                    # Comma-separated format (only process if applicable)
                    processed_query_str = process_query_with_custom_fields(query, custom_fields)
                    query_pairs = parse_query_string(processed_query_str)
                
                    # Skip processing if no valid query pairs found
                    if not query_pairs:
                        logging.info(f"No valid query pairs found in: '{query}' - skipping comma-separated processing")
                        # Continue to other filtering methods
                    else:
                        logging.info(f"Processing {len(query_pairs)} comma-separated query pairs: {query_pairs}")
                
                # Convert query_pairs to query_hash format (only if we have valid pairs)
                query_hash_items = []
                if query_pairs:
                    for i, (field, value) in enumerate(query_pairs):
                        # Map field label to name if needed (case-insensitive)
                        field_lower = field.lower()
                        if field_lower in field_label_to_name_map:
                            original_field = field
                            field = field_label_to_name_map[field_lower]
                            logging.info(f"Mapped field label '{original_field}' to field name '{field}'")
                        else:
                            logging.info(f"Field '{field}' not found in label mapping, using as-is")
                        
                        # Determine operator based on value type
                        if isinstance(value, list):
                            operator = "is_in"
                        else:
                            operator = "is"
                        
                        query_hash_items.append({
                            "condition": field,
                            "operator": operator,
                            "value": value
                        })
                
                # Build query_hash parameters (only if we have items to process)
                if query_hash_items:
                    for i, query_item in enumerate(query_hash_items):
                        condition = query_item.get("condition")
                        operator = query_item.get("operator") 
                        value = query_item.get("value")
                        
                        params[f"query_hash[{i}][condition]"] = condition
                        params[f"query_hash[{i}][operator]"] = operator
                        
                        if isinstance(value, list):
                            for val in value:
                                key = f"query_hash[{i}][value][]"
                                if key in params:
                                    if not isinstance(params[key], list):
                                        params[key] = [params[key]]
                                    params[key].append(val)
                                else:
                                    params[key] = val
                        else:
                            params[f"query_hash[{i}][value]"] = value
                
                # Make API request with converted query
                url = f"{base_url}/{project_id}/issues"
                result = await make_api_request("GET", url, headers, params=params)
                return result

        # Handle individual field parameters
        if field_params:
            async with httpx.AsyncClient() as client:
                # Get form fields (standard and custom) for individual parameter processing
                fields_info = await _get_project_fields_mapping(project_id, project_identifier)
                if "error" in fields_info:
                    return fields_info
                
                field_label_to_name_map = fields_info["field_label_to_name_map"]
                custom_fields = fields_info["custom_fields"]
                
                # Convert field_params to query_hash format
                query_hash_items = []
                for i, (field, value) in enumerate(field_params.items()):
                    # Map field label to name if needed (case-insensitive)
                    field_lower = field.lower()
                    if field_lower in field_label_to_name_map:
                        original_field = field
                        field = field_label_to_name_map[field_lower]
                        logging.info(f"Mapped field label '{original_field}' to field name '{field}'")
                    else:
                        logging.info(f"Field '{field}' not found in label mapping, using as-is")
                    
                    # Determine operator based on value type
                    if isinstance(value, list):
                        operator = "is_in"
                    else:
                        operator = "is"
                    
                    query_hash_items.append({
                        "condition": field,
                        "operator": operator,
                        "value": value
                    })
                
                # Build query_hash parameters
                for i, query_item in enumerate(query_hash_items):
                    condition = query_item.get("condition")
                    operator = query_item.get("operator")
                    value = query_item.get("value")
                    
                    params[f"query_hash[{i}][condition]"] = condition
                    params[f"query_hash[{i}][operator]"] = operator
                    
                    if isinstance(value, list):
                        for val in value:
                            key = f"query_hash[{i}][value][]"
                            if key in params:
                                if not isinstance(params[key], list):
                                    params[key] = [params[key]]
                                params[key].append(val)
                            else:
                                params[key] = val
                    else:
                        params[f"query_hash[{i}][value]"] = value

        # Make the API request - use /issues endpoint with query_hash format
        url = f"{base_url}/{project_id}/issues"
        result = await make_api_request("GET", url, headers, params=params)
        return result

    except Exception as e:
        return create_error_response(f"Failed to filter tasks: {str(e)}")

@mcp.tool()
async def fr_get_sprint_by_name(
    project_identifier: Optional[Union[int, str]] = None,
    sprint_name: str = None
) -> Any:
    """Get sprint ID by name by fetching all sprints and filtering by name.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        sprint_name: Name of the sprint to find (required)
        
    Returns:
        Sprint object with ID and details or error response
        
    Examples:
        # Get sprint by name
        fr_get_sprint_by_name(sprint_name="Sprint 1")
        
        # Get sprint by name for specific project
        fr_get_sprint_by_name(project_identifier="PROJ123", sprint_name="Sprint 1")
    """
    return await _generic_lookup_by_name(project_identifier, sprint_name, "sprints", "sprint_name")


@mcp.tool()
async def fr_get_release_by_name(
    project_identifier: Optional[Union[int, str]] = None,
    release_name: str = None
) -> Any:
    """Get release ID by name by fetching all releases and filtering by name.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        release_name: Name of the release to find (required)
        
    Returns:
        Release object with ID and details or error response
        
    Examples:
        # Get release by name
        fr_get_release_by_name(release_name="Release 1.0")
        
        # Get release by name for specific project
        fr_get_release_by_name(project_identifier="PROJ123", release_name="Release 1.0")
    """
    return await _generic_lookup_by_name(project_identifier, release_name, "releases", "release_name")


@mcp.tool()
async def fr_get_tag_by_name(
    project_identifier: Optional[Union[int, str]] = None,
    tag_name: str = None
) -> Any:
    """Get tag ID by name by fetching all tags and filtering by name.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        tag_name: Name of the tag to find (required)
        
    Returns:
        Tag object with ID and details or error response
        
    Examples:
        # Get tag by name
        fr_get_tag_by_name(tag_name="bug")
        
        # Get tag by name for specific project
        fr_get_tag_by_name(project_identifier="PROJ123", tag_name="bug")
    """
    return await _generic_lookup_by_name(project_identifier, tag_name, "tags", "tag_name")



@mcp.tool()
async def fr_clear_filter_cache() -> Any:
    """Clear the custom fields cache for filter operations.
    
    This is useful when custom fields are added/modified in Freshrelease
    and you want to refresh the cache without restarting the server.
    
    Returns:
        Success message or error response
    """
    try:
        _clear_custom_fields_cache()
        return {"message": "Custom fields cache cleared successfully"}
    except Exception as e:
        return create_error_response(f"Failed to clear cache: {str(e)}")


async def fr_clear_lookup_cache() -> Any:
    """Clear the lookup cache for sprints, releases, tags, and subprojects.
    
    This is useful when these items are added/modified in Freshrelease
    and you want to refresh the cache without restarting the server.
    
    Returns:
        Success message or error response
    """
    try:
        _clear_lookup_cache()
        return {"message": "Lookup cache cleared successfully"}
    except Exception as e:
        return create_error_response(f"Failed to clear lookup cache: {str(e)}")

async def fr_clear_resolution_cache() -> Any:
    """Clear the resolution cache for name-to-ID lookups.
    
    This is useful when you want to refresh resolved IDs
    without restarting the server.
    
    Returns:
        Success message or error response
    """
    try:
        _clear_resolution_cache()
        return {"message": "Resolution cache cleared successfully"}
    except Exception as e:
        return create_error_response(f"Failed to clear resolution cache: {str(e)}")


@performance_monitor("fr_save_filter")
async def fr_save_filter(
    label: str,
    query_hash: List[Dict[str, Any]],
    project_identifier: Optional[Union[int, str]] = None,
    private_filter: bool = True,
    quick_filter: bool = False
) -> Any:
    """Save a filter using query_hash from a previous fr_filter_tasks call.
    
    This tool allows you to create and save custom filters that can be reused.
    It uses the same filter logic as fr_filter_tasks but saves the filter instead of executing it.
    
    Args:
        label: Name for the saved filter
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        query: Filter query in string or dict format (optional)
        query_format: Format of the query string ("comma_separated" or "json")
        status_id: Filter by status ID or name (optional)
        priority_id: Filter by priority ID (optional)
        owner_id: Filter by owner ID, name, or email (optional)
        issue_type_id: Filter by issue type ID or name (optional)
        project_id: Filter by project ID or key (optional)
        story_points: Filter by story points (optional)
        sprint_id: Filter by sprint ID or name (optional)
        start_date: Filter by start date (YYYY-MM-DD format) (optional)
        due_by: Filter by due date (YYYY-MM-DD format) (optional)
        release_id: Filter by release ID or name (optional)
        tags: Filter by tags (string or array) (optional)
        document_ids: Filter by document IDs (string or array) (optional)
        parent_id: Filter by parent issue ID or key (optional)
        epic_id: Filter by epic ID or key (optional)
        sub_project_id: Filter by subproject ID or name (optional)
        effort_value: Filter by effort value (optional)
        duration_value: Filter by duration value (optional)
        private_filter: Whether the filter is private (default: True)
        quick_filter: Whether the filter is a quick filter (default: False)
    
    Returns:
        Success response with saved filter details or error response
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        project_id = get_project_identifier(project_identifier)
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        client = get_http_client()

        # Create the filter payload
        filter_payload = {
            "issue_filter": {
                "label": label,
                "query_hash": query_hash,
                "private_filter": private_filter,
                "quick_filter": quick_filter
            }
        }

        # Save the filter
        url = f"{base_url}/{project_id}/issue_filters"
        return await make_api_request("POST", url, headers, json_data=filter_payload, client=client)

    except Exception as e:
        return create_error_response(f"Failed to save filter: {str(e)}")


async def _get_testcase_fields_mapping(
    project_identifier: Optional[Union[int, str]] = None
) -> Dict[str, Any]:
    """Get testcase field label to condition name mapping and custom fields.
    
    Returns:
        Dictionary with field_label_to_condition_map, custom_fields, and metadata
    """
    try:
        # Get testcase form fields
        form_result = await fr_get_testcase_form_fields(project_identifier)
        if "error" in form_result:
            return form_result
        
        # Extract fields from the form
        form_data = form_result.get("form", {})
        fields = form_data.get("fields", [])
        
        # Create label to condition name mapping for testcases
        field_label_to_condition_map = {}
        custom_fields = []
        
        for field in fields:
            field_name = field.get("name", "")
            field_label = field.get("label", "")
            is_default = field.get("default", False)
            field_type = field.get("type", "")
            
            if field_label and field_name:
                # Map specific fields to their filter condition names
                if field_name == "severity":
                    condition_name = "severity_id"
                elif field_name == "section":
                    condition_name = "section_id"
                elif field_name == "test_case_type":
                    condition_name = "type_id"
                elif field_name == "issues":
                    condition_name = "issue_ids"
                else:
                    # For other fields, use the field name as condition name
                    condition_name = field_name
                
                field_label_to_condition_map[field_label.lower()] = condition_name
                
                # Identify custom fields (non-default fields)
                if not is_default:
                    custom_fields.append({
                        "name": field_name,
                        "label": field_label,
                        "type": field_type,
                        "condition": condition_name
                    })
        
        return {
            "field_label_to_condition_map": field_label_to_condition_map,
            "custom_fields": custom_fields,
            "form_data": form_data,
            "total_fields": len(fields)
        }
        
    except Exception as e:
        return {"error": f"Failed to get testcase fields mapping: {str(e)}"}


def _generate_epic_insights(epic_details: Dict[str, Any], child_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate comprehensive AI insights for an epic and its child tasks.
    
    Args:
        epic_details: Epic/parent task details
        child_tasks: List of detailed child task objects
        
    Returns:
        Dictionary containing comprehensive epic insights and analysis
    """
    total_tasks = len(child_tasks)
    
    if total_tasks == 0:
        return {
            "summary": "This epic has no child tasks yet.",
            "total_tasks": 0,
            "insights": ["Consider breaking down the epic into actionable tasks."],
            "recommendations": ["Define clear deliverables and create corresponding tasks."],
            "risk_factors": ["No tasks defined - epic scope unclear"]
        }
    
    # Initialize analysis counters
    status_counts = {}
    priority_counts = {}
    assignee_counts = {}
    git_pr_info = {"open_prs": 0, "merged_prs": 0, "branches": [], "commits": []}
    date_info = {"start_dates": [], "due_dates": [], "creation_dates": []}
    effort_info = {"story_points": 0, "estimated_hours": 0}
    
    # Analyze each task in detail
    for task in child_tasks:
        task_data = task.get("issue", {}) if "issue" in task else task
        
        # Status analysis
        status = task_data.get("status", {})
        status_name = status.get("name", "Unknown") if isinstance(status, dict) else str(status)
        status_counts[status_name] = status_counts.get(status_name, 0) + 1
        
        # Priority analysis
        priority = task_data.get("priority", {})
        priority_name = priority.get("name", "Unknown") if isinstance(priority, dict) else str(priority)
        priority_counts[priority_name] = priority_counts.get(priority_name, 0) + 1
        
        # Assignee analysis
        owner = task_data.get("owner", {})
        owner_name = owner.get("name", "Unassigned") if isinstance(owner, dict) else "Unassigned"
        assignee_counts[owner_name] = assignee_counts.get(owner_name, 0) + 1
        
        # Git/PR analysis from custom fields and description
        custom_fields = task_data.get("custom_field", {})
        description = task_data.get("description", "")
        
        # Look for PR references in description and custom fields
        import re
        pr_patterns = [
            r'PR[:\s#]*(\d+)',
            r'pull request[:\s#]*(\d+)',
            r'github\.com/[^/]+/[^/]+/pull/(\d+)',
            r'\/pull\/(\d+)'
        ]
        
        for pattern in pr_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                if "open" in description.lower() or "pending" in description.lower():
                    git_pr_info["open_prs"] += 1
                else:
                    git_pr_info["merged_prs"] += 1
        
        # Look for branch references
        branch_patterns = [
            r'branch[:\s]*([a-zA-Z0-9\-_/]+)',
            r'feature/([a-zA-Z0-9\-_/]+)',
            r'bugfix/([a-zA-Z0-9\-_/]+)'
        ]
        
        for pattern in branch_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            git_pr_info["branches"].extend(matches)
        
        # Date analysis
        if task_data.get("start_date"):
            date_info["start_dates"].append(task_data["start_date"])
        if task_data.get("due_by"):
            date_info["due_dates"].append(task_data["due_by"])
        if task_data.get("created_at"):
            date_info["creation_dates"].append(task_data["created_at"])
        
        # Effort analysis
        story_points = task_data.get("story_points", 0) or 0
        effort_info["story_points"] += story_points
        
        # Look for time estimates in custom fields
        for field_name, field_value in custom_fields.items():
            if "hour" in field_name.lower() or "time" in field_name.lower():
                if isinstance(field_value, (int, float)):
                    effort_info["estimated_hours"] += field_value
    
    # Calculate completion rate
    completed_statuses = ["done", "completed", "resolved", "closed", "finished"]
    completed_tasks = sum(count for status, count in status_counts.items() 
                        if any(comp in status.lower() for comp in completed_statuses))
    completion_rate = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 0
    
    # Calculate timeline insights
    timeline_insights = {}
    if date_info["start_dates"]:
        earliest_start = min(date_info["start_dates"])
        timeline_insights["earliest_start"] = earliest_start
    if date_info["due_dates"]:
        latest_due = max(date_info["due_dates"])
        timeline_insights["latest_due"] = latest_due
    if date_info["creation_dates"]:
        first_created = min(date_info["creation_dates"])
        latest_created = max(date_info["creation_dates"])
        timeline_insights["creation_span"] = {"first": first_created, "latest": latest_created}
    
    # Generate insights
    insights = []
    recommendations = []
    risk_factors = []
    
    # Completion insights
    if completion_rate < 25:
        insights.append(f"Epic is in early stages with {completion_rate:.1f}% completion rate.")
        recommendations.append("Focus on task prioritization and clear requirements.")
    elif completion_rate < 75:
        insights.append(f"Epic is progressing well with {completion_rate:.1f}% completion rate.")
        recommendations.append("Monitor blockers and maintain development momentum.")
    else:
        insights.append(f"Epic is nearly complete with {completion_rate:.1f}% completion rate.")
        recommendations.append("Focus on final testing and deployment preparation.")
    
    # Team distribution insights
    if len(assignee_counts) == 1 and "Unassigned" not in assignee_counts:
        insights.append("Epic is handled by a single developer.")
        risk_factors.append("Single point of failure - no backup coverage")
        recommendations.append("Consider involving additional team members for knowledge sharing.")
    elif len(assignee_counts) > 5:
        insights.append(f"Epic involves {len(assignee_counts)} team members.")
        risk_factors.append("High coordination overhead with many contributors")
        recommendations.append("Ensure clear communication channels and regular sync-ups.")
    elif "Unassigned" in assignee_counts and assignee_counts["Unassigned"] > total_tasks * 0.3:
        unassigned_pct = (assignee_counts["Unassigned"] / total_tasks) * 100
        insights.append(f"{unassigned_pct:.1f}% of tasks are unassigned.")
        risk_factors.append("High number of unassigned tasks may cause delays")
        recommendations.append("Assign ownership to all tasks for better accountability.")
    
    # Git/PR insights  
    if git_pr_info["open_prs"] > 0:
        insights.append(f"Found {git_pr_info['open_prs']} open pull requests in development.")
        if git_pr_info["open_prs"] > 3:
            risk_factors.append("High number of open PRs may indicate review bottlenecks")
            recommendations.append("Prioritize code reviews to prevent merge conflicts.")
    
    if git_pr_info["merged_prs"] > 0:
        insights.append(f"Development is active with {git_pr_info['merged_prs']} merged pull requests.")
        
    # Priority distribution insights
    high_priority_tasks = priority_counts.get("High", 0) + priority_counts.get("Critical", 0)
    if high_priority_tasks > total_tasks * 0.5:
        insights.append("Over half the tasks are high/critical priority.")
        risk_factors.append("Too many high-priority tasks may indicate scope creep")
        recommendations.append("Re-evaluate task priorities and consider epic scope reduction.")
    
    # Timeline risk assessment
    if timeline_insights.get("latest_due"):
        from datetime import datetime, timezone
        try:
            due_date = datetime.fromisoformat(timeline_insights["latest_due"].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            days_remaining = (due_date - now).days
            
            if days_remaining < 0:
                risk_factors.append(f"Epic is overdue by {abs(days_remaining)} days")
                recommendations.append("Immediate attention required - reassess scope and resources.")
            elif days_remaining < 7:
                risk_factors.append(f"Epic due in {days_remaining} days with {completion_rate:.1f}% completion")
                recommendations.append("Consider scope reduction or deadline extension.")
        except Exception:
            pass
    
    # Generate summary
    summary_parts = [f"Epic contains {total_tasks} tasks with {completion_rate:.1f}% completion rate."]
    if len(assignee_counts) > 1:
        summary_parts.append(f"Work is distributed across {len(assignee_counts)} team members.")
    if git_pr_info["open_prs"] > 0:
        summary_parts.append(f"{git_pr_info['open_prs']} pull requests are currently open.")
    
    return {
        "summary": " ".join(summary_parts),
        "total_tasks": total_tasks,
        "completion_rate": f"{completion_rate:.1f}%",
        "insights": insights,
        "recommendations": recommendations,
        "risk_factors": risk_factors,
        "metrics": {
            "status_distribution": status_counts,
            "priority_distribution": priority_counts,
            "assignee_distribution": assignee_counts,
            "git_development": git_pr_info,
            "effort_summary": effort_info,
            "timeline": timeline_insights
        }
    }


def _generate_testrun_insights(test_run: Dict[str, Any], users: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate simplified AI insights for a test run.
    
    Args:
        test_run: Test run data from API
        users: List of users associated with the test run
        
    Returns:
        Dictionary containing streamlined test run insights
    """
    progress = test_run.get("progress", {})
    total_tests = sum(progress.values())
    
    if total_tests == 0:
        return {
            "summary": "Empty test run - no test cases added yet.",
            "quality_score": "No Data",
            "recommendations": ["Add test cases to begin quality assessment"]
        }
    
    # Core metrics
    passed = progress.get("passed", 0)
    failed = progress.get("failed", 0)
    blocked = progress.get("blocked", 0)
    not_run = progress.get("not_run", 0)
    
    executed = passed + failed
    pass_rate = (passed / total_tests) * 100 if total_tests > 0 else 0
    completion_rate = (executed / total_tests) * 100 if total_tests > 0 else 0
    
    # Quality assessment
    if completion_rate >= 90:
        if pass_rate >= 95:
            quality_score = "Excellent"
        elif pass_rate >= 85:
            quality_score = "Good"
        elif pass_rate >= 70:
            quality_score = "Fair"
        else:
            quality_score = "Poor"
    else:
        quality_score = "In Progress"
    
    # Generate concise summary
    if completion_rate == 100:
        if failed == 0:
            summary = f"All {total_tests} tests passed successfully! 🎉"
        else:
            summary = f"{passed}/{total_tests} tests passed ({pass_rate:.0f}%). {failed} failures need attention."
    else:
        summary = f"{executed}/{total_tests} tests executed ({completion_rate:.0f}% complete). {passed} passed, {failed} failed."
    
    # Key recommendations
    recommendations = []
    if failed > 0:
        recommendations.append(f"Fix {failed} failing test cases")
    if blocked > 0:
        recommendations.append(f"Resolve {blocked} blocked tests")
    if not_run > 0 and completion_rate < 100:
        recommendations.append(f"Execute remaining {not_run} test cases")
    if not recommendations:
        recommendations.append("Test run is progressing well")
    
    # Get team info efficiently
    creator_name = "Unknown"
    if users and test_run.get("creator_id"):
        creator = next((u.get("name") for u in users if u.get("id") == test_run.get("creator_id")), None)
        if creator:
            creator_name = creator
    
    return {
        "summary": summary,
        "quality_score": quality_score,
        "recommendations": recommendations,
        "metrics": {
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "blocked": blocked,
            "not_run": not_run,
            "pass_rate": f"{pass_rate:.1f}%",
            "completion_rate": f"{completion_rate:.1f}%"
        },
        "created_by": creator_name
    }


def _add_ai_summary_to_testcase_result(result: Dict[str, Any], filter_criteria: Dict[str, Any]) -> Dict[str, Any]:
    """Add AI summary to testcase API result.
    
    Args:
        result: API response containing test cases
        filter_criteria: Applied filter criteria for context
        
    Returns:
        Enhanced result with AI summary or original result if error
    """
    if "error" in result:
        return result
        
    test_cases = result.get("test_cases", [])
    ai_summary = _generate_testcase_summary(test_cases, filter_criteria)
    
    return {
        "test_cases": test_cases,
        "ai_summary": ai_summary,
        "original_response": result
    }


def _generate_testcase_summary(test_cases: List[Dict[str, Any]], filter_criteria: Dict[str, Any]) -> Dict[str, Any]:
    """Generate AI-powered summary of filtered test cases.
    
    Args:
        test_cases: List of filtered test case objects
        filter_criteria: Applied filter criteria for context
        
    Returns:
        Dictionary containing comprehensive summary and insights
    """
    if not test_cases:
        return {
            "summary": "No test cases found matching the specified criteria.",
            "total_count": 0,
            "insights": ["Consider broadening your filter criteria to find relevant test cases."],
            "recommendations": ["Review section structure and test case organization."]
        }
    
    total_count = len(test_cases)
    
    # Analyze test case distribution
    severity_counts = {}
    section_counts = {}
    creator_counts = {}
    status_counts = {}
    automation_status = {"automated": 0, "manual": 0, "not_specified": 0}
    
    for tc in test_cases:
        # Severity analysis
        severity_id = tc.get("severity_id")
        if severity_id:
            severity_counts[severity_id] = severity_counts.get(severity_id, 0) + 1
        
        # Section analysis  
        section_id = tc.get("section_id")
        if section_id:
            section_counts[section_id] = section_counts.get(section_id, 0) + 1
            
        # Creator analysis
        creator_id = tc.get("creator_id")
        if creator_id:
            creator_counts[creator_id] = creator_counts.get(creator_id, 0) + 1
            
        # Status analysis
        status_id = tc.get("test_case_status_id")
        if status_id:
            status_counts[status_id] = status_counts.get(status_id, 0) + 1
            
        # Automation analysis from custom fields
        custom_fields = tc.get("custom_field", {})
        automation = custom_fields.get("cf_automation_status", "").lower()
        if "automated" in automation:
            automation_status["automated"] += 1
        elif "manual" in automation or "not automated" in automation:
            automation_status["manual"] += 1
        else:
            automation_status["not_specified"] += 1
    
    # Generate insights based on analysis
    insights = []
    recommendations = []
    
    # Coverage insights
    if total_count < 10:
        insights.append(f"Limited test coverage with only {total_count} test cases.")
        recommendations.append("Consider expanding test case coverage for better quality assurance.")
    elif total_count > 100:
        insights.append(f"Comprehensive test suite with {total_count} test cases.")
        recommendations.append("Consider organizing test cases into logical groups for better maintainability.")
    
    # Automation insights
    automation_rate = (automation_status["automated"] / total_count) * 100 if total_count > 0 else 0
    if automation_rate < 30:
        insights.append(f"Low automation rate ({automation_rate:.1f}%). Most tests are manual.")
        recommendations.append("Prioritize test automation to improve execution efficiency.")
    elif automation_rate > 70:
        insights.append(f"High automation rate ({automation_rate:.1f}%). Well-automated test suite.")
        recommendations.append("Maintain automation coverage and keep tests up-to-date.")
    
    # Distribution insights
    if len(section_counts) == 1:
        insights.append("Test cases are concentrated in a single section.")
        recommendations.append("Ensure test coverage across different application areas.")
    elif len(section_counts) > 5:
        insights.append(f"Test cases span across {len(section_counts)} different sections.")
        recommendations.append("Review section organization for optimal test management.")
    
    # Creator diversity
    if len(creator_counts) == 1:
        insights.append("All test cases created by a single person.")
        recommendations.append("Encourage team collaboration in test case creation.")
    elif len(creator_counts) > 5:
        insights.append(f"Test cases created by {len(creator_counts)} different team members.")
        recommendations.append("Maintain consistent quality standards across different creators.")
    
    # Generate summary text
    summary_parts = [f"Found {total_count} test cases matching your criteria."]
    
    if automation_status["automated"] > 0:
        summary_parts.append(f"{automation_status['automated']} are automated")
    if automation_status["manual"] > 0:
        summary_parts.append(f"{automation_status['manual']} are manual")
    
    summary = " ".join(summary_parts) + "."
    
    # Risk assessment
    risk_factors = []
    if automation_rate < 50:
        risk_factors.append("Low automation coverage may impact release velocity")
    if len(creator_counts) == 1:
        risk_factors.append("Single point of knowledge risk")
    if total_count < 5:
        risk_factors.append("Insufficient test coverage")
        
    return {
        "summary": summary,
        "total_count": total_count,
        "insights": insights,
        "recommendations": recommendations,
        "risk_factors": risk_factors,
        "metrics": {
            "automation_rate": f"{automation_rate:.1f}%",
            "sections_covered": len(section_counts),
            "contributors": len(creator_counts),
            "status_distribution": len(status_counts)
        },
        "filter_applied": filter_criteria
    }


def _add_query_hash_value(params: Dict[str, Any], index: int, value: Any) -> None:
    """Helper function to add query_hash values, handling both single and array values.
    
    Args:
        params: Parameters dictionary to update
        index: Query hash index 
        value: Value to add (can be single value or array)
    """
    if isinstance(value, list):
        # For arrays, use query_hash[i][value][] format and store as list
        key = f"query_hash[{index}][value][]"
        params[key] = value
    else:
        # For single values, use query_hash[i][value] format
        params[f"query_hash[{index}][value]"] = value


async def _resolve_testcase_field_value(
    condition: str, 
    value: Any, 
    project_id: Union[int, str],
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str],
    severity_options: Optional[Dict[str, int]] = None,
    section_options: Optional[Dict[str, int]] = None
) -> Any:
    """Resolve testcase field values to IDs if needed.
    
    Args:
        condition: The field condition (e.g., "creator_id", "section_id")
        value: The value to resolve
        project_id: Resolved project ID
        client: HTTP client instance
        base_url: API base URL
        headers: Request headers
        severity_options: Optional mapping of severity names to IDs from form fields
        section_options: Optional mapping of section names to IDs from form fields
        
    Returns:
        Resolved value or original value if no resolution needed
    """
    try:
        # Fields that need resolution
        if condition == "creator_id" and isinstance(value, str) and not value.isdigit():
            # Resolve user name/email to ID
            logging.info(f"Resolving creator '{value}' to user ID")
            user_result = await _resolve_user_name_to_id(value, project_id, client, base_url, headers)
            if user_result and isinstance(user_result, int):
                logging.info(f"Resolved creator '{value}' to ID {user_result}")
                return user_result
        elif condition == "severity_id" and isinstance(value, str) and severity_options and value.lower() in severity_options:
            # Use explicit severity mapping from form fields (preferred method)
            resolved_id = severity_options[value.lower()]
            logging.info(f"Resolved severity '{value}' to ID {resolved_id} using form fields")
            return resolved_id
        elif condition == "section_id" and isinstance(value, str) and not value.isdigit():
            # First try explicit section options if available, then fall back to generic resolution
            if section_options and value.lower() in section_options:
                resolved_id = section_options[value.lower()]
                logging.info(f"Resolved section '{value}' to ID {resolved_id} using form fields")
                return resolved_id
            else:
                # Fall back to generic section resolution
                section_result = await _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "sections")
                if section_result and isinstance(section_result, (int, dict)):
                    resolved_id = section_result.get("id", section_result) if isinstance(section_result, dict) else section_result
                    logging.info(f"Resolved section '{value}' to ID {resolved_id} using generic resolution")
                    return resolved_id
        elif condition == "test_case_type_id" and isinstance(value, str) and not value.isdigit():
            # Resolve test case type name to ID
            type_result = await _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "test_case_types")
            if type_result and isinstance(type_result, (int, dict)):
                resolved_id = type_result.get("id", type_result) if isinstance(type_result, dict) else type_result
                logging.info(f"Resolved test case type '{value}' to ID {resolved_id}")
                return resolved_id
        
        # Return original value if no resolution needed
        return value
        
    except Exception as e:
        logging.warning(f"Failed to resolve testcase field '{condition}' value '{value}': {str(e)}")
        # Return original value if resolution fails
        return value


@mcp.tool()
@performance_monitor("fr_testcase_filter_summary")
async def fr_testcase_filter_summary(
    project_identifier: Optional[Union[int, str]] = None,
    filter_rules: Optional[List[Dict[str, Any]]] = None,
    query: Optional[Union[str, Dict[str, Any]]] = None,
    query_format: str = "comma_separated",
    query_hash: Optional[List[Dict[str, Any]]] = None,
    
    # Additional API parameters
    filter_id: Optional[Union[int, str]] = None,
    include: Optional[str] = None,
    page: Optional[int] = 1,
    per_page: Optional[int] = 30,
    sort: Optional[str] = "created_at",
    sort_type: Optional[str] = "asc",
    test_run_id: Optional[Union[int, str]] = None
) -> Any:
    """Filter test cases and generate AI-powered summary with automatic label-to-condition and name-to-ID resolution.
    
    This tool filters test cases by various criteria and provides intelligent insights, recommendations,
    and risk assessment based on the filtered results. Supports native query_hash format for optimal performance.
    
    Field Label Support:
    - "Pre-requisite": Maps to pre_requisite condition  
    - "Steps to Execute": Maps to steps condition
    - "Expected Results": Maps to expected_results condition
    - "Severity": Maps to severity_id condition
    - "Section": Maps to section_id condition
    - "Type": Maps to test_case_type_id condition
    - "Creator": Maps to creator_id condition
    - "Status": Maps to test_case_status_id condition
    
    Automatic Name-to-ID Resolution:
    - section_id: Resolves section names to IDs
    - test_case_type_id: Resolves test case type names to IDs
    - creator_id: Resolves user names/emails to IDs
    - Custom fields: Resolves custom field values to IDs
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        filter_rules: List of filter rule objects with condition, operator, and value (legacy format)
        query: Filter query in JSON string or comma-separated format (optional)
        query_format: Format of the query - "comma_separated" or "json" (default: "comma_separated")
        query_hash: Native query_hash format for filtering (preferred) - preserves original structure including duplicates
        filter_id: Saved filter ID to apply (defaults to 1 if not provided)
        include: Fields to include in response (e.g., "custom_field")
        page: Page number for pagination (default: 1)
        per_page: Number of items per page (default: 30)
        sort: Field to sort by (e.g., "created_at", "updated_at", "id")
        sort_type: Sort direction ("asc" or "desc")
        test_run_id: Test run ID for filtering test cases within a specific test run
    
    Returns:
        Dictionary containing filtered test cases with AI-generated summary, insights, and recommendations
        
    Examples:
        # Get test case summary with AI insights
        fr_testcase_filter_summary(query="Section:Authentication,Creator:John Doe")
        
        # Returns: {
        #   "test_cases": [...],
        #   "ai_summary": {
        #     "summary": "Found 25 test cases. 15 are automated, 10 are manual.",
        #     "insights": ["High automation rate (60%). Well-automated test suite."],
        #     "recommendations": ["Maintain automation coverage and keep tests up-to-date."],
        #     "metrics": {"automation_rate": "60.0%", "sections_covered": 3}
        #   }
        # }
        
        # Complex filtering with summary insights
        fr_testcase_filter_summary(
            query_hash=[
                {"condition": "severity_id", "operator": "is_in", "value": [17, 16]},
                {"condition": "creator_id", "operator": "is_in", "value": [50624]}
            ],
            include="custom_field"
        )
    """
    try:
        # Validate environment variables and initialize API objects once
        env_data = validate_environment()
        project_id = get_project_identifier(project_identifier)
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        client = get_http_client()
        
        logging.info("=== Starting testcase filter summary with explicit field mapping ===")
        
        # Step 1: Get testcase form fields to understand field name-to-ID mappings
        logging.info("Step 1: Getting testcase form fields for field mapping")
        form_fields_result = await fr_get_testcase_form_fields(project_identifier)
        if "error" in form_fields_result:
            return form_fields_result
            
        # Extract field mappings from form fields
        form_data = form_fields_result.get("form", {})
        fields_list = form_data.get("fields", [])
        
        # Build comprehensive field mappings
        field_label_to_condition_map = {}
        field_name_to_id_map = {}
        severity_options = {}
        section_options = {}
        creator_options = {}
        
        logging.info(f"Found {len(fields_list)} testcase form fields")
        
        for field in fields_list:
            field_name = field.get("name", "")
            field_label = field.get("label", "")
            field_choices = field.get("choices", [])
            
            if field_label and field_name:
                # Map field labels to their condition names for filtering
                if field_name == "severity":
                    condition_name = "severity_id"
                    # Extract severity options for name-to-ID resolution
                    for choice in field_choices:
                        severity_options[choice.get("label", "").lower()] = choice.get("id")
                elif field_name == "section":
                    condition_name = "section_id"
                    # Extract section options for name-to-ID resolution
                    for choice in field_choices:
                        section_options[choice.get("label", "").lower()] = choice.get("id")
                elif field_name == "test_case_type":
                    condition_name = "test_case_type_id"
                elif field_name == "test_case_status":
                    condition_name = "test_case_status_id"
                elif field_name == "creator":
                    condition_name = "creator_id"
                else:
                    condition_name = field_name
                
                field_label_to_condition_map[field_label.lower()] = condition_name
                field_name_to_id_map[field_name] = condition_name
                
                logging.info(f"Mapped field '{field_label}' -> '{condition_name}'")
        
        # Step 2: Build comprehensive user mapping for creator_id resolution
        logging.info("Step 2: Preparing user resolution for creator_id fields")
        

        # Build base parameters
        params = {}
        
        # Add pagination and sorting parameters
        if page:
            params["page"] = page
        if per_page:
            params["per_page"] = per_page
        if sort:
            params["sort"] = sort
        if sort_type:
            params["sort_type"] = sort_type
        # Only add include parameter if explicitly provided (not None and not empty)
        if include is not None and include.strip():
            params["include"] = include
        if test_run_id:
            params["test_run_id"] = test_run_id
        
        # Always set filter_id to 1 for test case filtering as requested
        params["filter_id"] = filter_id if filter_id else 1

        # Handle comma-separated or JSON query format (only if query is provided and not empty)
        if query and str(query).strip():
            logging.info("Step 3: Processing query using form field mappings")
            
            # Build custom fields list for processing
            custom_fields = []
            for field in fields_list:
                if not field.get("default", False):  # Non-default fields are custom
                    custom_fields.append({
                        "name": field.get("name", ""),
                        "label": field.get("label", ""),
                        "type": field.get("type", ""),
                        "condition": field_name_to_id_map.get(field.get("name", ""), field.get("name", ""))
                    })
            
            # Parse query based on format
            if query_format == "json":
                if isinstance(query, str):
                    import json
                    query_dict = json.loads(query)
                else:
                    query_dict = query
                query_pairs = list(query_dict.items())
            else:
                # Comma-separated format (only process if applicable)
                processed_query_str = process_query_with_custom_fields(query, custom_fields)
                query_pairs = parse_query_string(processed_query_str)
                
                # Skip processing if no valid query pairs found
                if not query_pairs:
                    logging.info(f"No valid query pairs found in: '{query}' - skipping comma-separated processing")
                    # Continue to other filtering methods
                else:
                    logging.info(f"Processing {len(query_pairs)} comma-separated testcase query pairs: {query_pairs}")
            
            # Convert query_pairs to query_hash format (only if we have valid pairs)
            query_hash_items = []
            if query_pairs:
                for i, (field, value) in enumerate(query_pairs):
                    # Map field label to condition name if needed (case-insensitive)
                    field_lower = field.lower()
                    if field_lower in field_label_to_condition_map:
                        original_field = field
                        field = field_label_to_condition_map[field_lower]
                        logging.info(f"Mapped testcase field label '{original_field}' to condition name '{field}'")
                    else:
                        logging.info(f"Testcase field '{field}' not found in label mapping, using as-is")
                    
                    # Determine operator based on value type
                    if isinstance(value, list):
                        operator = "is_in"
                    else:
                        operator = "is"
                    
                    query_hash_items.append({
                        "condition": field,
                        "operator": operator,
                        "value": value
                    })
            
            # Build query_hash parameters (only if we have items to process)
            if query_hash_items:
                for i, query_item in enumerate(query_hash_items):
                    condition = query_item.get("condition")
                    operator = query_item.get("operator")
                    value = query_item.get("value")
                    
                    if condition and operator and value is not None:
                        params[f"query_hash[{i}][condition]"] = condition
                        params[f"query_hash[{i}][operator]"] = operator
                        
                        # Step 4: Resolve values to IDs using enhanced field mappings
                        final_value = await _resolve_testcase_field_value(
                            condition, value, project_id, client, base_url, headers,
                            severity_options, section_options
                        )
                        
                        # Handle array values using helper function
                        _add_query_hash_value(params, i, final_value)
                
                # Make API request with converted query
                url = f"{base_url}/{project_id}/test_cases"
                result = await make_api_request("GET", url, headers, params=params, client=client)
                
                # Add AI summary to the result
                filter_criteria = {
                    "query": query,
                    "query_format": query_format,
                    "page": page,
                    "per_page": per_page
                }
                return _add_ai_summary_to_testcase_result(result, filter_criteria)

        # Handle native query_hash format (highest priority)
        if query_hash:
            # Process query_hash entries as-is, preserving original structure including duplicates
            for i, query_item in enumerate(query_hash):
                condition = query_item.get("condition")
                operator = query_item.get("operator")
                value = query_item.get("value")
                
                if condition and operator and value is not None:
                    params[f"query_hash[{i}][condition]"] = condition
                    params[f"query_hash[{i}][operator]"] = operator
                    
                    # Resolve values to IDs using enhanced field mappings
                    final_value = await _resolve_testcase_field_value(
                        condition, value, project_id, client, base_url, headers,
                        severity_options, section_options
                    )
                    
                    # Handle array values using helper function
                    _add_query_hash_value(params, i, final_value)
            
            # Make API request with query_hash
            url = f"{base_url}/{project_id}/test_cases"
            result = await make_api_request("GET", url, headers, params=params, client=client)
            
            # Add AI summary to the result
            filter_criteria = {
                "query_hash": query_hash,
                "page": page,
                "per_page": per_page
            }
            return _add_ai_summary_to_testcase_result(result, filter_criteria)

        # Handle legacy filter_rules format (convert to query_hash)
        if not filter_rules:
            # No filtering criteria provided, return all test cases with pagination/sorting
            url = f"{base_url}/{project_id}/test_cases"
            result = await make_api_request("GET", url, headers, params=params, client=client)
            
            # Add AI summary to the result
            filter_criteria = {
                "filter_type": "all_testcases",
                "page": page,
                "per_page": per_page
            }
            return _add_ai_summary_to_testcase_result(result, filter_criteria)

        # Convert filter_rules to query_hash format using explicit field mappings
        logging.info("Step 5: Processing filter_rules using explicit field mappings")
        for i, rule in enumerate(filter_rules):
            if isinstance(rule, dict) and all(key in rule for key in ["condition", "operator", "value"]):
                condition = rule["condition"]
                operator = rule["operator"]
                value = rule["value"]
                
                # Map field label to condition name if needed (case-insensitive)
                condition_lower = condition.lower()
                if condition_lower in field_label_to_condition_map:
                    original_condition = condition
                    condition = field_label_to_condition_map[condition_lower]
                    logging.info(f"Mapped testcase filter_rules condition '{original_condition}' to '{condition}'")
                
                params[f"query_hash[{i}][condition]"] = condition
                params[f"query_hash[{i}][operator]"] = operator
                
                # Resolve values to IDs using enhanced field mappings
                final_value = await _resolve_testcase_field_value(
                    condition, value, project_id, client, base_url, headers,
                    severity_options, section_options
                )
                
                # Handle array values using helper function
                _add_query_hash_value(params, i, final_value)

        # Step 6: Make the testcase filter API request
        logging.info("Step 6: Making API request to fetch filtered testcases")
        url = f"{base_url}/{project_id}/test_cases"
        result = await make_api_request("GET", url, headers, params=params, client=client)
        
        # Add AI summary to the result
        filter_criteria = {
            "filter_rules": filter_rules,
            "page": page,
            "per_page": per_page
        }
        return _add_ai_summary_to_testcase_result(result, filter_criteria)

    except Exception as e:
        return create_error_response(f"Failed to filter test cases: {str(e)}")


@mcp.tool()
@performance_monitor("fr_get_issue_form_fields")
async def fr_get_issue_form_fields(
    project_identifier: Optional[Union[int, str]] = None,
    issue_type_id: Optional[Union[int, str]] = None
) -> Any:
    """Get available fields and their possible values for issue creation and filtering.
    
    This tool returns the form fields that can be used for creating issues and filtering.
    It shows both standard fields and custom fields available for the project.
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        issue_type_id: Issue type ID or name to get specific form fields (optional)
    
    Returns:
        Form fields data with available fields and their possible values
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        if "error" in env_data:
            return env_data
        
        project_id = get_project_identifier(project_identifier)
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        client = get_http_client()

        # Get issue form fields
        url = f"{base_url}/{project_id}/issues/form"
        
        # Add issue type parameter if provided
        params = {}
        if issue_type_id:
            # Resolve issue type name to ID if needed
            if isinstance(issue_type_id, str) and not issue_type_id.isdigit():
                issue_type_data = await _resolve_name_to_id_generic(
                    issue_type_id, project_id, client, base_url, headers, "issue_types"
                )
                if isinstance(issue_type_data, dict) and "id" in issue_type_data:
                    params["issue_type_id"] = issue_type_data["id"]
                else:
                    return create_error_response(f"Could not resolve issue type '{issue_type_id}' to ID")
            else:
                params["issue_type_id"] = issue_type_id
        
        return await make_api_request("GET", url, headers, client=client, params=params)

    except Exception as e:
        return create_error_response(f"Failed to get issue form fields: {str(e)}")


@mcp.tool()
@performance_monitor("fr_get_testcase_form_fields")
async def fr_get_testcase_form_fields(
    project_identifier: Optional[Union[int, str]] = None
) -> Any:
    """Get available fields and their possible values for test case filtering.
    
    This tool returns the form fields that can be used in test case filter rules.
    Use this to understand what fields are available and their possible values.
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
    
    Returns:
        Form fields data with available filter conditions and their possible values
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        if "error" in env_data:
            return env_data
        
        project_id = get_project_identifier(project_identifier)
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        client = get_http_client()

        # Get test case form fields
        url = f"{base_url}/{project_id}/forms/project_test_case_form"
        return await make_api_request("GET", url, headers, client=client)

    except Exception as e:
        return create_error_response(f"Failed to get test case form fields: {str(e)}")


@mcp.tool()
@performance_monitor("fr_get_all_issue_type_form_fields")
async def fr_get_all_issue_type_form_fields(
    project_identifier: Optional[Union[int, str]] = None
) -> Any:
    """Get form fields for all issue types in a project.
    
    This tool fetches form fields for each issue type in the project, allowing you to see
    what fields are available for different types of issues (Bug, Task, Epic, etc.).
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
    
    Returns:
        Dictionary with issue type names as keys and their form fields as values
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        if "error" in env_data:
            return env_data
        
        project_id = get_project_identifier(project_identifier)
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        client = get_http_client()

        # First, get all issue types
        issue_types_url = f"{base_url}/{project_id}/issue_types"
        issue_types_data = await make_api_request("GET", issue_types_url, headers, client=client)
        
        if not isinstance(issue_types_data, list):
            return create_error_response("Failed to fetch issue types", issue_types_data)
        
        # Get form fields for each issue type
        form_fields_by_type = {}
        
        for issue_type in issue_types_data:
            issue_type_id = issue_type.get("id")
            issue_type_name = issue_type.get("name", f"Type_{issue_type_id}")
            
            if issue_type_id:
                try:
                    form_url = f"{base_url}/{project_id}/issues/form"
                    form_data = await make_api_request(
                        "GET", form_url, headers, client=client, 
                        params={"issue_type_id": issue_type_id}
                    )
                    form_fields_by_type[issue_type_name] = form_data
                except Exception as e:
                    form_fields_by_type[issue_type_name] = {
                        "error": f"Failed to fetch form fields: {str(e)}"
                    }
        
        return {
            "project_id": project_id,
            "issue_types": form_fields_by_type,
            "total_issue_types": len(issue_types_data)
        }

    except Exception as e:
        return create_error_response(f"Failed to get all issue type form fields: {str(e)}")


async def fr_clear_testcase_form_cache() -> Any:
    """Clear the test case form cache.
    
    This is useful when test case form fields are modified in Freshrelease
    and you want to refresh the cache without restarting the server.
    
    Returns:
        Success message or error response
    """
    try:
        global _testcase_form_cache
        _testcase_form_cache.clear()
        return {"success": True, "message": "Test case form cache cleared successfully"}
    except Exception as e:
        return create_error_response(f"Failed to clear test case form cache: {str(e)}")


@mcp.tool()
async def fr_clear_all_caches() -> Any:
    """Clear all caches (custom fields, lookup data, and resolution cache).
    
    This is useful when you want to refresh all cached data
    without restarting the server.
    
    Returns:
        Success message or error response
    """
    try:
        _clear_custom_fields_cache()
        _clear_lookup_cache()
        _clear_resolution_cache()
        
        # Clear test case form cache
        global _testcase_form_cache
        _testcase_form_cache.clear()
        
        return {"message": "All caches cleared successfully"}
    except Exception as e:
        return create_error_response(f"Failed to clear caches: {str(e)}")


@mcp.tool()
@performance_monitor("fr_get_testrun_summary")
async def fr_get_testrun_summary(
    test_run_id: Union[int, str],
    project_identifier: Optional[Union[int, str]] = None
) -> Dict[str, Any]:
    """Get test run summary with simplified AI insights and quality analysis.
    
    Provides concise test run analysis focusing on key metrics, quality score,
    and actionable recommendations.
    
    Args:
        test_run_id: Test run ID (required)
        project_identifier: Project ID or key (optional)
        
    Returns:
        Dictionary containing test run summary with AI insights
        
    Examples:
        # Get test run summary with AI insights
        fr_get_testrun_summary(150183)
        
        # Returns: {
        #   "test_run_id": 150183,
        #   "name": "Sprint 1 Test Run",
        #   "status": "active", 
        #   "ai_insights": {
        #     "summary": "23/25 tests executed (92% complete). 21 passed, 2 failed.",
        #     "quality_score": "Good",
        #     "recommendations": ["Fix 2 failing test cases"]
        #   }
        # }
    """
    try:
        env_data = validate_environment()
        if "error" in env_data:
            return env_data
            
        if not test_run_id:
            return create_error_response("test_run_id is required")
            
        project_id = get_project_identifier(project_identifier)
        url = f"{env_data['base_url']}/{project_id}/test_runs/{test_run_id}"
        
        response = await make_api_request("GET", url, env_data["headers"], client=get_http_client())
        if "error" in response:
            return response
            
        test_run = response.get("test_run", {})
        if not test_run:
            return create_error_response("Test run not found")
            
        users = response.get("users", [])
        
        # Generate AI insights
        ai_insights = _generate_testrun_insights(test_run, users)
        
        # Build streamlined response
        result = {
            "test_run_id": test_run.get("id"),
            "name": test_run.get("name"),
            "status": test_run.get("status"),
            "ai_insights": ai_insights,
            "raw_progress": test_run.get("progress", {})
        }
        
        return result
        
    except Exception as e:
        return create_error_response(f"Failed to get test run summary: {str(e)}")


async def fr_get_performance_stats() -> Dict[str, Any]:
    """Get performance statistics for all monitored functions.
    
    Returns:
        Performance statistics including count, average duration, min/max duration
    """
    try:
        stats = get_performance_stats()
        return {"performance_stats": stats}
    except Exception as e:
        return create_error_response(f"Failed to get performance stats: {str(e)}")


async def fr_clear_performance_stats() -> Dict[str, Any]:
    """Clear performance statistics.
    
    Returns:
        Success message or error response
    """
    try:
        clear_performance_stats()
        return {"message": "Performance statistics cleared successfully"}
    except Exception as e:
        return create_error_response(f"Failed to clear performance stats: {str(e)}")

async def fr_close_http_client() -> Dict[str, Any]:
    """Close the global HTTP client to free resources.
    
    Returns:
        Success message or error response
    """
    try:
        await close_http_client()
        return {"message": "HTTP client closed successfully"}
    except Exception as e:
        return create_error_response(f"Failed to close HTTP client: {str(e)}")


@mcp.tool()
async def fr_add_testcases_to_testrun(
    project_identifier: Optional[Union[int, str]] = None, 
    test_run_id: Union[int, str] = None,
    test_case_keys: Optional[List[Union[str, int]]] = None,
    section_hierarchy_paths: Optional[List[str]] = None,
    section_subtree_ids: Optional[List[Union[str, int]]] = None,
    section_ids: Optional[List[Union[str, int]]] = None,
    filter_rule: Optional[List[Dict[str, Any]]] = None
) -> Any:
    """Add test cases to a test run by resolving test case keys to IDs and section hierarchies to IDs.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        test_run_id: Test run ID (required)
        test_case_keys: List of test case keys/IDs to add (optional)
        section_hierarchy_paths: List of section hierarchy paths like "Parent > Child" (optional)
        section_subtree_ids: List of section subtree IDs (optional)
        section_ids: List of section IDs (optional)
        filter_rule: Filter rules for test case selection (optional)
        
    Returns:
        Test run update result or error response
    """
    try:
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
    except ValueError as e:
        return create_error_response(str(e))

    if test_run_id is None:
        return create_error_response("test_run_id is required")

    async with httpx.AsyncClient() as client:
        try:
            # Resolve test case keys to IDs (if provided)
            resolved_test_case_ids: List[str] = []
            if test_case_keys:
                for key in test_case_keys:
                    tc_url = f"{base_url}/{project_id}/test_cases/{key}"
                    tc_data = await make_api_request("GET", tc_url, headers, client=client)
                    if isinstance(tc_data, dict) and "id" in tc_data:
                        resolved_test_case_ids.append(str(tc_data["id"]))
                    else:
                        return create_error_response(f"Unexpected test case response structure for key '{key}'", tc_data)

            # Resolve section hierarchy paths to IDs
            resolved_section_subtree_ids: List[str] = []
            if section_hierarchy_paths:
                for path in section_hierarchy_paths:
                    section_ids_from_path = await resolve_section_hierarchy_to_ids(client, base_url, project_id, headers, path)
                    resolved_section_subtree_ids.extend([str(sid) for sid in section_ids_from_path])

            # Combine resolved section subtree IDs with any provided directly
            all_section_subtree_ids = resolved_section_subtree_ids + [str(sid) for sid in (section_subtree_ids or [])]

            # Build payload with resolved IDs
            payload = {
                "filter_rule": filter_rule or [],
                "test_case_ids": resolved_test_case_ids,
                "section_subtree_ids": all_section_subtree_ids,
                "section_ids": [str(sid) for sid in (section_ids or [])]
            }

            # Make the PUT request
            url = f"{base_url}/{project_id}/test_runs/{test_run_id}/test_cases"
            return await make_api_request("PUT", url, headers, json_data=payload, client=client)

        except httpx.HTTPStatusError as e:
            return create_error_response(f"Failed to add test cases to test run: {str(e)}", e.response.json() if e.response else None)
        except Exception as e:
            return create_error_response(f"An unexpected error occurred: {str(e)}")


# Missing helper functions
async def _find_item_by_name(
    client: httpx.AsyncClient,
    base_url: str,
    project_id: Union[int, str],
    headers: Dict[str, str],
    data_type: str,
    item_name: str
) -> Dict[str, Any]:
    """Find an item by name in the given data type."""
    url = f"{base_url}/{project_id}/{data_type}"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    
    # Handle both direct list and nested object responses
    items_list = None
    if isinstance(data, list):
        items_list = data
    elif isinstance(data, dict) and data_type in data:
        items_list = data[data_type]
    else:
        raise ValueError(f"Unexpected response structure for {data_type}")
    
    if items_list:
        target = item_name.strip().lower()
        # For issue_types, use 'label' field instead of 'name' field
        field_name = "label" if data_type == "issue_types" else "name"
        
        for item in items_list:
            field_value = str(item.get(field_name, "")).strip().lower()
            if field_value == target:
                return item
        available_names = [str(item.get(field_name, "")) for item in items_list if item.get(field_name)]
        raise ValueError(f"{data_type.title().replace('_', ' ')} '{item_name}' not found. Available {data_type}: {', '.join(available_names)}")
    
    raise ValueError(f"No {data_type} found in response")


async def _generic_lookup_by_name(
    project_identifier: Optional[Union[int, str]],
    item_name: str,
    data_type: str,
    name_param: str
) -> Any:
    """Generic lookup function for finding items by name."""
    if not item_name:
        return create_error_response(f"{name_param} is required")
    
    try:
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
    except ValueError as e:
        return create_error_response(str(e))

    async with httpx.AsyncClient() as client:
        try:
            item = await _find_item_by_name(client, base_url, project_id, headers, data_type, item_name)
            
            return {
                data_type.rstrip('s'): item,  # Remove 's' from plural for response key
                "message": f"Found {data_type.rstrip('s')} '{item_name}' with ID {item.get('id')}"
            }
            
        except ValueError as e:
            return create_error_response(str(e))
        except Exception as e:
            return create_error_response(f"An unexpected error occurred: {str(e)}")


def _clear_custom_fields_cache() -> Dict[str, Any]:
    """Clear the custom fields cache."""
    global _custom_fields_cache
    _custom_fields_cache.clear()
    return {"message": "Custom fields cache cleared successfully"}


def _clear_lookup_cache() -> Dict[str, Any]:
    """Clear the lookup cache."""
    global _lookup_cache
    _lookup_cache.clear()
    return {"message": "Lookup cache cleared successfully"}


def _clear_resolution_cache() -> Dict[str, Any]:
    """Clear the resolution cache."""
    global _resolution_cache
    _resolution_cache.clear()
    return {"message": "Resolution cache cleared successfully"}


async def _resolve_name_to_id_generic(
    name: str,
    project_id: Union[int, str],
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str],
    data_type: str
) -> int:
    """Generic function to resolve names to IDs."""
    item = await _find_item_by_name(client, base_url, project_id, headers, data_type, name)
    return item["id"]


async def _resolve_user_name_to_id(
    user_identifier: str,
    project_id: Union[int, str],
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str]
) -> int:
    """Resolve user name or email to user ID."""
    # First try to find by exact name match
    try:
        url = f"{base_url}/{project_id}/users"
        params = {"q": user_identifier}
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        users_data = response.json()
        
        # Handle nested response structure {"users": [...], "meta": {...}}
        users_list = None
        if isinstance(users_data, list):
            users_list = users_data  # Direct array (backward compatibility)
        elif isinstance(users_data, dict) and "users" in users_data:
            users_list = users_data["users"]  # Nested structure
        else:
            raise ValueError(f"Unexpected response structure for users API")
        
        if users_list:
            # Look for exact name match first
            for user in users_list:
                if user.get("name", "").lower() == user_identifier.lower():
                    return user["id"]
                if user.get("email", "").lower() == user_identifier.lower():
                    return user["id"]
            
            # If no exact match, return the first result
            return users_list[0]["id"]
        
        raise ValueError(f"User '{user_identifier}' not found")
    except Exception as e:
        raise ValueError(f"Failed to resolve user '{user_identifier}': {str(e)}")


async def _resolve_issue_key_to_id(
    issue_key: str,
    project_id: Union[int, str],
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str]
) -> int:
    """Resolve issue key (e.g., 'FS-123456') to issue ID.
    
    Args:
        issue_key: Issue key to resolve (e.g., 'FS-123456')
        project_id: Project ID
        client: HTTP client instance
        base_url: Base API URL
        headers: Request headers
        
    Returns:
        Issue ID as integer
    """
    try:
        # If it's already a numeric ID, return as integer
        if isinstance(issue_key, int) or issue_key.isdigit():
            return int(issue_key)
        
        # Try to get the issue by key
        url = f"{base_url}/{project_id}/issues/{issue_key}"
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        
        issue_data = response.json()
        
        # Handle both direct issue response and nested issue response
        if isinstance(issue_data, dict):
            if "issue" in issue_data:
                issue = issue_data["issue"]
            else:
                issue = issue_data
            
            issue_id = issue.get("id")
            if issue_id:
                return int(issue_id)
        
        raise ValueError(f"Could not find issue ID for key: {issue_key}")
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ValueError(f"Issue not found: {issue_key}")
        raise ValueError(f"Failed to resolve issue key {issue_key}: HTTP {e.response.status_code}")
    except Exception as e:
        raise ValueError(f"Failed to resolve issue key {issue_key}: {str(e)}")


async def _resolve_subproject_name_to_id(
    sub_project_name: str,
    project_id: Union[int, str]
) -> int:
    """Resolve sub-project name to ID using the utility function.
    
    This function integrates the new get_subproject_id_by_name utility
    with the existing field resolution system for task filtering.
    
    Note: The project_id parameter is kept for compatibility with the field resolver
    system, but the utility function uses the environment variable.
    
    Args:
        sub_project_name: Name of the sub-project to resolve
        project_id: Project ID or key (unused - kept for compatibility)
        
    Returns:
        Sub-project ID as integer
        
    Raises:
        ValueError: If sub-project name cannot be resolved with helpful error message
    """
    # Use the utility function for consistent sub-project resolution
    result = await get_subproject_id_by_name(sub_project_name)
    
    if "error" in result:
        # If there's an error, raise an exception with helpful info
        available = ", ".join(result.get("available_sub_projects", []))
        error_msg = result["error"]
        if available:
            error_msg += f". Available sub-projects: {available}"
        raise ValueError(error_msg)
    
    return result["sub_project_id"]


async def _resolve_query_fields(
    query_pairs: List[tuple],
    project_id: Union[int, str],
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str],
    custom_fields: List[Dict[str, Any]],
    field_label_to_name_map: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Resolve query field labels to names, then names and values to their proper IDs.
    
    Handles:
    - Field label to name mapping (e.g., "Status" -> "status_id", "Issue Type" -> "issue_type")
    - Standard fields (owner_id, status_id, issue_type_id, sprint_id, release_id, sub_project_id)
    - Custom fields (with cf_ prefix)
    - Name-to-ID resolution for all supported field types
    """
    resolved_query = {}
    
    # Convert field labels to field names if mapping is provided
    mapped_query_pairs = []
    if field_label_to_name_map:
        for field_name, value in query_pairs:
            # Check if field_name is actually a label that needs mapping
            field_name_lower = field_name.lower()
            if field_name_lower in field_label_to_name_map:
                # Map label to actual field name
                actual_field_name = field_label_to_name_map[field_name_lower]
                mapped_query_pairs.append((actual_field_name, value))
                logging.info(f"Mapped field label '{field_name}' to field name '{actual_field_name}'")
            else:
                # Use field name as-is (might already be a field name)
                mapped_query_pairs.append((field_name, value))
    else:
        # No mapping provided, use query pairs as-is
        mapped_query_pairs = query_pairs
    
    # Field resolution mapping
    field_resolvers = {
        "owner_id": lambda value: _resolve_user_name_to_id(value, project_id, client, base_url, headers),
        "status_id": lambda value: _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "statuses"),
        "issue_type_id": lambda value: _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "issue_types"),
        "sprint_id": lambda value: _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "sprints"),
        "release_id": lambda value: _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "releases"),
        "sub_project_id": lambda value: _resolve_subproject_name_to_id(value, project_id),
        "parent_id": lambda value: _resolve_issue_key_to_id(value, project_id, client, base_url, headers),
        "epic_id": lambda value: _resolve_issue_key_to_id(value, project_id, client, base_url, headers),
    }
    
    for field_name, value in mapped_query_pairs:
        try:
            # Handle custom fields
            if field_name.startswith("cf_") or is_custom_field(field_name, custom_fields):
                # Ensure custom field has cf_ prefix
                if not field_name.startswith("cf_"):
                    field_name = f"cf_{field_name}"
                
                # For custom fields, try to resolve value to ID if it's a string
                if isinstance(value, str):
                    try:
                        resolved_value = await _resolve_custom_field_value_optimized(
                            field_name, value, project_id, client, base_url, headers
                        )
                        resolved_query[field_name] = resolved_value
                    except Exception:
                        # If custom field resolution fails, use original value
                        resolved_query[field_name] = value
                else:
                    resolved_query[field_name] = value
            
            # Handle standard fields with name-to-ID resolution
            elif field_name in field_resolvers and isinstance(value, str):
                try:
                    resolved_value = await field_resolvers[field_name](value)
                    resolved_query[field_name] = resolved_value
                except Exception:
                    # If resolution fails, use original value
                    resolved_query[field_name] = value
            
            # Handle other fields (pass through as-is)
            else:
                resolved_query[field_name] = value
                
        except Exception as e:
            # If any error occurs, use original value
            resolved_query[field_name] = value
    
    return resolved_query


async def _resolve_custom_field_value_optimized(
    field_name: str,
    value: str,
    project_id: Union[int, str],
    client: httpx.AsyncClient,
    base_url: str,
    headers: Dict[str, str]
) -> str:
    """Resolve custom field values to IDs."""
    # This is a placeholder implementation
    return value

@mcp.tool()
async def get_subproject_id_by_name(
    sub_project_name: str,
    project_identifier: Optional[Union[int, str]] = None
) -> Dict[str, Any]:
    """Utility function to get sub-project ID and info by name.
    
    This utility function can be used by other MCP tools that need to resolve
    sub-project names to IDs. It provides consistent error handling and caching.
    
    Usage Example in other functions:
        subproject_result = await get_subproject_id_by_name("Frontend Development")
        if "error" in subproject_result:
            return subproject_result
        sub_project_id = subproject_result["sub_project_id"]
        sub_project_info = subproject_result["sub_project_info"]
    
    Args:
        sub_project_name: Name of the sub-project to find (required)
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        
    Returns:
        Dictionary with sub_project_id, sub_project_info, or error
        Format: {"sub_project_id": int, "sub_project_info": dict} or {"error": str, "available_sub_projects": list}
    """
    try:
        project_id = get_project_identifier(project_identifier)
        
        if not sub_project_name:
            return {"error": "sub_project_name is required"}
        
        headers = {
            "Authorization": f"Token {FRESHRELEASE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        client = get_http_client()
        
        # Get all sub-projects to find the ID by name
        # Handle both project keys (like "FS", "PROJ") and project IDs (like 123)
        sub_projects_url = f"https://{FRESHRELEASE_DOMAIN}/{project_id}/sub_projects"
        
        logging.info(f"Fetching sub-projects from: {sub_projects_url}")
        sub_projects_response = await client.get(sub_projects_url, headers=headers)
        
        if sub_projects_response.status_code != 200:
            logging.error(f"Failed to fetch sub-projects: {sub_projects_response.status_code}")
            return {
                "error": f"Failed to fetch sub-projects: {sub_projects_response.status_code}",
                "details": sub_projects_response.text
            }
        
        sub_projects_data = sub_projects_response.json()
        
        # Handle the standard sub-projects API response structure
        if isinstance(sub_projects_data, dict) and "sub_projects" in sub_projects_data:
            sub_projects = sub_projects_data["sub_projects"]
        else:
            logging.error(f"Unexpected sub-projects API response structure: {sub_projects_data}")
            return {
                "error": f"Unexpected response structure for sub_projects API",
                "response_keys": list(sub_projects_data.keys()) if isinstance(sub_projects_data, dict) else None,
                "response_type": str(type(sub_projects_data))
            }
        
        # Validate we have a list of sub-projects
        if not isinstance(sub_projects, list):
            return {
                "error": f"Expected sub_projects to be a list, got {type(sub_projects)}",
                "sub_projects_value": sub_projects
            }
        
        # Find sub-project by name (case-insensitive)
        for sub_project in sub_projects:
            if sub_project.get("name", "").lower() == sub_project_name.lower():
                return {
                    "sub_project_id": sub_project.get("id"),
                    "sub_project_info": sub_project
                }
        
        # Sub-project not found
        available_names = [sp.get("name", "") for sp in sub_projects]
        return {
            "error": f"Sub-project '{sub_project_name}' not found",
            "available_sub_projects": available_names
        }
        
    except Exception as e:
        logging.error(f"Error getting sub-project ID by name: {str(e)}")
        return {"error": f"Failed to get sub-project ID: {str(e)}"}


@mcp.tool()
@performance_monitor("fr_get_current_subproject_sprint")
async def fr_get_current_subproject_sprint(
    sub_project_name: str
) -> Dict[str, Any]:
    """Get the current active sprint for a sub-project by name.
    
    This function first resolves the sub-project name to ID, then fetches
    the active sprints for that sub-project and returns the current one.
    
    Args:
        sub_project_name: Name of the sub-project to get current sprint for (required)
        
    Returns:
        Current active sprint data or error response
        
    Examples:
        # Get current sprint for a sub-project (uses FRESHRELEASE_PROJECT_KEY)
        fr_get_current_subproject_sprint(sub_project_name="Frontend Development")
        
        # Get current sprint for Backend API sub-project
        fr_get_current_subproject_sprint(sub_project_name="Backend API")
    """
    try:
        # Step 1: Get sub-project ID by name using utility function
        subproject_result = await get_subproject_id_by_name(sub_project_name)
        
        if "error" in subproject_result:
            return subproject_result
        
        sub_project_id = subproject_result["sub_project_id"]
        sub_project_info = subproject_result["sub_project_info"]
        
        # Get project identifier (avoid redundant call since utility function already calls this)
        project_id = get_project_identifier()
        
        headers = {
            "Authorization": f"Token {FRESHRELEASE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        client = get_http_client()
        
        # Step 2: Get active sprints for the sub-project
        # Handle both project keys (like "FS", "PROJ") and project IDs (like 123)
        # The sprints API can accept both project keys and IDs
        sprints_url = f"https://{FRESHRELEASE_DOMAIN}/{project_id}/sprints"
        sprints_params = {
            "primary_workspace_id": sub_project_id,
            "query_hash[0][condition]": "state",
            "query_hash[0][operator]": "is_in", 
            "query_hash[0][value]": "2"  # 2 = active state
        }
        
        logging.info(f"Fetching active sprints from: {sprints_url}")
        logging.info(f"Sprint params: {sprints_params}")
        
        sprints_response = await client.get(sprints_url, headers=headers, params=sprints_params)
        
        if sprints_response.status_code != 200:
            logging.error(f"Failed to fetch sprints: {sprints_response.status_code}")
            return {
                "error": f"Failed to fetch sprints: {sprints_response.status_code}",
                "details": sprints_response.text
            }
        
        sprints_data = sprints_response.json()
        sprints = sprints_data.get("sprints", [])
        
        if not sprints:
            return {
                "message": f"No active sprints found for sub-project '{sub_project_name}'",
                "sub_project": sub_project_info,
                "active_sprints": []
            }
        
        # Return the first active sprint (current sprint)
        current_sprint = sprints[0]
        
        return {
            "current_sprint": current_sprint,
            "sub_project": sub_project_info,
            "total_active_sprints": len(sprints),
            "all_active_sprints": sprints
        }
        
    except Exception as e:
        logging.error(f"Error getting current sub-project sprint: {str(e)}")
        return {"error": f"Failed to get current sub-project sprint: {str(e)}"}


def main():
    logging.info("Starting Freshrelease MCP server")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
