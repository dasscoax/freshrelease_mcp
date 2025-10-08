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
@performance_monitor("fr_get_epic_tasks")
async def fr_get_epic_tasks(
    epic_key: Union[int, str],
    project_identifier: Optional[Union[int, str]] = None,
    include_details: bool = True,
    include: Optional[str] = None,
    page: Optional[int] = 1,
    per_page: Optional[int] = 50
) -> Dict[str, Any]:
    """Get all tasks and their details that belong to a specific epic or parent task.
    
    This method fetches all child tasks/subtasks under a given epic or parent task,
    providing a complete overview of the epic's scope and progress.
    
    Args:
        epic_key: Epic/Parent task ID or key (e.g., "FS-12345", 123456)
        project_identifier: Project ID or key (optional, uses FRESHRELEASE_PROJECT_KEY if not provided)
        include_details: Whether to include detailed task information (default: True)
        include: Additional fields to include (e.g., "custom_field,owner,priority,status")
        page: Page number for pagination (default: 1)
        per_page: Number of items per page (default: 50)
        
    Returns:
        Dictionary containing epic details and list of child tasks or error response
        
    Examples:
        # Get all tasks under epic FS-12345
        fr_get_epic_tasks("FS-12345")
        
        # Get tasks with custom fields and specific pagination
        fr_get_epic_tasks("FS-12345", include="custom_field,owner,status", per_page=100)
    """
    try:
        # Validate environment variables
        env_data = validate_environment()
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        project_id = get_project_identifier(project_identifier)
        
        logging.info(f"Fetching tasks for epic/parent: {epic_key}")
        
        # First, get the epic/parent task details
        epic_details = None
        if include_details:
            try:
                epic_response = await fr_get_task(project_identifier, epic_key)
                if "error" not in epic_response:
                    epic_details = epic_response
                    logging.info(f"Retrieved epic details: {epic_details.get('issue', {}).get('title', 'N/A')}")
            except Exception as e:
                logging.warning(f"Could not fetch epic details: {str(e)}")
        
        # Build query to get all child tasks
        # Use both parent_id and epic_id to cover all possible relationships
        query_hash = [
            {"condition": "parent_id", "operator": "is", "value": epic_key}
        ]
        
        # Also check for epic_id if the epic_key is different from parent_id
        # Some systems use separate epic relationships
        try:
            # Try to add epic_id filter as well for comprehensive results
            query_hash.append({"condition": "epic_id", "operator": "is", "value": epic_key})
        except Exception:
            # If epic_id filter fails, continue with just parent_id
            pass
        
        # Set up parameters for child task filtering
        filter_params = {
            "query_hash": query_hash,
            "project_identifier": project_identifier,
            "page": page,
            "per_page": per_page
        }
        
        if include:
            filter_params["include"] = include
        
        # Get child tasks using the existing filter function
        child_tasks_response = await fr_filter_tasks(**filter_params)
        
        if "error" in child_tasks_response:
            return child_tasks_response
        
        # Extract the tasks list from the response
        if isinstance(child_tasks_response, dict) and "issues" in child_tasks_response:
            child_tasks = child_tasks_response["issues"]
            pagination_info = {
                "page": child_tasks_response.get("page", page),
                "per_page": child_tasks_response.get("per_page", per_page),
                "total": child_tasks_response.get("total", len(child_tasks))
            }
        elif isinstance(child_tasks_response, list):
            child_tasks = child_tasks_response
            pagination_info = {
                "page": page,
                "per_page": per_page,
                "total": len(child_tasks)
            }
        else:
            child_tasks = []
            pagination_info = {
                "page": page,
                "per_page": per_page,
                "total": 0
            }
        
        # Prepare the response
        result = {
            "epic_key": epic_key,
            "child_tasks": child_tasks,
            "child_tasks_count": len(child_tasks),
            "pagination": pagination_info
        }
        
        # Add epic details if requested and available
        if include_details and epic_details:
            result["epic_details"] = epic_details
        
        # Add summary statistics
        if child_tasks:
            # Count tasks by status
            status_counts = {}
            priority_counts = {}
            assignee_counts = {}
            
            for task in child_tasks:
                task_data = task if isinstance(task, dict) else task.get("issue", {})
                
                # Status counts
                status = task_data.get("status", {})
                status_name = status.get("name", "Unknown") if isinstance(status, dict) else str(status)
                status_counts[status_name] = status_counts.get(status_name, 0) + 1
                
                # Priority counts  
                priority = task_data.get("priority", {})
                priority_name = priority.get("name", "Unknown") if isinstance(priority, dict) else str(priority)
                priority_counts[priority_name] = priority_counts.get(priority_name, 0) + 1
                
                # Assignee counts
                owner = task_data.get("owner", {})
                owner_name = owner.get("name", "Unassigned") if isinstance(owner, dict) else "Unassigned"
                assignee_counts[owner_name] = assignee_counts.get(owner_name, 0) + 1
            
            result["summary"] = {
                "status_breakdown": status_counts,
                "priority_breakdown": priority_counts,
                "assignee_breakdown": assignee_counts
            }
        
        logging.info(f"Retrieved {len(child_tasks)} child tasks for epic {epic_key}")
        return result

    except Exception as e:
        error_msg = f"Failed to get epic tasks: {str(e)}"
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
    headers: Dict[str, str]
) -> Any:
    """Resolve testcase field values to IDs if needed.
    
    Args:
        condition: The field condition (e.g., "creator_id", "section_id")
        value: The value to resolve
        project_id: Resolved project ID
        client: HTTP client instance
        base_url: API base URL
        headers: Request headers
        
    Returns:
        Resolved value or original value if no resolution needed
    """
    try:
        # Fields that need resolution
        if condition == "creator_id" and isinstance(value, str) and not value.isdigit():
            # Resolve user name/email to ID
            user_result = await _resolve_user_name_to_id(value, project_id, client, base_url, headers)
            if user_result and isinstance(user_result, int):
                return user_result
        elif condition == "section_id" and isinstance(value, str) and not value.isdigit():
            # Resolve section name to ID
            section_result = await _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "sections")
            if section_result and isinstance(section_result, (int, dict)):
                return section_result.get("id", section_result) if isinstance(section_result, dict) else section_result
        elif condition == "test_case_type_id" and isinstance(value, str) and not value.isdigit():
            # Resolve test case type name to ID
            type_result = await _resolve_name_to_id_generic(value, project_id, client, base_url, headers, "test_case_types")
            if type_result and isinstance(type_result, (int, dict)):
                return type_result.get("id", type_result) if isinstance(type_result, dict) else type_result
        
        # Return original value if no resolution needed
        return value
        
    except Exception:
        # Return original value if resolution fails
        return value


