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
    status: Optional[str] = None,
    due_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a task under a Freshrelease project.

    - due_date: ISO 8601 date string (e.g., 2025-12-31) if supported by your account
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
        payload["status"] = status
    if due_date is not None:
        payload["due_date"] = due_date

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Failed to create task: {str(e)}", "details": e.response.json() if e.response else None}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}


@mcp.tool()
async def fr_get_task(project_identifier: Union[int, str],task_id: int) -> Dict[str, Any]:
    """Get a task from Freshrelease by ID."""
    if not FRESHRELEASE_DOMAIN or not FRESHRELEASE_API_KEY:
        return {"error": "FRESHRELEASE_DOMAIN or FRESHRELEASE_API_KEY is not set"}

    base_url = f"https://{FRESHRELEASE_DOMAIN}"
    url = f"{base_url}/{project_identifier}/issues/{task_id}"
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

def main():
    logging.info("Starting Freshdesk MCP server")
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
