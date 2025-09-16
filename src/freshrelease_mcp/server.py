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
    "title", "description", "status_id", "priority_id", "owner_id", 
    "issue_type_id", "project_id", "story_points", "sprint_id", 
    "start_date", "due_by", "release_id", "tags", "document_ids", 
    "parent_id", "epic_id", "sub_project_id", "effort_value", "duration_value"
}

# Cache for custom fields to avoid repeated API calls
_custom_fields_cache: Dict[str, List[Dict[str, Any]]] = {}

# Cache for lookup data (sprints, releases, tags, subprojects)
_lookup_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

# Cache for resolved IDs to avoid repeated API calls
_resolution_cache: Dict[str, Dict[str, Any]] = {}


def get_standard_fields() -> frozenset:
    """Get the set of standard Freshrelease fields that are not custom fields."""
    return frozenset(_STANDARD_FIELDS)


async def get_project_custom_fields(client: httpx.AsyncClient, base_url: str, project_id: Union[int, str], headers: Dict[str, str]) -> List[Dict[str, Any]]:
    """Fetch custom fields for a project from the form API with caching."""
    project_key = str(project_id)
    
    # Return cached result if available
    if project_key in _custom_fields_cache:
        return _custom_fields_cache[project_key]
    
    url = f"{base_url}/{project_id}/issues/form"
    
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        custom_fields = data.get("custom_fields", [])
        
        # Cache the result
        _custom_fields_cache[project_key] = custom_fields
        return custom_fields
    except Exception:
        # If custom fields API fails, cache empty list and return it
        _custom_fields_cache[project_key] = []
        return []


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

# Status categories from Freshrelease repository
class STATUS_CATEGORIES(str, Enum):
    todo = 1
    in_progress = 2
    done = 3

class STATUS_CATEGORY_NAMES(str, Enum):
    YET_TO_START = "Yet To Start"
    WORK_IN_PROGRESS = "Work In Progress"
    COMPLETED = "Completed"