@mcp.tool()
@performance_monitor("fr_filter_testcases")
async def fr_filter_testcases(
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
    """Filter test cases using filter rules with automatic label-to-condition and name-to-ID resolution.
    
    This tool allows you to filter test cases by various criteria using either user-friendly field labels 
    or internal condition names. Supports native query_hash format for optimal performance.
    
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
        Filtered list of test cases or error response
        
    Examples:
        # Using comma-separated query format (simple and intuitive)
        fr_filter_testcases(query="Section:Authentication,Type:Functional Test,Creator:John Doe")
        
        # Multiple field filtering with comma-separated format
        fr_filter_testcases(query="Severity:High,Status:Active,Creator:jane@company.com")
        
        # Using native query_hash format (preferred for complex queries)
        fr_filter_testcases(query_hash=[
            {"condition": "status", "operator": "is", "value": 1},
            {"condition": "creator_id", "operator": "is_in", "value": [50624]}
        ])
        
        # Using filter_rules (legacy, auto-converted to query_hash)
        fr_filter_testcases(filter_rules=[
            {"condition": "Section", "operator": "is", "value": "Authentication"},
            {"condition": "Type", "operator": "is", "value": "Functional Test"},
            {"condition": "Creator", "operator": "is", "value": "John Doe"}
        ])
        
        # With pagination, sorting, and test run filtering
        fr_filter_testcases(
            query_hash=[{"condition": "creator_id", "operator": "is", "value": 50624}],
            include="custom_field",
            page=1,
            per_page=15,
            sort="id",
            sort_type="asc",
            test_run_id=154125
        )
        
        # Complex filtering with duplicates, arrays, and test run
        fr_filter_testcases(
            query_hash=[
                {"condition": "severity_id", "operator": "is_in", "value": [17, 16, 15]},
                {"condition": "creator_id", "operator": "is_in", "value": [50624]},
                {"condition": "source_of_creation", "operator": "is_in", "value": [0]},
                {"condition": "section_id", "operator": "is", "value": 59866}
            ],
            page=1,
            per_page=15,
            sort="id",
            sort_type="asc",
            test_run_id=154125
        )
        # Results in: query_hash[0] through query_hash[3] with proper array formatting
    """
    try:
        # Validate environment variables and initialize API objects once
        env_data = validate_environment()
        project_id = get_project_identifier(project_identifier)
        base_url = env_data["base_url"]
        headers = env_data["headers"]
        client = get_http_client()

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
            # Get testcase field mappings for label-to-condition translation
            field_mapping_result = await _get_testcase_fields_mapping(project_identifier)
            if "error" in field_mapping_result:
                return field_mapping_result
                
            field_label_to_condition_map = field_mapping_result.get("field_label_to_condition_map", {})
            custom_fields = field_mapping_result.get("custom_fields", [])
            
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
                        
                        # Resolve values to IDs if needed
                        final_value = await _resolve_testcase_field_value(condition, value, project_id, client, base_url, headers)
                        
                        # Handle array values using helper function
                        _add_query_hash_value(params, i, final_value)
                
                # Make API request with converted query
                url = f"{base_url}/{project_id}/test_cases"
                result = await make_api_request("GET", url, headers, params=params, client=client)
                return result

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
                    
                    # Resolve values to IDs if needed
                    final_value = await _resolve_testcase_field_value(condition, value, project_id, client, base_url, headers)
                    
                    # Handle array values using helper function
                    _add_query_hash_value(params, i, final_value)
            
            # Make API request with query_hash
            url = f"{base_url}/{project_id}/test_cases"
            result = await make_api_request("GET", url, headers, params=params, client=client)
            return result

        # Handle legacy filter_rules format (convert to query_hash)
        if not filter_rules:
            # No filtering criteria provided, return all test cases with pagination/sorting
            url = f"{base_url}/{project_id}/test_cases"
            return await make_api_request("GET", url, headers, params=params, client=client)

        # Get testcase field mappings for label-to-condition translation
        field_mapping_result = await _get_testcase_fields_mapping(project_identifier)
        if "error" in field_mapping_result:
            return field_mapping_result
            
        field_label_to_condition_map = field_mapping_result.get("field_label_to_condition_map", {})

        # Convert filter_rules to query_hash format
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
                
                # Resolve values to IDs if needed
                final_value = await _resolve_testcase_field_value(condition, value, project_id, client, base_url, headers)
                
                # Handle array values using helper function
                _add_query_hash_value(params, i, final_value)

        # Make the API request
        url = f"{base_url}/{project_id}/test_cases"
        result = await make_api_request("GET", url, headers, params=params, client=client)
        return result

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
async def fr_get_testrun_details(
    test_run_id: Union[int, str],
    project_identifier: Optional[Union[int, str]] = None
) -> Dict[str, Any]:
    """Get test run details with simple execution insights.
    
    Args:
        test_run_id: Test run ID (required)
        project_identifier: Project ID or key (optional)
        
    Returns:
        Test run details with execution summary
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
            
        progress = test_run.get("progress", {})
        creator = next((u.get("name", "Unknown") for u in response.get("users", []) if u.get("id") == test_run.get("creator_id")), "Unknown")
        
        # Simple metrics
        total = sum(progress.values())
        passed = progress.get("passed", 0)
        failed = progress.get("failed", 0)
        
        # Build simple response
        result = {
            "id": test_run.get("id"),
            "name": test_run.get("name"),
            "status": test_run.get("status"),
            "creator": creator,
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "progress": progress
        }
        
        # Simple insights
        if total == 0:
            result["insight"] = "No test cases in this run"
        elif failed > 0:
            result["insight"] = f"{failed} test cases failed out of {total}"
        elif passed == total:
            result["insight"] = f"All {total} test cases passed successfully"
        else:
            result["insight"] = f"{passed}/{total} test cases completed"
            
        return result
        
    except Exception as e:
        return create_error_response(f"Failed to get test run details: {str(e)}")


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
