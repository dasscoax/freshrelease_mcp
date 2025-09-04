import asyncio
from freshrelease_mcp.server import (
    fr_list_status_categories,
    fr_get_status_category_id,
    fr_get_status_category_id_from_name,
    fr_list_status_category_names,
    fr_create_project,
    fr_get_project,
    fr_create_task,
    fr_get_task,
)

async def test_fr_list_status_categories():
    result = await fr_list_status_categories()
    print(result)

async def test_fr_get_status_category_id():
    result = await fr_get_status_category_id("todo")
    print(result)

async def test_fr_get_status_category_id_from_name():
    result = await fr_get_status_category_id_from_name("Yet To Start")
    print(result)

async def test_fr_list_status_category_names():
    result = await fr_list_status_category_names()
    print(result)

async def test_fr_create_project():
    # Adjust parameters or mock environment as needed
    result = await fr_create_project("Demo Project", description="Example")
    print(result)

async def test_fr_get_project():
    # Replace with a valid key or ID in your environment
    result = await fr_get_project("ENG")
    print(result)

async def test_fr_create_task():
    # Replace with a valid key or ID in your environment
    result = await fr_create_task("ENG", "Demo Task", description="Task details")
    print(result)

async def test_fr_get_task():
    # Replace with a valid task ID in your environment
    result = await fr_get_task(123)
    print(result)

if __name__ == "__main__":
    # asyncio.run(test_fr_list_status_categories())
    # asyncio.run(test_fr_get_status_category_id())
    # asyncio.run(test_fr_get_status_category_id_from_name())
    # asyncio.run(test_fr_list_status_category_names())
    # asyncio.run(test_fr_create_project())
    # asyncio.run(test_fr_get_project())
    # asyncio.run(test_fr_create_task())
    # asyncio.run(test_fr_get_task())
    pass