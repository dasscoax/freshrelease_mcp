import asyncio
from freshrelease_mcp.server import (
    fr_create_project,
    fr_get_project,
    fr_create_task,
    fr_get_task,
    fr_get_all_tasks,
    fr_search_users,
    fr_link_testcase_issues,
)

async def test_fr_create_project():
    result = await fr_create_project("Demo Project", description="Example")
    print(result)

async def test_fr_get_project():
    result = await fr_get_project("ENG")
    print(result)

async def test_fr_create_task():
    result = await fr_create_task("ENG", "Demo Task", description="Task details", issue_type_name="task")
    print(result)

async def test_fr_get_task():
    result = await fr_get_task("ENG", "ENG-123")
    print(result)

async def test_fr_get_all_tasks():
    result = await fr_get_all_tasks("ENG")
    print(result)

async def test_fr_search_users():
    result = await fr_search_users("ENG", "dev@yourco.com")
    print(result)

async def test_fr_link_testcase_issues():
    result = await fr_link_testcase_issues("ENG", ["TC-101", "TC-102"], ["ENG-123", "ENG-456"])
    print(result)

if __name__ == "__main__":
    # asyncio.run(test_fr_create_project())
    # asyncio.run(test_fr_get_project())
    # asyncio.run(test_fr_create_task())
    # asyncio.run(test_fr_get_task())
    # asyncio.run(test_fr_get_all_tasks())
    # asyncio.run(test_fr_search_users())
    # asyncio.run(test_fr_link_testcase_issues())
    pass