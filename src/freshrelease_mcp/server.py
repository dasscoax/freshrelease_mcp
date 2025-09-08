import httpx
import asyncio
from mcp.server.fastmcp import FastMCP
import logging
import os
import base64
from typing import Optional, Dict, Union, Any, List
from enum import IntEnum, Enum
import re
from pydantic import BaseModel, Field

# Set up logging
logging.basicConfig(level=logging.INFO)

# Initialize FastMCP server
mcp = FastMCP("freshrelease-mcp")

FRESHRELEASE_API_KEY = os.getenv("FRESHRELEASE_API_KEY")
FRESHRELEASE_DOMAIN = os.getenv("FRESHRELEASE_DOMAIN")


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
async def fr_create_project(name: str, description: Optional[str] = None) -> Dict[str, Any]:
    """Create a project in Freshrelease."""
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/projects"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {"name": name}
    if description is not None:
        payload["description"] = description

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to create project: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


@mcp.tool()
async def fr_get_project(project_identifier: Union[int, str]) -> Dict[str, Any]:
    """Get a project from Freshrelease by ID or key.

    - project_identifier: numeric ID (e.g., 123) or key (e.g., "ENG")
    """
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/projects/{project_identifier}"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch project: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


@mcp.tool()
async def fr_create_task(
    project_identifier: Union[int, str],
    title: str,
    description: Optional[str] = None,
    assignee_id: Optional[int] = None,
    status: Optional[Union[str, TASK_STATUS]] = None,
    due_date: Optional[str] = None,
    issue_type_name: Optional[str] = None,
    user: Optional[str] = None,
    additional_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a task under a Freshrelease project.

    - due_date: ISO 8601 date string (e.g., 2025-12-31) if supported by your account
    - issue_type_name: case-insensitive issue type key (e.g., "epic", "task").
      Resolved to an `issue_type_id` via `/project_issue_types` and added to payload.
    - user: optional name or email. If provided and `assignee_id` is not,
      resolves to a user id via `/{project_identifier}/users?q=...` and sets `assignee_id`.
    - additional_fields: arbitrary key/value pairs to include in the request body
      (unknown keys will be passed through to the API). Core fields
      (title, description, assignee_id, status, due_date, issue_type_id) cannot be overridden.
    """
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/{project_identifier}/issues"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {"title": title}
    if description is not None:
        payload["description"] = description
    if assignee_id is not None:
        payload["assignee_id"] = assignee_id
    if status is not None:
        payload["status"] = status.value if isinstance(status, TASK_STATUS) else status
    if due_date is not None:
        payload["due_date"] = due_date

    # Merge any additional fields without allowing overrides of core fields
    if additional_fields:
        protected_keys = {"title", "description", "assignee_id", "status", "due_date", "issue_type_id"}
        for key, value in additional_fields.items():
            if key in protected_keys:
                continue
            payload[key] = value

    # Use a single client for optional resolutions and the final POST
    async with httpx.AsyncClient() as client:
        # Resolve issue_type_name -> issue_type_id via project_issue_types endpoint
        name_to_resolve = (issue_type_name or "task")
        if name_to_resolve:
            issue_types_url = f"{base_url}/{project_identifier}/project_issue_types"
            try:
                it_resp = await client.get(issue_types_url, headers=headers)
                it_resp.raise_for_status()
                it_data = it_resp.json()
                # Expecting structure with 'issue_types': [ { name, id, ... } ]
                types_list = it_data.get("issue_types", []) if isinstance(it_data, dict) else []
                target = name_to_resolve.strip().lower()
                matched_id: Optional[int] = None
                for t in types_list:
                    name = str(t.get("name", "")).strip().lower()
                    if name == target:
                        matched_id = t.get("id")
                        break
                if matched_id is None:
                    return {"error": f"Issue type '{name_to_resolve}' not found", "details": it_data}
                payload["issue_type_id"] = matched_id
            except httpx.HTTPStatusError as e:
                return {"error": f"Failed to resolve issue type: {str(e)}", "details": e.response.json() if e.response else None}
            except Exception as e:
                return {"error": f"An unexpected error occurred while resolving issue type: {str(e)}"}

        # Resolve user -> assignee_id if applicable
        if ("assignee_id" not in payload) and user:
            users_url = f"{base_url}/{project_identifier}/users"
            params = {"q": user}
            try:
                u_resp = await client.get(users_url, headers=headers, params=params)
                u_resp.raise_for_status()
                users_data = u_resp.json()
                chosen_id: Optional[int] = None
                if isinstance(users_data, list) and users_data:
                    lowered = user.strip().lower()
                    # Prefer exact email match
                    for item in users_data:
                        email = str(item.get("email", "")).strip().lower()
                        if email and email == lowered:
                            chosen_id = item.get("id")
                            break
                    # Then exact name match
                    if chosen_id is None:
                        for item in users_data:
                            name_val = str(item.get("name", "")).strip().lower()
                            if name_val and name_val == lowered:
                                chosen_id = item.get("id")
                                break
                    # Fallback to first result
                    if chosen_id is None:
                        chosen_id = users_data[0].get("id")
                if chosen_id is None:
                    return {"error": f"No users found matching '{user}'"}
                payload["assignee_id"] = chosen_id
            except httpx.HTTPStatusError as e:
                return {"error": f"Failed to resolve user: {str(e)}", "details": e.response.json() if e.response else None}
            except Exception as e:
                return {"error": f"An unexpected error occurred while resolving user: {str(e)}"}

        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to create task: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


@mcp.tool()
async def fr_get_task(project_identifier: Union[int, str], key: Union[int, str]) -> Dict[str, Any]:
    """Get a task from Freshrelease by ID."""
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/{project_identifier}/issues/{key}"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch task: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def fr_get_all_tasks(project_identifier: Union[int, str]) -> Dict[str, Any]:
    """Get a task from Freshrelease by ID."""
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/{project_identifier}/issues"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch task: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def fr_get_issue_type_by_name(project_identifier: Union[int, str], issue_type_name: str) -> Dict[str, Any]:
    """Fetch the issue type object for a given human name within a project.

    This function lists issue types under the specified project and returns the
    first match by case-insensitive name comparison.
    """
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/{project_identifier}/issue_types"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Expecting a list of objects with a 'name' property
            if isinstance(data, list):
                target = issue_type_name.strip().lower()
                for item in data:
                    name = str(item.get("name", "")).strip().lower()
                    if name == target:
                        return item
                return {"error": f"Issue type '{issue_type_name}' not found"}
            return {"error": "Unexpected response structure for issue types", "details": data}
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to fetch issue types: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

@mcp.tool()
async def fr_search_users(project_identifier: Union[int, str], search_text: str) -> Any:
    """Search users in a project by name or email.

    Calls `/{project_identifier}/users?q=search_text` and returns the JSON response.
    """
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/{project_identifier}/users"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }
    params = {"q": search_text}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to search users: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

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

@mcp.tool()
async def fr_link_testcase_issues(project_identifier: Union[int, str], testcase_keys: List[Union[str, int]], issue_keys: List[Union[str, int]]) -> Any:
    """Bulk update multiple test cases with issue links by keys.

    - Resolves `testcase_keys[]` via `GET /{project_identifier}/test_cases/{key}` to ids
    - Resolves `issue_keys[]` via `GET /{project_identifier}/issues/{key}` to ids
    - Performs: PUT `/{project_identifier}/test_cases/update_many` with body
      { "ids": [...], "test_case": { "issue_ids": [...] } }
    """
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    headers = {
        "Authorization": f"Token {FRESHRELEASE_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            # Resolve testcase keys to ids
            resolved_testcase_ids: List[int] = []
            for key in testcase_keys:
                resolved_testcase_ids.append(await testcase_id_from_key(client, base_url, project_identifier, headers, key))
            # Resolve issue keys to ids
            resolved_issue_ids = await issue_ids_from_keys(client, base_url, project_identifier, headers, issue_keys)
            url = f"{base_url}/{project_identifier}/test_cases/update_many"
            payload = {"ids": resolved_testcase_ids, "test_case": {"issue_ids": resolved_issue_ids}}
            response = await client.put(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to bulk update testcases: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}

def main():
    logging.info("Starting Freshdesk MCP server")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
