import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys
import asyncio

# Add the parent directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.freshrelease_mcp.server import parse_link_header

# Create a mock version of our server functions to isolate testing
async def mock_list_companies(page=1, per_page=30):
    companies = [
        {
            "id": 51001000001,
            "name": "Acme Corp",
            "description": "Leading provider of widgets",
            "note": "Preferred vendor",
            "domains": ["acme.example"],
            "created_at": "2024-05-01T12:00:00Z",
            "updated_at": "2025-01-15T09:30:00Z",
            "custom_fields": {
                "organisation_name": "Acme Corp",
                "account_status": "Active",
                "hosting_platform": "AWS"
            }
        },
        {
            "id": 51001000002,
            "name": "Globex Inc",
            "domains": ["globex.com", "globex.org"],
            "created_at": "2024-11-10T08:45:00Z",
            "updated_at": "2025-02-20T16:10:00Z",
            "custom_fields": {
                "organisation_name": "Globex Inc",
                "account_status": "Expired"
            }
        }
    ]

    pagination_info = {
        "next": 2 if page < 3 else None,
        "prev": page - 1 if page > 1 else None
    }

    return {
        "companies": companies,
        "pagination": {
            "current_page": page,
            "next_page": pagination_info.get("next"),
            "prev_page": pagination_info.get("prev"),
            "per_page": per_page
        }
    }

async def mock_view_company(company_id):
    if company_id == 51001000001:
        return {
            "id": 51001000001,
            "name": "Acme Corp",
            "description": "Leading provider of widgets",
            "note": "Preferred vendor",
            "domains": ["acme.example"],
            "created_at": "2024-05-01T12:00:00Z",
            "updated_at": "2025-01-15T09:30:00Z",
            "custom_fields": {
                "organisation_name": "Acme Corp",
                "account_status": "Active",
                "hosting_platform": "AWS"
            }
        }
    else:
        return {"error": "Company not found"}

async def mock_search_companies(query):
    if "acme" in query.lower():
        return [
            {
                "id": 51001000001,
                "name": "Acme Corp"
            },
            {
                "id": 51001000002,
                "name": "Acme Solutions"
            }
        ]
    else:
        return []

async def mock_list_company_fields():
    return [
        {
            "id": 51000152653,
            "name": "name",
            "label": "Company Name",
            "position": 1,
            "required_for_agents": True,
            "type": "default_name",
            "default": True
        },
        {
            "id": 51000169767,
            "name": "organisation_name",
            "label": "Organisation Name",
            "position": 2,
            "required_for_agents": True,
            "type": "custom_text",
            "default": False
        },
        {
            "id": 51000265522,
            "name": "account_status",
            "label": "Account Status",
            "position": 3,
            "required_for_agents": False,
            "type": "custom_dropdown",
            "default": False,
            "choices": [
                "Active",
                "Expired"
            ]
        }
    ]

# Class for sync tests using unittest
class TestParseHeaderFunction(unittest.TestCase):
    def test_parse_link_header(self):
        # Test the parse_link_header function directly
        header = '<https://example.com/page=2>; rel="next", <https://example.com/page=1>; rel="prev"'
        result = parse_link_header(header)
        self.assertEqual(result.get('next'), 2)
        self.assertEqual(result.get('prev'), 1)

    def test_parse_link_header_empty(self):
        # Test with empty header
        result = parse_link_header("")
        self.assertEqual(result, {"next": None, "prev": None})

    def test_parse_link_header_invalid_format(self):
        # Test with invalid format
        result = parse_link_header("invalid format")
        self.assertEqual(result, {"next": None, "prev": None})

# Define async test cases outside of unittest framework
async def test_list_companies():
    result = await mock_list_companies(page=1, per_page=10)

    assert 'companies' in result
    assert len(result['companies']) == 2
    assert result['companies'][0]['name'] == 'Acme Corp'
    assert 'pagination' in result
    assert result['pagination']['current_page'] == 1
    assert 'next_page' in result['pagination']
    print("✓ test_list_companies passed")

async def test_view_company():
    result = await mock_view_company(51001000001)

    assert result['id'] == 51001000001
    assert result['name'] == 'Acme Corp'
    assert result['domains'] == ['acme.example']
    print("✓ test_view_company passed")

async def test_search_companies():
    result = await mock_search_companies("acme")

    assert len(result) == 2
    assert result[0]['id'] == 51001000001
    assert result[0]['name'] == 'Acme Corp'
    print("✓ test_search_companies passed")

async def test_list_company_fields():
    result = await mock_list_company_fields()

    assert len(result) == 3
    assert result[0]['name'] == 'name'
    assert result[1]['name'] == 'organisation_name'
    assert result[2]['name'] == 'account_status'
    print("✓ test_list_company_fields passed")

if __name__ == "__main__":
    # Run async tests
    print("Running async tests:")
    asyncio.run(test_list_companies())
    asyncio.run(test_view_company())
    asyncio.run(test_search_companies())
    asyncio.run(test_list_company_fields())

    # Run sync tests
    print("\nRunning sync tests:")
    unittest.main(argv=['first-arg-is-ignored'], exit=False)