class TASK_STATUS(str, Enum):
    """Machine-friendly task status values supported by the API."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

@mcp.tool()
@performance_monitor("fr_create_project")
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
        if "error" in env_data:
            return env_data
        
        base_url = env_data["base_url"]
        headers = env_data["headers"]

        url = f"{base_url}/projects"
        payload: Dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description

        return await make_api_request("POST", url, headers, json_data=payload)

    except Exception as e:
        return create_error_response(f"Failed to create project: {str(e)}")


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
        if "error" in env_data:
            return env_data
        
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        url = f"{base_url}/projects/{project_id}"
        return await make_api_request("GET", url, headers)

    except Exception as e:
        return create_error_response(f"Failed to get project: {str(e)}")


@mcp.tool()
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
@performance_monitor("fr_get_issue_type_by_name")
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
        
        # Expecting a list of objects with a 'name' property
        if isinstance(data, list):
            target = issue_type_name.strip().lower()
            for item in data:
                name = str(item.get("name", "")).strip().lower()
                if name == target:
                    return item
            return create_error_response(f"Issue type '{issue_type_name}' not found")
        return create_error_response("Unexpected response structure for issue types", data)

    except Exception as e:
        return create_error_response(f"Failed to get issue type: {str(e)}")

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

    async with httpx.AsyncClient() as client:
        try:
            return await make_api_request(client, "GET", url, headers, params=params)
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
    
    if not isinstance(users_data, list) or not users_data:
        raise ValueError(f"No users found matching '{user}'")
    
    lowered = user.strip().lower()
    
    # Prefer exact email match
    for item in users_data:
        email = str(item.get("email", "")).strip().lower()
        if email and email == lowered:
            return item.get("id")
    
    # Then exact name match
    for item in users_data:
        name_val = str(item.get("name", "")).strip().lower()
        if name_val and name_val == lowered:
            return item.get("id")
    
    # Fallback to first result
    return users_data[0].get("id")


async def resolve_issue_type_name_to_id(
    client: httpx.AsyncClient,
    base_url: str,
    project_identifier: Union[int, str],
    headers: Dict[str, str],
    issue_type_name: str
) -> int:
    """Resolve issue type name to ID.
    
    Args:
        client: HTTP client instance
        base_url: API base URL
        project_identifier: Project identifier
        headers: Request headers
        issue_type_name: Issue type name to resolve
        
    Returns:
        Resolved issue type ID
        
    Raises:
        ValueError: If issue type not found
        httpx.HTTPStatusError: For API errors
    """
    issue_types_url = f"{base_url}/{project_identifier}/project_issue_types"
    response = await client.get(issue_types_url, headers=headers)
    response.raise_for_status()
    it_data = response.json()
    
    types_list = it_data.get("issue_types", []) if isinstance(it_data, dict) else []
    target = issue_type_name.strip().lower()
    
    for t in types_list:
        name = str(t.get("name", "")).strip().lower()
        if name == target:
            return t.get("id")
    
    raise ValueError(f"Issue type '{issue_type_name}' not found")


async def resolve_section_hierarchy_to_ids(client: httpx.AsyncClient, base_url: str, project_identifier: Union[int, str], headers: Dict[str, str], section_path: str) -> List[int]:
    """Resolve a section hierarchy path like 'section > sub-section > sub-sub-section' to section IDs.
    
    Returns list of IDs for all matching sections in the hierarchy.
    """
    # Split by '>' and strip whitespace
    path_parts = [part.strip() for part in section_path.split('>')]
    if not path_parts or not path_parts[0]:
        return []
    
    # Fetch all sections
    sections_url = f"{base_url}/{project_identifier}/sections"
    resp = await client.get(sections_url, headers=headers)
    resp.raise_for_status()
    sections = resp.json()
    
    if not isinstance(sections, list):
        raise httpx.HTTPStatusError("Unexpected sections response structure", request=resp.request, response=resp)
    
    # Build a hierarchy map: parent_id -> children
    hierarchy: Dict[int, List[Dict[str, Any]]] = {}
    root_sections: List[Dict[str, Any]] = []
    
    for section in sections:
        parent_id = section.get("parent_id")
        if parent_id is None:
            root_sections.append(section)
        else:
            if parent_id not in hierarchy:
                hierarchy[parent_id] = []
            hierarchy[parent_id].append(section)
    
    # Recursive function to find sections by path
    def find_sections_by_path(sections_list: List[Dict[str, Any]], remaining_path: List[str]) -> List[int]:
        if not remaining_path:
            return [s.get("id") for s in sections_list if isinstance(s.get("id"), int)]
        
        current_name = remaining_path[0].lower()
        matching_sections = []
        
        for section in sections_list:
            section_name = str(section.get("name", "")).strip().lower()
            if section_name == current_name:
                section_id = section.get("id")
                if isinstance(section_id, int):
                    if len(remaining_path) == 1:
                        # This is the final level, return this section
                        matching_sections.append(section_id)
                    else:
                        # Look in children for the next level
                        children = hierarchy.get(section_id, [])
                        child_matches = find_sections_by_path(children, remaining_path[1:])
                        matching_sections.extend(child_matches)
        
        return matching_sections
    
    # Start from root sections
    return find_sections_by_path(root_sections, path_parts)

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

    async with httpx.AsyncClient() as client:
        try:
            return await make_api_request(client, "GET", url, headers)
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

    async with httpx.AsyncClient() as client:
        try:
            return await make_api_request(client, "GET", url, headers)
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
            
            return await make_api_request(client, "PUT", url, headers, json_data=payload)
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
            sections = await make_api_request(client, "GET", sections_url, headers)

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
                data = await make_api_request(client, "GET", testcases_url, headers, params=params)
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

@mcp.tool()
@performance_monitor("fr_filter_tasks")
async def fr_filter_tasks(
    project_identifier: Optional[Union[int, str]] = None,
    query: Optional[Union[str, Dict[str, Any]]] = None,
    query_format: str = "comma_separated",
    # Standard fields
    title: Optional[str] = None,
    description: Optional[str] = None,
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
    document_ids: Optional[Union[str, List[Union[int, str]]]] = None,
    parent_id: Optional[Union[int, str]] = None,
    epic_id: Optional[Union[int, str]] = None,
    sub_project_id: Optional[Union[int, str]] = None,
    effort_value: Optional[Union[int, str]] = None,
    duration_value: Optional[Union[int, str]] = None
) -> Any:
    """Filter tasks/issues using various criteria with automatic name-to-ID resolution and custom field detection.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        query: Filter query in JSON string or comma-separated format (optional)
        query_format: Format of the query - "comma_separated" or "json" (default: "comma_separated")
        
        # Standard fields (optional) - supports both IDs and names
        title: Filter by title
        description: Filter by description
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
        document_ids: Filter by document IDs (string or array)
        parent_id: Filter by parent issue ID or key (e.g., "PROJ-123")
        epic_id: Filter by epic issue ID or key (e.g., "PROJ-456")
        sub_project_id: Filter by sub project ID or name (e.g., "Frontend")
        effort_value: Filter by effort value
        duration_value: Filter by duration value
        
    Returns:
        Filtered list of tasks or error response
        
    Examples:
        # Using individual field parameters with names (automatically resolved to IDs)
        fr_filter_tasks(owner_id="John Doe", status_id="In Progress", issue_type_id="Bug")
        
        # Using project key instead of ID
        fr_filter_tasks(project_id="PROJ123", sprint_id="Sprint 1")
        
        # Using issue keys for parent/epic
        fr_filter_tasks(parent_id="PROJ-123", epic_id="PROJ-456")
        
        # Using query format with names
        fr_filter_tasks(query="owner_id:John Doe,status_id:In Progress,cf_custom_field:value")
        
        # JSON format
        fr_filter_tasks(query='{"owner_id":"John Doe","status_id":"In Progress"}', query_format="json")
        
        # Get all tasks (no filter)
        fr_filter_tasks()
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)

        # Collect individual field parameters (excluding project_id to avoid duplication)
        field_params = {
            "title": title,
            "description": description,
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
            "document_ids": document_ids,
            "parent_id": parent_id,
            "epic_id": epic_id,
            "sub_project_id": sub_project_id,
            "effort_value": effort_value,
            "duration_value": duration_value
        }

        # Filter out None values
        field_params = {k: v for k, v in field_params.items() if v is not None}

        # Build the final query
        final_query = field_params
        
        # Make the API request
        url = f"{base_url}/{project_id}/issues/filter"
        params = {"query": ",".join([f"{k}:{v}" for k, v in final_query.items()])}
        
        result = await make_api_request("GET", url, headers, params=params)
        
        return result

    except Exception as e:
        return create_error_response(f"Failed to filter tasks: {str(e)}")
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
async def fr_get_subproject_by_name(
    project_identifier: Optional[Union[int, str]] = None,
    subproject_name: str = None
) -> Any:
    """Get subproject ID by name by fetching all subprojects and filtering by name.

    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        subproject_name: Name of the subproject to find (required)
        
    Returns:
        Subproject object with ID and details or error response
        
    Examples:
        # Get subproject by name
        fr_get_subproject_by_name(subproject_name="Frontend")
        
        # Get subproject by name for specific project
        fr_get_subproject_by_name(project_identifier="PROJ123", subproject_name="Frontend")
    """
    return await _generic_lookup_by_name(project_identifier, subproject_name, "sub_projects", "subproject_name")


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


@mcp.tool()
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
        title: Filter by title (optional)
        description: Filter by description (optional)
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


@mcp.tool()
@performance_monitor("fr_filter_testcases")
async def fr_filter_testcases(
    project_identifier: Optional[Union[int, str]] = None,
    filter_rules: Optional[List[Dict[str, Any]]] = None
) -> Any:
    """Filter test cases using filter rules with automatic name-to-ID resolution.
    
    This tool allows you to filter test cases by various criteria like section, severity, type, and linked issues.
    It automatically resolves names to IDs for:
    - section_id: Resolves section names to IDs
    - type_id: Resolves test case type names to IDs
    - issue_ids: Resolves issue keys to IDs
    - tags: Resolves tag names to IDs
    - Custom fields: Resolves custom field values to IDs
    
    Use fr_get_testcase_form_fields to get available fields and their possible values for filtering.
    
    Args:
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        filter_rules: List of filter rule objects with condition, operator, and value
                     Example: [{"condition": "section_id", "operator": "is", "value": "My Section"}]
    
    Returns:
        Filtered list of test cases or error response
        
    Example:
        # Filter by section name (automatically resolved to ID)
        test_cases = fr_filter_testcases(
            filter_rules=[{"condition": "section_id", "operator": "is", "value": "Authentication"}]
        )
        
        # Filter by test case type name and severity
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
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        project_id = get_project_identifier(project_identifier)
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        client = get_http_client()

        # Process and resolve filter rules with optimized batch resolution
        resolved_rules = []
        if filter_rules:
            # Group resolution tasks by type for batch processing
            resolution_tasks = {
                "section": [],
                "type": [],
                "issue": [],
                "tag": [],
                "custom": []
            }
            
            # Collect all resolution tasks
            for i, rule in enumerate(filter_rules):
                if isinstance(rule, dict) and all(key in rule for key in ["condition", "operator", "value"]):
                    condition = rule["condition"]
                    value = rule["value"]
                    
                    if condition == "section_id" and isinstance(value, str):
                        resolution_tasks["section"].append((i, value))
                    elif condition == "type_id" and isinstance(value, str):
                        resolution_tasks["type"].append((i, value))
                    elif condition == "issue_ids" and isinstance(value, (list, str)):
                        if isinstance(value, str):
                            value = [value]
                        for issue_key in value:
                            resolution_tasks["issue"].append((i, issue_key))
                    elif condition == "tags" and isinstance(value, (list, str)):
                        if isinstance(value, str):
                            value = [value]
                        for tag_name in value:
                            resolution_tasks["tag"].append((i, tag_name))
                    elif condition.startswith("cf_") and isinstance(value, (list, str)):
                        field_name = condition[3:]
                        if isinstance(value, str):
                            value = [value]
                        for field_value in value:
                            resolution_tasks["custom"].append((i, field_name, field_value))
            
            # Batch resolve all tasks
            resolution_results = {}
            
            # Resolve sections
            if resolution_tasks["section"]:
                section_resolutions = await asyncio.gather(*[
                    _resolve_name_to_id_generic(name, project_id, client, base_url, headers, "section")
                    for _, name in resolution_tasks["section"]
                ], return_exceptions=True)
                for (rule_idx, name), result in zip(resolution_tasks["section"], section_resolutions):
                    if rule_idx not in resolution_results:
                        resolution_results[rule_idx] = {}
                    resolution_results[rule_idx]["section_id"] = result if not isinstance(result, Exception) else None
            
            # Resolve types
            if resolution_tasks["type"]:
                type_resolutions = await asyncio.gather(*[
                    _resolve_name_to_id_generic(name, project_id, client, base_url, headers, "type")
                    for _, name in resolution_tasks["type"]
                ], return_exceptions=True)
                for (rule_idx, name), result in zip(resolution_tasks["type"], type_resolutions):
                    if rule_idx not in resolution_results:
                        resolution_results[rule_idx] = {}
                    resolution_results[rule_idx]["type_id"] = result if not isinstance(result, Exception) else None
            
            # Resolve issues
            if resolution_tasks["issue"]:
                issue_resolutions = await asyncio.gather(*[
                    _resolve_name_to_id_generic(issue_key, project_id, client, base_url, headers, "issue")
                    for _, issue_key in resolution_tasks["issue"]
                ], return_exceptions=True)
                for (rule_idx, issue_key), result in zip(resolution_tasks["issue"], issue_resolutions):
                    if rule_idx not in resolution_results:
                        resolution_results[rule_idx] = {}
                    if "issue_ids" not in resolution_results[rule_idx]:
                        resolution_results[rule_idx]["issue_ids"] = []
                    resolution_results[rule_idx]["issue_ids"].append(result if not isinstance(result, Exception) else issue_key)
            
            # Resolve tags
            if resolution_tasks["tag"]:
                tag_resolutions = await asyncio.gather(*[
                    _resolve_name_to_id_generic(tag_name, project_id, client, base_url, headers, "tag")
                    for _, tag_name in resolution_tasks["tag"]
                ], return_exceptions=True)
                for (rule_idx, tag_name), result in zip(resolution_tasks["tag"], tag_resolutions):
                    if rule_idx not in resolution_results:
                        resolution_results[rule_idx] = {}
                    if "tags" not in resolution_results[rule_idx]:
                        resolution_results[rule_idx]["tags"] = []
                    resolution_results[rule_idx]["tags"].append(result if not isinstance(result, Exception) else tag_name)
            
            # Resolve custom fields
            if resolution_tasks["custom"]:
                custom_resolutions = await asyncio.gather(*[
                    _resolve_custom_field_value_optimized(field_name, field_value, project_id, client, base_url, headers)
                    for _, field_name, field_value in resolution_tasks["custom"]
                ], return_exceptions=True)
                for (rule_idx, field_name, field_value), result in zip(resolution_tasks["custom"], custom_resolutions):
                    if rule_idx not in resolution_results:
                        resolution_results[rule_idx] = {}
                    if f"cf_{field_name}" not in resolution_results[rule_idx]:
                        resolution_results[rule_idx][f"cf_{field_name}"] = []
                    resolution_results[rule_idx][f"cf_{field_name}"].append(result if not isinstance(result, Exception) else field_value)
            
            # Build resolved rules
            for i, rule in enumerate(filter_rules):
                if isinstance(rule, dict) and all(key in rule for key in ["condition", "operator", "value"]):
                    condition = rule["condition"]
                    operator = rule["operator"]
                    value = rule["value"]
                    
                    # Apply resolved values
                    if condition == "section_id" and i in resolution_results and "section_id" in resolution_results[i]:
                        resolved_id = resolution_results[i]["section_id"]
                        if resolved_id:
                            value = resolved_id
                    elif condition == "type_id" and i in resolution_results and "type_id" in resolution_results[i]:
                        resolved_id = resolution_results[i]["type_id"]
                        if resolved_id:
                            value = resolved_id
                    elif condition == "issue_ids" and i in resolution_results and "issue_ids" in resolution_results[i]:
                        value = resolution_results[i]["issue_ids"]
                    elif condition == "tags" and i in resolution_results and "tags" in resolution_results[i]:
                        value = resolution_results[i]["tags"]
                    elif condition.startswith("cf_") and i in resolution_results and condition in resolution_results[i]:
                        value = resolution_results[i][condition]
                    
                    resolved_rules.append({
                        "condition": condition,
                        "operator": operator,
                        "value": value
                    })

        # Build filter_rule query parameters
        params = {}
        for i, rule in enumerate(resolved_rules):
            params[f"filter_rule[{i}][condition]"] = rule["condition"]
            params[f"filter_rule[{i}][operator]"] = rule["operator"]
            params[f"filter_rule[{i}][value]"] = rule["value"]

        # Get filtered test cases
        url = f"{base_url}/{project_id}/test_cases"
        return await make_api_request("GET", url, headers, params=params, client=client)

    except Exception as e:
        return create_error_response(f"Failed to filter test cases: {str(e)}")


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
        url = f"{base_url}/{project_id}/test_cases/form"
        return await make_api_request("GET", url, headers, client=client)

    except Exception as e:
        return create_error_response(f"Failed to get test case form fields: {str(e)}")


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
                    tc_data = await make_api_request(client, "GET", tc_url, headers)
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
            return await make_api_request(client, "PUT", url, headers, json_data=payload)

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
    
    if isinstance(data, list):
        target = item_name.strip().lower()
        for item in data:
            name = str(item.get("name", "")).strip().lower()
            if name == target:
                return item
        available_names = [str(item.get("name", "")) for item in data if item.get("name")]
        raise ValueError(f"{data_type.title().replace('_', ' ')} '{item_name}' not found. Available {data_type}: {', '.join(available_names)}")
    
    raise ValueError(f"Unexpected response structure for {data_type}")


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
    client: httpx.AsyncClient,
    base_url: str,
    project_id: Union[int, str],
    headers: Dict[str, str],
    name: str,
    data_type: str
) -> int:
    """Generic function to resolve names to IDs."""
    item = await _find_item_by_name(client, base_url, project_id, headers, data_type, name)
    return item["id"]


async def _resolve_custom_field_value_optimized(
    client: httpx.AsyncClient,
    base_url: str,
    project_id: Union[int, str],
    headers: Dict[str, str],
    field_name: str,
    value: str
) -> str:
    """Resolve custom field values to IDs."""
    # This is a placeholder implementation
    return value


def main():
    logging.info("Starting Freshdesk MCP server")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
